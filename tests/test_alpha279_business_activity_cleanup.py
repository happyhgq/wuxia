"""Alpha279：默认场景不展示后台营生日志，人物状态与实际营生保持一致。"""
import contextlib
import io

from actions import handle_talk_and_ask, handle_world_activity, look
from economy import EconomyManager
import main
from player import Player
from ui_output import _ANSI_RE


def capture(fn, *args, **kwargs):
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        result = fn(*args, **kwargs)
    return _ANSI_RE.sub("", stream.getvalue()), result


def people_line(output, npc_name):
    for line in output.splitlines():
        stripped = line.strip()
        if stripped.startswith("【") or "：" not in stripped:
            continue
        if npc_name in stripped.split("：", 1)[0]:
            return stripped
    return ""


def player_at(room_id, economy_state=None):
    player = Player("营生显示测试", "散人")
    player.location = room_id
    if economy_state is not None:
        player.economy_state = economy_state
    return player


def test_default_scene_does_not_render_recent_business_log():
    manager = EconomyManager()
    manager.update(120)
    player = player_at("village_square", manager.export_state())
    output, _ = capture(look, player)
    assert "近期营生" not in output
    assert "【附近动态】" not in output
    assert "刚刚采购" not in output
    assert "木匠老许近日" not in output


def test_world_activity_query_uses_natural_language_without_backend_fields():
    manager = EconomyManager()
    manager.update(120)
    player = player_at("village_square", manager.export_state())
    output, _ = capture(handle_world_activity, player, ["8"])
    assert "江湖营生动态" in output
    assert "近日采集、制作与交易间" in output
    assert "近日" in output
    for internal in ("时辰", "单价", "room_id", "world_activity", "按配方消耗原料制成"):
        assert internal not in output


def test_local_business_query_only_reports_current_room():
    state = {
        "tick": 30,
        "events": {"world_activity": [
            {"tick": 30, "kind": "制作", "actor": "木匠老许", "action": "制作",
             "item": "木剑", "amount": 1, "room_id": "village_square"},
            {"tick": 30, "kind": "制作", "actor": "别处铁匠", "action": "制作",
             "item": "铁剑", "amount": 2, "room_id": "blacksmith"},
        ]},
    }
    player = player_at("village_square", state)
    output, _ = capture(handle_talk_and_ask, player, ["营生"])
    assert "【附近营生】" in output
    assert "木匠老许" in output and "木剑" in output
    assert "别处铁匠" not in output


def test_local_business_query_works_without_npcs_in_room():
    player = player_at("village_gate", {})
    output, _ = capture(handle_talk_and_ask, player, ["商情"])
    assert "营生如常" in output
    assert "此地空无一人" not in output


def test_look_shangqing_routes_to_local_business_query():
    state = {
        "tick": 7,
        "events": {"world_activity": [
            {"tick": 7, "kind": "交易", "actor": "药铺老板", "action": "采购原料",
             "item": "草药", "amount": 2, "room_id": "medicine_shop"},
        ]},
    }
    player = player_at("medicine_shop", state)
    output, _ = capture(look, player, ["商情"])
    assert "【附近营生】" in output
    assert "百草堂主" in output
    assert "草药" in output


def test_schedule_busy_wins_over_economy_activity_text():
    manager = EconomyManager()
    manager.update(10)
    manager.state.npc_inventory["铁匠"] = {"铁矿石": 8}
    manager.state.npc_inventory["木匠老许"] = {"木材": 8}
    state = manager.export_state()

    # 铁匠在卯时尚未开工，营生模拟的活动说明可以接管人物行。
    blacksmith = player_at("blacksmith", state)
    output, _ = capture(look, blacksmith)
    assert "正在打铁" in people_line(output, "铁匠")

    # 木匠老许此刻日程明确在岗，人物行以日程为准，不再被营生文案改写。
    square = player_at("village_square", state)
    output, _ = capture(look, square)
    line = people_line(output, "木匠老许")
    assert "支起木架做活" in line
    assert "正在制作木剑" not in line


def test_resting_npc_is_not_rewritten_as_working_after_hours():
    manager = EconomyManager()
    manager.update(20)
    player = player_at("blacksmith_inner", manager.export_state())
    # tick 13 = 19:00，铁匠已收炉回到内堂，不应再被营生模拟改写为“正在打铁”。
    player.set_var("quest_clock", 13)
    player.refresh_npc_schedules()
    output, _ = capture(look, player)
    line = people_line(output, "铁匠")
    assert line
    assert "正在打铁" not in line
    assert "在住处休息" not in line


def test_scene_status_does_not_leak_economy_backend_details():
    manager = EconomyManager()
    manager.update(10)
    manager.state.npc_inventory["铁匠"] = {"铁矿石": 8}
    player = player_at("blacksmith", manager.export_state())
    output, _ = capture(look, player)
    for internal in ("按库存和原料安排制作", "库存已满", "work_hours", "npc_inventory"):
        assert internal not in output


def test_help_and_command_aliases_expose_local_business_query():
    assert main.CMD_MAP.get("商情") == "business_rumor"
    assert main.CMD_MAP.get("营生消息") == "business_rumor"
    output, _ = capture(main.show_help, "商情")
    assert "打听 营生" in output
    assert "查看 商情" in output
