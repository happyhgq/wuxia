"""Alpha317：房间环境描述不得断言会随作息移动的 NPC 的当前动作或在场。"""
import contextlib
import io
import json
from pathlib import Path

import actions
import actor_display
import engine
from player import Player
from ui_output import _ANSI_RE

ROOT = Path(__file__).resolve().parents[1]


def room_data():
    return json.loads((ROOT / "data" / "rooms.json").read_text(encoding="utf-8"))


def capture(fn, *args):
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        result = fn(*args)
    return _ANSI_RE.sub("", stream.getvalue()), result


def make_player(room, tick):
    player = Player("环境描述一致", "散人")
    player.location = room
    player.set_var("quest_clock", tick)
    return player


def npc_line(output, npc_name):
    label = actor_display.format_room_label(npc_name)
    for line in output.splitlines():
        if line.strip().startswith(label + "："):
            return line.strip()
    return ""


def test_medicine_shop_desc_does_not_assert_apothecary_action():
    desc = room_data()["medicine_shop"]["desc"]
    assert "研磨" not in desc
    assert "待称的药材" in desc


def test_medicine_shop_look_matches_morning_schedule():
    # tick 2 = 08:00，药铺老板在柜台称药、包药。
    player = make_player("medicine_shop", 2)
    output, _ = capture(actions.look, player)
    assert "正在柜台后称药、包药" in npc_line(output, "药铺老板")
    assert "研磨" not in output


def test_blacksmith_desc_does_not_assert_smith_or_apprentice_action():
    desc = room_data()["blacksmith"]["desc"]
    assert "抡锤" not in desc
    assert "拉风箱" not in desc


def test_blacksmith_lunch_break_lists_no_smith_or_apprentice():
    # tick 6 = 12:00，铁匠在内堂用午饭，学徒在广场歇息。
    player = make_player("blacksmith", 6)
    output, _ = capture(actions.look, player)
    assert npc_line(output, "铁匠") == ""
    assert npc_line(output, "铁匠学徒小石") == ""


def test_village_gate_desc_does_not_claim_dozing_guard():
    room = room_data()["village_gate"]
    assert "打盹" not in room["desc"]
    assert "无人值守" in room["night_desc"]


def test_village_gate_morning_patrol_leaves_gate_unmanned():
    # tick 0 = 06:00，守卫在长街巡逻，村口人物列表为空。
    player = make_player("village_gate", 0)
    output, _ = capture(actions.look, player)
    assert npc_line(output, "守卫") == ""


def test_village_gate_noon_guard_on_duty():
    # tick 6 = 12:00，守卫回到村口值守。
    player = make_player("village_gate", 6)
    output, _ = capture(actions.look, player)
    assert "正在村口值守" in npc_line(output, "守卫")


def test_village_head_house_desc_does_not_assert_chief_presence():
    desc = room_data()["village_head_house"]["desc"]
    assert "负手而立" not in desc


def test_village_head_house_morning_chief_at_square():
    # tick 2 = 08:00，村长在广场听村民说事。
    player = make_player("village_head_house", 2)
    output, _ = capture(actions.look, player)
    assert npc_line(output, "村长") == ""


def test_village_head_house_afternoon_chief_on_site():
    # tick 8 = 14:00，村长在正房与里正核对账册。
    player = make_player("village_head_house", 8)
    output, _ = capture(actions.look, player)
    assert "在正房与里正核对田亩账册" in npc_line(output, "村长")


def test_village_square_desc_names_stall_not_vendor_presence():
    desc = room_data()["village_square"]["desc"]
    assert "菜贩孙婶的菜摊" in desc
    assert "菜贩孙婶摆摊" not in desc


def test_engine_fallback_desc_has_no_stale_npc_action():
    fallback = {
        "village_gate": "打盹",
        "medicine_shop": "研磨",
        "blacksmith": "抡锤",
        "village_head_house": "负手而立",
    }
    for room_id, phrase in fallback.items():
        assert phrase not in engine.DEFAULT_ROOMS[room_id]["desc"]
