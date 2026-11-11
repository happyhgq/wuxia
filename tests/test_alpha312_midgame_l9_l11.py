# -*- coding: utf-8 -*-
"""Alpha312：L9–11 中段扩容（黑风后山守烽老卒、沉河堰口一线）。"""
import collections
import contextlib
import io
import json
from pathlib import Path

import combat
import engine
from actions import handle_explore, handle_quest, handle_talk_and_ask
from main import resolve_room_exit
from player import Player

ROOT = Path(__file__).resolve().parents[1]

DIRECTION_VECTORS = {"北": (0, 1), "南": (0, -1), "东": (1, 0), "西": (-1, 0)}

NEW_ROOMS = {
    "sunken_weir": ("沉河堰口", [3, 1], {"西": "sunken_cache", "北": "sunken_flume"}, ["沉河尸傀"], 9),
    "sunken_flume": ("沉河引水槽", [3, 2], {"南": "sunken_weir", "东": "sunken_sluice"}, ["遗祠守墓人"], 10),
    "sunken_sluice": ("沉河闸口", [4, 2], {"西": "sunken_flume"}, ["沉河尸傀"], 11),
}

NEW_QUESTS = {
    "黑风旧卒·外林查哨": ("守烽老卒", "kill", "黑风寨伏击手", 3),
    "沉河·捞药备伤": ("沉河捞尸人", "collect", "雾露草", 4),
    "沉河·闸口除傀": ("沉河捞尸人", "kill", "沉河尸傀", 3),
    "沉河·堰口除傀": ("沉河捞尸人", "kill", "沉河尸傀", 2),
}


def _data(name):
    return json.loads((ROOT / "data" / name).read_text(encoding="utf-8"))


def _capture(fn, *args, **kwargs):
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        result = fn(*args, **kwargs)
    return stream.getvalue(), result


def test_new_rooms_keep_vectors_and_extend_sunken_ruins():
    rooms = engine.ROOMS
    assert len(rooms) == 183
    for room_id, (name, coord, exits, enemies, level) in NEW_ROOMS.items():
        room = rooms[room_id]
        assert room["name"] == name
        assert room["zone"] == "sunken_ruins"
        assert room["coord"] == coord
        assert room["exits"] == exits
        assert room["enemies"] == enemies
        assert room["difficulty_level"] == level
        assert room["recommended_level"] == level
        assert room["indoor"] is True
        assert room["safe"] is False
        assert room["exploration_events"]
        for direction, target in exits.items():
            dx, dy = DIRECTION_VECTORS[direction]
            assert rooms[target]["coord"] == [coord[0] + dx, coord[1] + dy], (room_id, direction)

    assert rooms["sunken_weir"]["danger"] == "dangerous"
    assert rooms["sunken_flume"]["danger"] == "dangerous"
    assert rooms["sunken_sluice"]["danger"] == "high"
    assert rooms["sunken_weir"]["difficulty_label"] == "沉河堰口·凶险"
    assert rooms["sunken_flume"]["difficulty_label"] == "沉河引水槽·凶险"
    assert rooms["sunken_sluice"]["difficulty_label"] == "沉河闸口·极危"

    # 暗库东侧为隐蔽水道：暗库只保留西向常规出口，堰口西向回暗库。
    assert rooms["sunken_cache"]["exits"] == {"西": "sunken_channel"}
    assert rooms["sunken_cache"]["hidden_exits"]["东"]["target"] == "sunken_weir"
    assert rooms["sunken_weir"]["exits"]["西"] == "sunken_cache"


def test_new_rooms_are_reachable_through_normal_and_hidden_exits():
    rooms = engine.ROOMS
    seen = {"village_square"}
    queue = collections.deque(["village_square"])
    while queue:
        room_id = queue.popleft()
        targets = list(rooms[room_id].get("exits", {}).values())
        targets += [info["target"] for info in rooms[room_id].get("hidden_exits", {}).values()]
        for target in targets:
            if target in rooms and target not in seen:
                seen.add(target)
                queue.append(target)
    assert set(NEW_ROOMS) <= seen


def test_deep_water_exit_is_locked_until_cache_is_explored():
    player = Player("暗库探索验收", "散人")
    player.location = "sunken_cache"
    room = engine.ROOMS["sunken_cache"]

    destination, message = resolve_room_exit(player, room, "东")
    assert destination is None
    assert "先在沉河暗库输入“探索”" in message

    output, _ = _capture(handle_explore, player)
    assert "东侧低矮水道" in output
    assert player.get_flag("explore:sunken_cache:deep_found") is True

    destination, message = resolve_room_exit(player, engine.ROOMS["sunken_cache"], "东")
    assert (destination, message) == ("sunken_weir", "")


