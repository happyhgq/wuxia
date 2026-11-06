"""Alpha282：武当剑理、内功听息与外门日常组成的独立任务线。"""
import contextlib
import io
import json
from pathlib import Path

import engine
from actions import handle_quest
from player import Player
from travel_system import room_access_denial

ROOT = Path(__file__).resolve().parents[1]

TRIAL = "武当历练·以静制动"
PATROL = "武当历练·松径清扰"
SWORD = "武当剑理·松间问道"
INNER = "武当内功·紫霄听息"
OUTER = "武当外门·晨钟暮鼓"

TRAINING_GROUND = "wudang_training_ground"
OUTER_COURT = "wudang_outer_court"
GATE = "wudang_gate"


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


def make_wudang_player(monkeypatch, name="武当任务线测试"):
    # 任务交付会正常写回游戏存档；测试显式使用临时存档，避免污染正式存档。
    monkeypatch.setattr(Player, "save_to_file", lambda self, filename=None: True)
    player = Player(name, "散人")
    player.level = 30
    ok, message = player.join_sect("武当")
    assert ok, message
    return player


def set_mastery(player, skill_name, mastery):
    state = player._ensure_skill_state()
    state.setdefault(skill_name, {"learned": True, "mastery": 0})
    state[skill_name]["learned"] = True
    state[skill_name]["mastery"] = mastery


def complete_prerequisite_quests(player):
    player.location = TRAINING_GROUND
    assert "已接取任务" in accept(player, TRIAL)
    for _ in range(2):
        capture(player.update_quest_progress, "黑风寨精锐", "kill")
    assert "奖励已结算" in deliver(player, TRIAL)

    assert "已接取任务" in accept(player, PATROL)
    for _ in range(2):
        capture(player.update_quest_progress, "黑风寨精锐", "kill")
    assert "奖励已结算" in deliver(player, PATROL)


def test_wudang_questline_data_chain_is_complete_and_reachable():
    quests = read_data("quests.json")
    npcs = read_data("npcs.json")
    items = read_data("items.json")
    rooms = read_data("rooms.json")
    sects = read_data("sects.json")

    chain = [SWORD, INNER, OUTER]
    for quest in chain:
        assert quest in quests

    assert quests[SWORD]["requires"]["completed_quests"] == [PATROL]
    assert quests[SWORD]["requires"]["skills"]["太极剑"]["mastery"]["gte"] == 10
    assert quests[INNER]["requires"]["completed_quests"] == [SWORD]
    assert quests[INNER]["requires"]["level"] == 3
    assert quests[INNER]["requires"]["sect_reputation"]["武当"]["gte"] == 20
    assert quests[OUTER]["requires"]["completed_quests"] == [INNER]
    assert quests[OUTER]["requires"]["flags"] == ["sect:wudang:rank:1"]

    assert quests[SWORD]["on_complete"]["set_flags"]["sect:wudang:sword_principle"] is True
    assert quests[SWORD]["on_complete"]["set_flags"][
        "sect:wudang:questline:sword_principle_done"
    ] is True
    assert quests[INNER]["on_complete"]["set_flags"][
        "sect:wudang:questline:inner_breath_done"
    ] is True
    assert quests[OUTER]["on_complete"]["set_flags"][
        "sect:wudang:questline:outer_daily_done"
    ] is True

    assert quests[SWORD]["reward"]["item"] == "太极剑穗"
    assert items["太极剑穗"]["type"] == "accessory"
    assert quests[INNER]["reward"]["item"] == "清心散"
    assert quests[OUTER]["reward"]["item"] == "行军干粮"

    # 任务链在入门阶段即可接取，不得被更高身份区域或未设计内容锁住。
    assert "武当传功师兄" in rooms[TRAINING_GROUND]["npcs"]
    assert "武当传功师父" in rooms[TRAINING_GROUND]["npcs"]
    assert "武当执事弟子" in rooms[OUTER_COURT]["npcs"]
    assert "武当守山弟子" in rooms[GATE]["npcs"]

    assert SWORD in npcs["武当传功师兄"]["quests"]
    assert INNER in npcs["武当传功师父"]["quests"]
    assert OUTER in npcs["武当执事弟子"]["quests"]

    # 晋升门槛改为门派数据驱动，且武当外门/内门分别绑定剑理与内功任务。
    assert sects["武当"]["promotion_flags"]["1"] == ["sect:wudang:sword_principle"]
    assert sects["武当"]["promotion_flags"]["2"] == [
        "sect:wudang:questline:inner_breath_done"
    ]
    assert sects["少林"]["promotion_flags"]["4"] == [
        "sect:shaolin:scripture_catalogue_reviewed"
    ]


