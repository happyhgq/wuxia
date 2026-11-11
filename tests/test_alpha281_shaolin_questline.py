"""Alpha281：少林戒律、护寺、受戒与身份晋升组成的独立任务线。"""
import contextlib
import io
import json
from pathlib import Path

import engine
from actions import handle_quest
from player import Player
from travel_system import room_access_denial

ROOT = Path(__file__).resolve().parents[1]

TRIAL = "少林历练·黑风除恶"
PATROL = "少林历练·巡山护戒"
DISCIPLINE = "少林戒律·问心持戒"
TEMPLE_GUARD = "少林护寺·山门驱谍"
ORDINATION = "少林受戒·入室听经"
NOVICE_DAILY = "少林沙弥·日课初行"

TRAINING_GROUND = "shaolin_training_ground"
DHARMA_HALL = "shaolin_dharma_hall"
FRONT_COURT = "shaolin_front_court"


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


def make_shaolin_player(monkeypatch, name="少林任务线测试"):
    # 任务交付会正常写回游戏存档；测试显式使用临时存档，避免污染正式存档。
    monkeypatch.setattr(Player, "save_to_file", lambda self, filename=None: True)
    player = Player(name, "散人")
    player.level = 30
    ok, message = player.join_sect("少林")
    assert ok, message
    return player


def set_mastery(player, skill_name, mastery):
    state = player._ensure_skill_state()
    state.setdefault(skill_name, {"learned": True, "mastery": 0})
    state[skill_name]["learned"] = True
    state[skill_name]["mastery"] = mastery


def test_shaolin_questline_data_chain_is_complete_and_reachable():
    quests = read_data("quests.json")
    npcs = read_data("npcs.json")
    items = read_data("items.json")
    enemies = read_data("enemies.json")
    rooms = read_data("rooms.json")

    chain = [TRIAL, PATROL, DISCIPLINE, TEMPLE_GUARD, ORDINATION, NOVICE_DAILY]
    for quest in chain:
        assert quest in quests

    assert quests[PATROL]["requires"]["completed_quests"] == [TRIAL]
    assert quests[DISCIPLINE]["requires"]["completed_quests"] == [PATROL]
    assert quests[TEMPLE_GUARD]["requires"]["completed_quests"] == [DISCIPLINE]
    assert quests[ORDINATION]["requires"]["completed_quests"] == [TEMPLE_GUARD]
    assert quests[ORDINATION]["requires"]["level"] == 3
    assert quests[ORDINATION]["requires"]["sect_reputation"]["少林"]["gte"] == 20
    assert quests[ORDINATION]["requires"]["skills"]["罗汉拳"]["mastery"]["gte"] == 10
    assert quests[NOVICE_DAILY]["requires"]["completed_quests"] == [ORDINATION]
    assert quests[NOVICE_DAILY]["requires"]["flags"] == ["sect:shaolin:rank:1"]

    # 受戒奖励与晋升标记必须写入既有 world_state.flags，不新增存档顶层结构。
    assert quests[ORDINATION]["reward"]["effects"]["set_flags"][
        "sect:shaolin:ordination:novice"
    ] is True
    assert quests[TEMPLE_GUARD]["reward"]["item"] == "菩提念珠"
    assert items["菩提念珠"]["type"] == "accessory"

    for target in ("黑风寨精锐", "黑风寨刀阵头目"):
        assert target in enemies
    assert "少林传功师兄" in rooms[TRAINING_GROUND]["npcs"]
    assert "少林戒律僧" in rooms[DHARMA_HALL]["npcs"]
    assert "少林守山僧" in rooms["shaolin_gate"]["npcs"]
    assert "少林知客师兄" in rooms[FRONT_COURT]["npcs"]

    assert DISCIPLINE in npcs["少林传功师兄"]["quests"]
    assert TEMPLE_GUARD in npcs["少林戒律僧"]["quests"]
    assert ORDINATION in npcs["少林戒律僧"]["quests"]
    assert NOVICE_DAILY in npcs["少林传功师兄"]["quests"]


def test_shaolin_ordination_hall_is_enterable_by_entry_rank_monk():
    rooms = read_data("rooms.json")
    assert rooms[DHARMA_HALL]["access"]["sect"] == "少林"
    assert rooms[DHARMA_HALL]["access"]["min_rank_index"] == 0

    player = Player("少林讲经堂入门弟子", "散人")
    player.level = max(player.level, 3)
    assert player.join_sect("少林")[0]
    assert player.get_sect_official_rank_index("少林") == 0
    assert room_access_denial(player, rooms[DHARMA_HALL]) == ""

    guest = Player("少林讲经堂访客", "散人")
    guest.set_flag("sect:少林:guest_access", True)
    assert room_access_denial(guest, rooms[DHARMA_HALL])


