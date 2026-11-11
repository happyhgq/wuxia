"""Alpha283：华山剑理/巡剑与铁衣门商路/护送任务线、晋升门槛与门派面板。"""
import contextlib
import io
import json
from pathlib import Path

import engine
from actions import handle_quest, handle_sect
from player import Player
from travel_system import room_access_denial

ROOT = Path(__file__).resolve().parents[1]

HUASHAN_TRIAL = "华山历练·磨剑黑风"
HUASHAN_PATROL = "华山历练·险道试剑"
HUASHAN_SWORD = "华山剑理·松风听剑"
HUASHAN_ROAD = "华山巡剑·古道清障"

TIEYI_TRIAL = "铁衣门历练·护路除匪"
TIEYI_PATROL = "铁衣门历练·清除巡哨"
TIEYI_TRADE = "铁衣门护运·商路问价"
TIEYI_ESCORT = "铁衣门守约·短途护送"

HUASHAN_TRAINING = "huashan_training_ground"
HUASHAN_GATE = "huashan_gate"
TIEYI_GUEST = "tieyi_guest_hall"
TIEYI_OUTER = "tieyi_outer_court"
TIEYI_GATE = "tieyi_gate"


def read_data(name):
    return json.loads((ROOT / "data" / name).read_text(encoding="utf-8"))


def capture(fn, *args):
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        fn(*args)
    return output.getvalue()


def accept(player, quest):
    return capture(handle_quest, player, "jiequ", [quest])


def deliver(player, quest):
    return capture(handle_quest, player, "jiaofu", [quest])


def set_mastery(player, skill_name, mastery):
    state = player._ensure_skill_state()
    state.setdefault(skill_name, {"learned": True, "mastery": 0})
    state[skill_name]["learned"] = True
    state[skill_name]["mastery"] = mastery


def make_player(monkeypatch, sect, name="Alpha283任务线测试"):
    # 任务交付会写回游戏存档；测试显式使用临时存档，避免污染正式存档。
    monkeypatch.setattr(Player, "save_to_file", lambda self, filename=None: True)
    player = Player(name, "散人")
    player.level = 30
    ok, message = player.join_sect(sect)
    assert ok, message
    return player


def complete_huashan_prerequisites(player):
    player.location = HUASHAN_TRAINING
    assert "已接取任务" in accept(player, HUASHAN_TRIAL)
    for _ in range(2):
        capture(player.update_quest_progress, "黑风寨精锐", "kill")
    assert "奖励已结算" in deliver(player, HUASHAN_TRIAL)

    assert "已接取任务" in accept(player, HUASHAN_PATROL)
    capture(player.update_quest_progress, "黑风寨刀阵头目", "kill")
    assert "奖励已结算" in deliver(player, HUASHAN_PATROL)


def complete_tieyi_prerequisites(player):
    player.location = TIEYI_GUEST
    assert "已接取任务" in accept(player, TIEYI_TRIAL)
    for _ in range(2):
        capture(player.update_quest_progress, "劫镖山贼", "kill")
    assert "奖励已结算" in deliver(player, TIEYI_TRIAL)

    player.location = TIEYI_OUTER
    assert "已接取任务" in accept(player, TIEYI_PATROL)
    for _ in range(2):
        capture(player.update_quest_progress, "黑风寨精锐", "kill")
    assert "奖励已结算" in deliver(player, TIEYI_PATROL)