def test_new_npcs_are_placed_and_bound_to_the_new_quests():
    npcs = _data("npcs.json")
    rooms = engine.ROOMS
    assert len(npcs) == 81

    veteran = npcs["守烽老卒"]
    assert veteran["home_room"] == "bandit_back_mountain"
    assert rooms["bandit_back_mountain"]["npcs"] == ["守烽老卒"]
    assert veteran["quests"] == ["黑风旧卒·外林查哨"]
    assert veteran["schedule_tier"] == "T3"
    assert veteran["always_available"] is True
    assert veteran["talk_verb"] == "哑声道"
    assert veteran["conditional_dialogue"][0]["requires"]["flags"] == [
        "blackwind_backmountain:watch_cleared"
    ]
    for field in ("appearance", "voice", "demeanor", "behavior_hint", "scene_status"):
        assert veteran[field].strip(), field

    salvager = npcs["沉河捞尸人"]
    assert salvager["home_room"] == "sunken_weir"
    assert rooms["sunken_weir"]["npcs"] == ["沉河捞尸人"]
    assert salvager["quests"] == ["沉河·捞药备伤", "沉河·闸口除傀", "沉河·堰口除傀"]
    assert salvager["schedule_tier"] == "T3"
    assert salvager["always_available"] is True
    assert salvager["talk_verb"] == "闷声道"
    assert salvager["conditional_dialogue"][0]["requires"]["flags"] == ["sunken_ruins:sluice_closed"]
    for field in ("appearance", "voice", "demeanor", "behavior_hint", "scene_status"):
        assert salvager[field].strip(), field


def test_new_quests_are_configured_as_a_gated_l9_l11_chain():
    quests = _data("quests.json")
    assert len(quests) == 82
    for name, (npc, target_type, target_name, required_cnt) in NEW_QUESTS.items():
        quest = quests[name]
        assert quest["npc"] == npc
        assert quest["turn_in_npc"] == npc
        assert quest["target_type"] == target_type
        assert quest["target_name"] == target_name
        assert quest["required_cnt"] == required_cnt
        assert quest["notice_location"] == "天衡广场"
        assert quest["notice"]

    watch = quests["黑风旧卒·外林查哨"]
    assert watch["requires"] == {"level": 9}
    assert watch["difficulty"] == "进阶"
    assert watch["on_complete"]["set_flags"] == {"blackwind_backmountain:watch_cleared": True}

    herbs = quests["沉河·捞药备伤"]
    assert herbs["requires"]["level"] == 10
    assert herbs["requires"]["flags"] == [
        "sunken_ruins:caravan_truth_known",
        "explore:sunken_cache:deep_found",
    ]
    assert herbs["on_complete"] == {
        "set_flags": {"sunken_ruins:seal_recovered": True},
        "relations": {"沉河捞尸人": 3},
    }

    sluice = quests["沉河·闸口除傀"]
    assert sluice["requires"] == {"level": 11, "flags": ["sunken_ruins:seal_recovered"]}
    assert [stage["target_type"] for stage in sluice["stages"]] == ["kill", "talk"]
    assert sluice["on_complete"]["region_effects"] == {"sunken_ruins": {"security": 3, "travel": 2}}
    assert sluice["difficulty"] == "高难"

    repeat = quests["沉河·堰口除傀"]
    assert repeat["repeatable"] is True and repeat["retryable"] is True
    assert repeat["requires"] == {"level": 11, "flags": ["sunken_ruins:sluice_closed"]}
    assert repeat["repeat_cooldown_ticks"] == 12
    assert "exp" not in repeat["reward"] and "exp" not in repeat["repeat_reward"]
    assert "honor_delta" not in repeat["repeat_reward"]
    assert "on_complete" not in repeat


def test_watch_quest_turns_in_at_the_back_mountain_veteran():
    player = Player("外林查哨验收", "散人")
    player.level = 9
    player.location = "bandit_back_mountain"

    output, _ = _capture(handle_talk_and_ask, player, ["守烽老卒", "接受委托", "黑风旧卒·外林查哨"])
    assert "黑风旧卒·外林查哨" in player.active_quests
    assert "已接取任务" in output

    for _ in range(3):
        _capture(player.update_quest_progress, "黑风寨伏击手")
    gold_before = player.gold
    relation_before = player.get_relation("守烽老卒")
    _capture(handle_quest, player, "jiaofu", ["黑风旧卒·外林查哨"])

    assert "黑风旧卒·外林查哨" in player.completed_quests
    assert player.get_flag("blackwind_backmountain:watch_cleared") is True
    assert player.get_relation("守烽老卒") == relation_before + 3
    assert player.gold == gold_before + 90
    assert player.inventory.count("金创药") >= 2