def test_shaolin_questline_branch_ordination_promotion_and_daily_duty(
    tmp_path, monkeypatch
):
    # 在隔离任务完成自动存档之前保留真实存档方法，用于显式验证 V12 中途读档。
    real_save_to_file = Player.save_to_file
    player = make_shaolin_player(monkeypatch)

    # 前置历练：黑风除恶与巡山护戒。
    player.location = TRAINING_GROUND
    assert "已接取任务" in accept(player, TRIAL)
    for _ in range(2):
        capture(player.update_quest_progress, "黑风寨精锐", "kill")
    assert "奖励已结算" in deliver(player, TRIAL)

    assert "已接取任务" in accept(player, PATROL)
    for _ in range(2):
        capture(player.update_quest_progress, "黑风寨精锐", "kill")
    assert "奖励已结算" in deliver(player, PATROL)

    # 问心持戒：在罗汉场接取，前往讲经堂问心后必须真正选择一条持戒路线。
    set_mastery(player, "罗汉拳", 10)
    player.location = TRAINING_GROUND
    assert "已接取任务" in accept(player, DISCIPLINE)
    assert player.quest_states[DISCIPLINE]["stage"] == 0
    capture(player.update_quest_progress, "少林戒律僧", "talk")
    assert player.quest_states[DISCIPLINE].get("branch_pending") is True
    options = player.get_quest_branch_options(DISCIPLINE)
    assert [option["id"] for option in options] == ["precepts_first", "guard_first"]
    ok, message = player.choose_quest_branch(DISCIPLINE, "precepts_first")
    assert ok, message
    assert player.get_flag("sect:shaolin:discipline:precepts") is True
    assert player.quest_states[DISCIPLINE]["stage"] == 1

    for _ in range(2):
        capture(player.update_quest_progress, "黑风寨精锐", "kill")
    capture(player.update_quest_progress, "少林戒律僧", "talk")
    player.location = DHARMA_HALL
    assert "奖励已结算" in deliver(player, DISCIPLINE)
    assert player.get_flag("sect:shaolin:questline:discipline_done") is True

    # 护寺驱谍：山门问讯、驱逐巡哨、回讲经堂复命。
    assert "已接取任务" in accept(player, TEMPLE_GUARD)
    capture(player.update_quest_progress, "少林守山僧", "talk")
    for _ in range(2):
        capture(player.update_quest_progress, "黑风寨精锐", "kill")
    capture(player.update_quest_progress, "少林戒律僧", "talk")
    assert "奖励已结算" in deliver(player, TEMPLE_GUARD)
    assert "菩提念珠" in player.inventory
    assert player.get_flag("sect:shaolin:questline:temple_guard_done") is True

    # 受戒：先由传功师兄验看拳法，再回讲经堂完成入门受戒。
    assert "已接取任务" in accept(player, ORDINATION)
    capture(player.update_quest_progress, "少林传功师兄", "talk")

    # 中途存档/读档必须保留任务阶段与分支选择，且仍是 V12。
    mid_save = tmp_path / "shaolin_ordination_mid.json"
    assert real_save_to_file(player, str(mid_save))
    raw = json.loads(mid_save.read_text(encoding="utf-8"))
    assert raw["version"] == engine.SAVE_VERSION
    reloaded = Player.load_from_file(str(mid_save))
    assert reloaded is not None
    assert reloaded.quest_states[ORDINATION]["stage"] == 1
    player = reloaded
    player.location = DHARMA_HALL

    capture(player.update_quest_progress, "少林戒律僧", "talk")
    assert "奖励已结算" in deliver(player, ORDINATION)
    assert player.get_flag("sect:shaolin:ordination:novice") is True
    assert player.get_flag("sect:shaolin:questline:ordination_done") is True
    assert "清心散" in player.inventory

    # 受戒完成但尚未正式授阶时，沙弥日课不得提前解锁，提示不得泄露内部标记。
    player.location = TRAINING_GROUND
    locked = accept(player, NOVICE_DAILY)
    assert "接取失败" in locked
    assert "需先晋升为【少林·沙弥】" in locked
    assert "sect:shaolin:rank:1" not in locked

    ok, message = player.promote_sect_rank("少林")
    assert ok, message
    assert player.get_sect_official_rank_index("少林") == 1
    assert player.get_flag("sect:shaolin:rank:1") is True

    # 正式成为沙弥后，日课任务解锁并完成寺内三段日常。
    assert "已接取任务" in accept(player, NOVICE_DAILY)
    for target in ("少林戒律僧", "少林知客师兄", "少林传功师兄"):
        capture(player.update_quest_progress, target, "talk")
    assert "奖励已结算" in deliver(player, NOVICE_DAILY)
    assert player.get_flag("sect:shaolin:questline:novice_daily_done") is True
    assert NOVICE_DAILY in player.completed_quests

    final_save = tmp_path / "shaolin_questline_final.json"
    assert real_save_to_file(player, str(final_save))
    final_raw = json.loads(final_save.read_text(encoding="utf-8"))
    assert final_raw["version"] == engine.SAVE_VERSION
    restored = Player.load_from_file(str(final_save))
    assert restored is not None
    assert restored.get_sect_official_rank_index("少林") == 1
    assert restored.get_flag("sect:shaolin:ordination:novice") is True
    assert NOVICE_DAILY in restored.completed_quests


def test_locked_shaolin_quest_hints_are_natural_language(monkeypatch):
    player = make_shaolin_player(monkeypatch, name="少林锁定提示测试")
    player.completed_quests.extend([TRIAL, PATROL])
    player.location = DHARMA_HALL

    output = accept(player, ORDINATION)
    assert "接取失败" in output
    assert "门派【少林】声望需至少 20" in output
    assert "武学【罗汉拳】熟练度需至少 10" in output
    assert "sect:" not in output
    assert "gte" not in output
    assert ORDINATION not in player.active_quests