def test_alpha283_data_chain_items_npcs_and_questline_metadata():
    quests = read_data("quests.json")
    npcs = read_data("npcs.json")
    items = read_data("items.json")
    rooms = read_data("rooms.json")
    sects = read_data("sects.json")

    for quest in (HUASHAN_SWORD, HUASHAN_ROAD, TIEYI_TRADE, TIEYI_ESCORT):
        assert quest in quests

    assert quests[HUASHAN_SWORD]["requires"]["completed_quests"] == [HUASHAN_PATROL]
    assert quests[HUASHAN_SWORD]["requires"]["skills"]["华山剑法"]["mastery"]["gte"] == 10
    assert quests[HUASHAN_ROAD]["requires"]["completed_quests"] == [HUASHAN_SWORD]
    assert quests[HUASHAN_ROAD]["requires"]["flags"] == ["sect:huashan:rank:1"]

    assert quests[TIEYI_TRADE]["requires"]["completed_quests"] == [TIEYI_PATROL]
    assert quests[TIEYI_TRADE]["requires"]["level"] == 3
    assert quests[TIEYI_TRADE]["requires"]["skills"]["铁衣功"]["mastery"]["gte"] == 10
    assert quests[TIEYI_ESCORT]["requires"]["completed_quests"] == [TIEYI_TRADE]
    assert quests[TIEYI_ESCORT]["requires"]["flags"] == ["sect:tieyi:rank:1"]

    assert quests[HUASHAN_SWORD]["on_complete"]["set_flags"]["sect:huashan:sword_principle"] is True
    assert quests[HUASHAN_SWORD]["on_complete"]["set_flags"][
        "sect:huashan:questline:sword_principle_done"
    ] is True
    assert quests[HUASHAN_ROAD]["on_complete"]["set_flags"][
        "sect:huashan:questline:patrol_done"
    ] is True
    assert quests[TIEYI_TRADE]["on_complete"]["set_flags"]["sect:tieyi:trade_route"] is True
    assert quests[TIEYI_TRADE]["on_complete"]["set_flags"][
        "sect:tieyi:questline:trade_route_done"
    ] is True
    assert quests[TIEYI_ESCORT]["on_complete"]["set_flags"][
        "sect:tieyi:questline:escort_done"
    ] is True

    assert quests[HUASHAN_SWORD]["reward"]["item"] == "华山剑穗"
    assert items["华山剑穗"]["type"] == "accessory"
    assert quests[HUASHAN_ROAD]["reward"]["item"] == "行军干粮"
    assert quests[TIEYI_TRADE]["reward"]["item"] == "行军干粮"
    assert quests[TIEYI_ESCORT]["reward"]["item"] == "铁衣护腕"
    assert items["铁衣护腕"]["type"] == "armor"

    # 护运执事必须在外院，保证低阶弟子能接取前置历练与新任务线。
    assert "铁衣门护运执事" in rooms[TIEYI_OUTER]["npcs"]
    assert "铁衣门护运执事" not in (rooms["tieyi_council_hall"].get("npcs") or [])
    assert "铁衣门守门弟子" in rooms[TIEYI_GATE]["npcs"]
    assert "华山授业师父" in rooms[HUASHAN_TRAINING]["npcs"]
    assert "华山守门弟子" in rooms[HUASHAN_GATE]["npcs"]

    assert HUASHAN_SWORD in npcs["华山传功师兄"]["quests"]
    assert HUASHAN_ROAD in npcs["华山传功师兄"]["quests"]
    assert TIEYI_TRADE in npcs["铁衣门护运执事"]["quests"]
    assert TIEYI_ESCORT in npcs["铁衣门护运执事"]["quests"]

    assert sects["华山"]["promotion_flags"]["1"] == ["sect:huashan:sword_principle"]
    assert sects["华山"]["promotion_flags"]["2"] == [
        "sect:huashan:questline:patrol_done"
    ]
    assert sects["铁衣门"]["promotion_flags"]["1"] == ["sect:tieyi:trade_route"]
    assert sects["铁衣门"]["promotion_flags"]["2"] == [
        "sect:tieyi:questline:escort_done"
    ]
    huashan_line = [entry["quest"] for entry in sects["华山"]["questline"]]
    tieyi_line = [entry["quest"] for entry in sects["铁衣门"]["questline"]]
    assert huashan_line == [
        HUASHAN_TRIAL, HUASHAN_PATROL, HUASHAN_SWORD, HUASHAN_ROAD, "青锋疑云"
    ]
    assert tieyi_line == [TIEYI_TRIAL, TIEYI_PATROL, TIEYI_TRADE, TIEYI_ESCORT]
    assert sects["华山"]["questline"][-1]["optional"] is True