def test_wudang_questline_is_reachable_at_entry_rank():
    rooms = read_data("rooms.json")
    for room_id in (TRAINING_GROUND, OUTER_COURT, GATE):
        assert "min_rank_index" not in (rooms[room_id].get("access") or {})

    player = Player("武当入门可达性", "散人")
    assert player.join_sect("武当")[0]
    assert player.get_sect_official_rank_index("武当") == 0
    for room_id in (TRAINING_GROUND, OUTER_COURT, GATE):
        assert room_access_denial(player, rooms[room_id]) == ""

    guest = Player("武当门外访客", "散人")
    assert room_access_denial(guest, rooms[TRAINING_GROUND])
    assert room_access_denial(guest, rooms[OUTER_COURT])


def test_wudang_questline_full_flow_branch_and_v12_round_trip(tmp_path, monkeypatch):
    real_save_to_file = Player.save_to_file
    player = make_wudang_player(monkeypatch)
    complete_prerequisite_quests(player)

    set_mastery(player, "太极剑", 10)
    player.location = TRAINING_GROUND
    assert "已接取任务" in accept(player, SWORD)
    assert player.quest_states[SWORD]["stage"] == 0

    capture(player.update_quest_progress, "武当传功师父", "talk")
    assert player.quest_states[SWORD].get("branch_pending") is True
    options = player.get_quest_branch_options(SWORD)
    assert [option["id"] for option in options] == ["observe_sword", "ask_principle"]
    ok, message = player.choose_quest_branch(SWORD, "observe_sword")
    assert ok, message
    assert player.get_flag("sect:wudang:sword_principle:observe") is True
    assert player.quest_states[SWORD]["stage"] == 1

    # 中途存档/读档必须保留任务阶段与分支选择，且仍是 V12。
    mid_save = tmp_path / "wudang_sword_mid.json"
    assert real_save_to_file(player, str(mid_save))
    raw = json.loads(mid_save.read_text(encoding="utf-8"))
    assert raw["version"] == engine.SAVE_VERSION
    reloaded = Player.load_from_file(str(mid_save))
    assert reloaded is not None
    assert reloaded.quest_states[SWORD]["stage"] == 1
    assert reloaded.get_flag("sect:wudang:sword_principle:observe") is True
    player = reloaded

    capture(player.update_quest_progress, "武当执事弟子", "talk")
    assert player.quest_states[SWORD]["stage"] == 2
    capture(player.update_quest_progress, "武当传功师父", "talk")
    player.location = TRAINING_GROUND
    assert "奖励已结算" in deliver(player, SWORD)
    assert player.get_flag("sect:wudang:sword_principle") is True
    assert player.get_flag("sect:wudang:questline:sword_principle_done") is True
    assert "太极剑穗" in player.inventory

    # 剑理完成后可晋升外门；内功未完成时，内门晋升应被数据门槛挡住。
    ok, message = player.promote_sect_rank("武当")
    assert ok, message
    assert player.get_sect_official_rank_index("武当") == 1
    assert player.get_flag("sect:wudang:rank:1") is True

    set_mastery(player, "太极剑", 30)
    ok, message = player.promote_sect_rank("武当")
    assert not ok
    assert "《武当内功·紫霄听息》" in message
    assert "sect:" not in message

    assert "已接取任务" in accept(player, INNER)
    capture(player.update_quest_progress, "武当执事弟子", "talk")
    capture(player.update_quest_progress, "武当传功师父", "talk")
    player.location = TRAINING_GROUND
    assert "奖励已结算" in deliver(player, INNER)
    assert player.get_flag("sect:wudang:questline:inner_breath_done") is True
    assert "清心散" in player.inventory

    ok, message = player.promote_sect_rank("武当")
    assert ok, message
    assert player.get_sect_official_rank_index("武当") == 2

    # 外门日常要求内功完成且已正式成为外门弟子。
    player.location = OUTER_COURT
    assert "已接取任务" in accept(player, OUTER)
    for target in ("武当执事弟子", "武当守山弟子", "武当传功师兄"):
        capture(player.update_quest_progress, target, "talk")
    assert "奖励已结算" in deliver(player, OUTER)
    assert player.get_flag("sect:wudang:questline:outer_daily_done") is True
    assert "行军干粮" in player.inventory
    assert OUTER in player.completed_quests

    final_save = tmp_path / "wudang_questline_final.json"
    assert real_save_to_file(player, str(final_save))
    final_raw = json.loads(final_save.read_text(encoding="utf-8"))
    assert final_raw["version"] == engine.SAVE_VERSION
    restored = Player.load_from_file(str(final_save))
    assert restored is not None
    assert restored.get_sect_official_rank_index("武当") == 2
    assert restored.get_flag("sect:wudang:sword_principle") is True
    assert restored.get_flag("sect:wudang:questline:inner_breath_done") is True
    assert restored.get_flag("sect:wudang:questline:outer_daily_done") is True
    assert OUTER in restored.completed_quests