def test_herb_quest_requires_both_story_flags_and_consumes_four_herbs():
    player = Player("沉河捞药验收", "散人")
    player.level = 10
    player.location = "sunken_weir"

    output, _ = _capture(handle_talk_and_ask, player, ["沉河捞尸人", "接受委托", "沉河·捞药备伤"])
    assert "暂时不能接取" in output
    assert "先查明沉河旧商队的真相" in output
    assert "沉河·捞药备伤" not in player.active_quests

    player.set_flag("sunken_ruins:caravan_truth_known", True)
    output, _ = _capture(handle_talk_and_ask, player, ["沉河捞尸人", "接受委托", "沉河·捞药备伤"])
    assert "暂时不能接取" in output
    assert "沉河·捞药备伤" not in player.active_quests

    player.set_flag("explore:sunken_cache:deep_found", True)
    _capture(handle_talk_and_ask, player, ["沉河捞尸人", "接受委托", "沉河·捞药备伤"])
    assert "沉河·捞药备伤" in player.active_quests

    for _ in range(4):
        _capture(player.update_quest_progress, "雾露草", event_type="collect")
    output, _ = _capture(handle_quest, player, "jiaofu", ["沉河·捞药备伤"])
    assert "交付失败" in output
    assert "沉河·捞药备伤" in player.active_quests

    player.inventory.extend(["雾露草"] * 4)
    gold_before = player.gold
    relation_before = player.get_relation("沉河捞尸人")
    _capture(handle_quest, player, "jiaofu", ["沉河·捞药备伤"])

    assert "沉河·捞药备伤" in player.completed_quests
    assert player.get_flag("sunken_ruins:seal_recovered") is True
    assert player.inventory.count("雾露草") == 0
    assert player.inventory.count("清心散") >= 1
    assert player.gold == gold_before + 70
    assert player.get_relation("沉河捞尸人") == relation_before + 3


def test_sluice_quest_needs_kill_stage_then_talk_stage_before_turn_in():
    player = Player("闸口除傀验收", "散人")
    player.level = 11
    player.location = "sunken_weir"
    player.set_flag("sunken_ruins:seal_recovered", True)

    _capture(handle_talk_and_ask, player, ["沉河捞尸人", "接受委托", "沉河·闸口除傀"])
    assert "沉河·闸口除傀" in player.active_quests

    for _ in range(3):
        _capture(player.update_quest_progress, "沉河尸傀")
    assert player.quest_states["沉河·闸口除傀"]["stage"] == 1
    output, _ = _capture(handle_quest, player, "jiaofu", ["沉河·闸口除傀"])
    assert "任务目标未全部达成" in output

    _capture(player.update_quest_progress, "沉河捞尸人", event_type="talk")
    gold_before = player.gold
    relation_before = player.get_relation("沉河捞尸人")
    _capture(handle_quest, player, "jiaofu", ["沉河·闸口除傀"])

    assert "沉河·闸口除傀" in player.completed_quests
    assert player.get_flag("sunken_ruins:sluice_closed") is True
    assert player.get_relation("沉河捞尸人") == relation_before + 4
    assert player.gold == gold_before + 110
    assert player.inventory.count("金创药") >= 2
    region = player.get_var("region_activity", {})["sunken_ruins"]
    assert region["security"] == 3
    assert region["travel"] == 2


def test_weir_commission_repeats_with_repeat_reward_after_cooldown():
    player = Player("堰口委托验收", "散人")
    player.level = 11
    player.location = "sunken_weir"
    player.set_flag("sunken_ruins:sluice_closed", True)

    _capture(handle_talk_and_ask, player, ["沉河捞尸人", "接受委托", "沉河·堰口除傀"])
    for _ in range(2):
        _capture(player.update_quest_progress, "沉河尸傀")
    gold_before = player.gold
    _capture(handle_quest, player, "jiaofu", ["沉河·堰口除傀"])
    assert player.gold == gold_before + 50
    assert "沉河·堰口除傀" in player.completed_quests

    output, _ = _capture(handle_talk_and_ask, player, ["沉河捞尸人", "接受委托", "沉河·堰口除傀"])
    assert "需再等待 12 个世界时刻" in output
    assert "沉河·堰口除傀" not in player.active_quests

    player.set_var(
        "quest_repeat_last_completed:沉河·堰口除傀",
        player.get_quest_clock() - 12,
    )
    _capture(handle_talk_and_ask, player, ["沉河捞尸人", "接受委托", "沉河·堰口除傀"])
    assert "沉河·堰口除傀" in player.active_quests

    for _ in range(2):
        _capture(player.update_quest_progress, "沉河尸傀")
    gold_before = player.gold
    exp_before = player.exp
    _capture(handle_quest, player, "jiaofu", ["沉河·堰口除傀"])
    assert player.gold == gold_before + 55
    assert player.exp == exp_before


def test_kill_quest_exp_matches_scaled_room_profiles():
    quests = _data("quests.json")
    for name, (enemy_name, room_id) in {
        "黑风旧卒·外林查哨": ("黑风寨伏击手", "bandit_outer_wood"),
        "沉河·闸口除傀": ("沉河尸傀", "sunken_sluice"),
    }.items():
        quest = quests[name]
        profile = combat.get_enemy_profile(enemy_name, room_id)
        ratio = quest["reward"]["exp"] / (profile["exp"] * quest["required_cnt"])
        assert 0.8 <= ratio <= 1.2, (name, ratio)


def test_total_quest_exp_includes_midgame_quests():
    quests = _data("quests.json")
    assert sum(info["reward"].get("exp", 0) for info in quests.values()) == 16114