def test_alpha283_first_new_quests_are_reachable_at_entry_rank(monkeypatch):
    rooms = read_data("rooms.json")
    for room_id in (HUASHAN_TRAINING, HUASHAN_GATE, TIEYI_OUTER, TIEYI_GATE):
        assert "min_rank_index" not in (rooms[room_id].get("access") or {})

    huashan = make_player(monkeypatch, "华山", "华山入门可达性")
    assert huashan.get_sect_official_rank_index("华山") == 0
    for room_id in (HUASHAN_TRAINING, HUASHAN_GATE):
        assert room_access_denial(huashan, rooms[room_id]) == ""
    huashan.completed_quests.extend([HUASHAN_TRIAL, HUASHAN_PATROL])
    set_mastery(huashan, "华山剑法", 10)
    huashan.location = HUASHAN_TRAINING
    assert "已接取任务" in accept(huashan, HUASHAN_SWORD)

    tieyi = make_player(monkeypatch, "铁衣门", "铁衣门入门可达性")
    assert tieyi.get_sect_official_rank_index("铁衣门") == 0
    for room_id in (TIEYI_OUTER, TIEYI_GATE):
        assert room_access_denial(tieyi, rooms[room_id]) == ""
    tieyi.completed_quests.extend([TIEYI_TRIAL, TIEYI_PATROL])
    tieyi.level = 3
    set_mastery(tieyi, "铁衣功", 10)
    tieyi.location = TIEYI_OUTER
    assert "已接取任务" in accept(tieyi, TIEYI_TRADE)

    guest = Player("门派门外访客", "散人")
    assert room_access_denial(guest, rooms[HUASHAN_TRAINING])
    assert room_access_denial(guest, rooms[TIEYI_OUTER])


def test_huashan_questline_full_flow_and_v12_round_trip(tmp_path, monkeypatch):
    real_save_to_file = Player.save_to_file
    player = make_player(monkeypatch, "华山", "华山任务线全流程")
    complete_huashan_prerequisites(player)

    set_mastery(player, "华山剑法", 10)
    player.location = HUASHAN_TRAINING
    assert "已接取任务" in accept(player, HUASHAN_SWORD)

    capture(player.update_quest_progress, "华山授业师父", "talk")
    assert player.quest_states[HUASHAN_SWORD].get("branch_pending") is True
    options = player.get_quest_branch_options(HUASHAN_SWORD)
    assert [option["id"] for option in options] == ["speed_first", "steady_first"]
    ok, message = player.choose_quest_branch(HUASHAN_SWORD, "speed_first")
    assert ok, message
    assert player.get_flag("sect:huashan:sword_principle:speed") is True

    # 中途存档/读档必须保留任务阶段与分支选择，且仍是 V12。
    mid_save = tmp_path / "huashan_sword_mid.json"
    assert real_save_to_file(player, str(mid_save))
    raw = json.loads(mid_save.read_text(encoding="utf-8"))
    assert raw["version"] == engine.SAVE_VERSION
    reloaded = Player.load_from_file(str(mid_save))
    assert reloaded is not None
    assert reloaded.quest_states[HUASHAN_SWORD]["stage"] == 1
    assert reloaded.get_flag("sect:huashan:sword_principle:speed") is True
    player = reloaded

    capture(player.update_quest_progress, "华山守门弟子", "talk")
    assert player.quest_states[HUASHAN_SWORD]["stage"] == 2
    capture(player.update_quest_progress, "华山传功师兄", "talk")
    player.location = HUASHAN_TRAINING
    assert "奖励已结算" in deliver(player, HUASHAN_SWORD)
    assert player.get_flag("sect:huashan:sword_principle") is True
    assert player.get_flag("sect:huashan:questline:sword_principle_done") is True
    assert "华山剑穗" in player.inventory

    # 剑理完成后才允许晋升外门。
    ok, message = player.promote_sect_rank("华山")
    assert ok, message
    assert player.get_sect_official_rank_index("华山") == 1
    assert player.get_flag("sect:huashan:rank:1") is True

    assert "已接取任务" in accept(player, HUASHAN_ROAD)
    capture(player.update_quest_progress, "华山守门弟子", "talk")
    for _ in range(2):
        capture(player.update_quest_progress, "黑风寨精锐", "kill")
    capture(player.update_quest_progress, "华山传功师兄", "talk")
    player.location = HUASHAN_TRAINING
    assert "奖励已结算" in deliver(player, HUASHAN_ROAD)
    assert player.get_flag("sect:huashan:questline:patrol_done") is True
    assert "行军干粮" in player.inventory

    # 巡剑完成后才允许晋升内门。
    player.level = 10
    set_mastery(player, "华山剑法", 30)
    ok, message = player.promote_sect_rank("华山")
    assert ok, message
    assert player.get_sect_official_rank_index("华山") == 2

    final_save = tmp_path / "huashan_questline_final.json"
    assert real_save_to_file(player, str(final_save))
    final_raw = json.loads(final_save.read_text(encoding="utf-8"))
    assert final_raw["version"] == engine.SAVE_VERSION
    restored = Player.load_from_file(str(final_save))
    assert restored is not None
    assert restored.get_sect_official_rank_index("华山") == 2
    assert restored.get_flag("sect:huashan:sword_principle") is True
    assert restored.get_flag("sect:huashan:questline:patrol_done") is True
    assert HUASHAN_ROAD in restored.completed_quests