def test_wudang_promotion_flags_use_natural_language(monkeypatch):
    player = make_wudang_player(monkeypatch, name="武当晋升门槛测试")
    player.change_sect_reputation("武当", 500)
    set_mastery(player, "太极剑", 100)

    ok, message = player.promote_sect_rank("武当")
    assert not ok
    assert "《武当剑理·松间问道》" in message
    assert "sect:" not in message

    player.set_flag("sect:wudang:sword_principle", True)
    ok, message = player.promote_sect_rank("武当")
    assert ok, message
    assert player.get_sect_official_rank_index("武当") == 1

    ok, message = player.promote_sect_rank("武当")
    assert not ok
    assert "《武当内功·紫霄听息》" in message
    assert "sect:" not in message

    player.set_flag("sect:wudang:questline:inner_breath_done", True)
    ok, message = player.promote_sect_rank("武当")
    assert ok, message
    assert player.get_sect_official_rank_index("武当") == 2


def test_locked_wudang_quest_hints_are_natural_language(monkeypatch):
    player = make_wudang_player(monkeypatch, name="武当锁定提示测试")
    player.location = TRAINING_GROUND

    locked = accept(player, SWORD)
    assert "接取失败" in locked
    assert "需先完成并交付【武当历练·松径清扰】" in locked

    player.completed_quests.extend([TRIAL, PATROL])
    locked = accept(player, INNER)
    assert "接取失败" in locked
    assert "需先完成并交付【武当剑理·松间问道】" in locked
    assert "sect:" not in locked
    assert "gte" not in locked
    assert INNER not in player.active_quests

    # 外门日常在未正式晋升前不得提前解锁，也不得泄露内部标记。
    player.completed_quests.append(SWORD)
    set_mastery(player, "太极剑", 10)
    locked = accept(player, OUTER)
    assert "接取失败" in locked
    assert "需先晋升为【武当·外门弟子】" in locked
    assert "sect:wudang:rank:1" not in locked
    assert OUTER not in player.active_quests