def test_tieyi_questline_full_flow_and_v12_round_trip(tmp_path, monkeypatch):
    real_save_to_file = Player.save_to_file
    player = make_player(monkeypatch, "铁衣门", "铁衣门任务线全流程")
    complete_tieyi_prerequisites(player)

    player.level = 5
    set_mastery(player, "铁衣功", 10)
    player.location = TIEYI_OUTER
    assert "已接取任务" in accept(player, TIEYI_TRADE)

    capture(player.update_quest_progress, "铁衣门守门弟子", "talk")
    capture(player.update_quest_progress, "铁衣门接引执事", "talk")
    assert player.quest_states[TIEYI_TRADE].get("branch_pending") is True
    options = player.get_quest_branch_options(TIEYI_TRADE)
    assert [option["id"] for option in options] == ["fair_price", "secure_route"]
    ok, message = player.choose_quest_branch(TIEYI_TRADE, "secure_route")
    assert ok, message
    assert player.get_flag("sect:tieyi:trade_route:secure") is True

    mid_save = tmp_path / "tieyi_trade_mid.json"
    assert real_save_to_file(player, str(mid_save))
    raw = json.loads(mid_save.read_text(encoding="utf-8"))
    assert raw["version"] == engine.SAVE_VERSION
    reloaded = Player.load_from_file(str(mid_save))
    assert reloaded is not None
    assert reloaded.quest_states[TIEYI_TRADE]["stage"] == 2
    assert reloaded.get_flag("sect:tieyi:trade_route:secure") is True
    player = reloaded

    capture(player.update_quest_progress, "铁衣门护运执事", "talk")
    player.location = TIEYI_OUTER
    assert "奖励已结算" in deliver(player, TIEYI_TRADE)
    assert player.get_flag("sect:tieyi:trade_route") is True
    assert player.get_flag("sect:tieyi:questline:trade_route_done") is True
    assert "行军干粮" in player.inventory

    ok, message = player.promote_sect_rank("铁衣门")
    assert ok, message
    assert player.get_sect_official_rank_index("铁衣门") == 1
    assert player.get_flag("sect:tieyi:rank:1") is True

    assert "已接取任务" in accept(player, TIEYI_ESCORT)
    capture(player.update_quest_progress, "铁衣门守门弟子", "talk")
    for _ in range(2):
        capture(player.update_quest_progress, "劫镖山贼", "kill")
    capture(player.update_quest_progress, "铁衣门护运执事", "talk")
    player.location = TIEYI_OUTER
    assert "奖励已结算" in deliver(player, TIEYI_ESCORT)
    assert player.get_flag("sect:tieyi:questline:escort_done") is True
    assert "铁衣护腕" in player.inventory

    player.level = 10
    set_mastery(player, "铁衣功", 30)
    ok, message = player.promote_sect_rank("铁衣门")
    assert ok, message
    assert player.get_sect_official_rank_index("铁衣门") == 2

    final_save = tmp_path / "tieyi_questline_final.json"
    assert real_save_to_file(player, str(final_save))
    final_raw = json.loads(final_save.read_text(encoding="utf-8"))
    assert final_raw["version"] == engine.SAVE_VERSION
    restored = Player.load_from_file(str(final_save))
    assert restored is not None
    assert restored.get_sect_official_rank_index("铁衣门") == 2
    assert restored.get_flag("sect:tieyi:trade_route") is True
    assert restored.get_flag("sect:tieyi:questline:escort_done") is True
    assert TIEYI_ESCORT in restored.completed_quests


def test_huashan_and_tieyi_promotion_flags_use_natural_language(monkeypatch):
    huashan = make_player(monkeypatch, "华山", "华山晋升门槛测试")
    huashan.change_sect_reputation("华山", 500)
    set_mastery(huashan, "华山剑法", 100)

    ok, message = huashan.promote_sect_rank("华山")
    assert not ok
    assert "《华山剑理·松风听剑》" in message
    assert "sect:" not in message

    huashan.set_flag("sect:huashan:sword_principle", True)
    ok, message = huashan.promote_sect_rank("华山")
    assert ok, message
    assert huashan.get_sect_official_rank_index("华山") == 1

    ok, message = huashan.promote_sect_rank("华山")
    assert not ok
    assert "《华山巡剑·古道清障》" in message
    assert "sect:" not in message

    huashan.set_flag("sect:huashan:questline:patrol_done", True)
    ok, message = huashan.promote_sect_rank("华山")
    assert ok, message
    assert huashan.get_sect_official_rank_index("华山") == 2

    tieyi = make_player(monkeypatch, "铁衣门", "铁衣门晋升门槛测试")
    tieyi.change_sect_reputation("铁衣门", 500)
    set_mastery(tieyi, "铁衣功", 100)

    ok, message = tieyi.promote_sect_rank("铁衣门")
    assert not ok
    assert "《铁衣门护运·商路问价》" in message
    assert "sect:" not in message

    tieyi.set_flag("sect:tieyi:trade_route", True)
    ok, message = tieyi.promote_sect_rank("铁衣门")
    assert ok, message
    assert tieyi.get_sect_official_rank_index("铁衣门") == 1

    ok, message = tieyi.promote_sect_rank("铁衣门")
    assert not ok
    assert "《铁衣门守约·短途护送》" in message
    assert "sect:" not in message

    tieyi.set_flag("sect:tieyi:questline:escort_done", True)
    ok, message = tieyi.promote_sect_rank("铁衣门")
    assert ok, message
    assert tieyi.get_sect_official_rank_index("铁衣门") == 2


def test_sect_panel_lists_questline_status_and_natural_hints(monkeypatch):
    player = make_player(monkeypatch, "华山", "华山任务线面板")
    entries = {entry["quest"]: entry for entry in player.get_sect_questline_summary()}

    assert entries[HUASHAN_TRIAL]["status"] == "available"
    assert entries[HUASHAN_PATROL]["status"] == "locked"
    assert entries[HUASHAN_SWORD]["status"] == "locked"
    assert entries[HUASHAN_ROAD]["status"] == "locked"
    assert entries["青锋疑云"]["status"] == "available"
    assert entries["青锋疑云"]["optional"] is True

    assert entries[HUASHAN_PATROL]["giver"] == "华山传功师兄"
    assert entries[HUASHAN_PATROL]["location"] == "华山演武场"
    assert any("华山历练·磨剑黑风" in hint for hint in entries[HUASHAN_PATROL]["missing"])
    assert any("外门弟子" in hint for hint in entries[HUASHAN_ROAD]["missing"])

    output = capture(handle_sect, player, [])
    assert "门派任务线" in output
    assert "可接取" in output and "未解锁" in output
    assert "（可选）" in output
    assert "发布：华山传功师兄" in output
    assert "地点：华山演武场" in output
    assert "需先完成并交付【华山历练·磨剑黑风】" in output
    assert "sect:" not in output

    # 完成任务后，面板要切换为已完成/可接取，而不是一直显示锁定。
    player.completed_quests.extend([HUASHAN_TRIAL, HUASHAN_PATROL])
    set_mastery(player, "华山剑法", 10)
    updated = {entry["quest"]: entry for entry in player.get_sect_questline_summary()}
    assert updated[HUASHAN_TRIAL]["status"] == "completed"
    assert updated[HUASHAN_PATROL]["status"] == "completed"
    assert updated[HUASHAN_SWORD]["status"] == "available"
    assert updated[HUASHAN_ROAD]["status"] == "locked"

    player.active_quests[HUASHAN_SWORD] = 0
    active = {entry["quest"]: entry for entry in player.get_sect_questline_summary()}
    assert active[HUASHAN_SWORD]["status"] == "active"
