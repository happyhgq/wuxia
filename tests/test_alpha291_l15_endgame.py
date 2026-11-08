# -*- coding: utf-8 -*-
"""Alpha291：L15 横向满级内容——夜行客、四门派终局委托、精铁回收与终局面板。"""
import contextlib
import io
import json
import re
import unicodedata
from pathlib import Path

import combat
import engine
import player as player_module
import world_lifecycle
from actions import handle_quest
from main import handle_status_panel_input, make_prompt, show_status
from player import Player

ROOT = Path(__file__).resolve().parents[1]

SECT_QUESTS = {
    "少林·伏魔护寺": {
        "npc": "少林戒律僧",
        "room": "shaolin_dharma_hall",
        "sect": "少林",
        "target": "断魂堡死卫",
        "count": 2,
    },
    "武当·夜巡断魂": {
        "npc": "武当执事弟子",
        "room": "wudang_outer_court",
        "sect": "武当",
        "target": "枯骨涧刀客",
        "count": 2,
    },
    "华山·绝壁试锋": {
        "npc": "华山授业师父",
        "room": "huashan_training_ground",
        "sect": "华山",
        "target": "断魂堡守卫长",
        "count": 1,
    },
    "铁衣门·断魂护镖": {
        "npc": "铁衣门护运执事",
        "room": "tieyi_outer_court",
        "sect": "铁衣门",
        "target": "断魂岭马贼",
        "count": 3,
    },
}

EXCHANGE_QUEST = "断魂岭·精铁换药"


def _data(name):
    return json.loads((ROOT / "data" / name).read_text(encoding="utf-8"))


def _capture(fn, *args):
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        result = fn(*args)
    return result, stream.getvalue()


def _ready_player(sect="少林", location="shaolin_dharma_hall", gold=100):
    player = Player("终局委托验收", sect)
    player.level = 15
    player.exp = 0
    player.exp_to_level = player_module.exp_needed_for_level(15)
    player.gold = gold
    player.location = location
    return player


def _deliver(player, name):
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        handle_quest(player, "jiaofu", [name])
    return output.getvalue()


def test_duanhun_iron_is_a_normal_material_with_exchange_hint():
    item = engine.ITEMS["断魂精铁"]
    assert item["type"] == "material"
    assert item["price"] == 40
    assert item["material"] == "精铁"
    assert "守岭猎户" in item["use_hint"]
    assert item["desc"] and item["craft_note"]


def test_guard_captain_is_a_second_deterministic_iron_source():
    """终局减负：堡门守卫长 60 秒刷新且必掉断魂精铁，与夜行客形成两条稳定来源。"""
    guard = engine.ENEMIES["断魂堡守卫长"]
    assert "断魂堡守卫长" in engine.ROOMS["duanhun_fort_gate"]["enemies"]
    assert guard.get("respawn_seconds") is None
    assert world_lifecycle.NORMAL_SECONDS == 60
    assert guard["level"] == 14 and guard["tier"] == "elite"

    iron = [drop for drop in guard["drops"] if drop["item"] == "断魂精铁"]
    assert len(iron) == 1
    assert iron[0]["chance"] == 1.0
    assert iron[0]["guaranteed"] is True
    for _ in range(5):
        rewards = combat.resolve_enemy_rewards(guard)
        assert {"item": "断魂精铁", "quantity": 1} in rewards["drops"]

    quest = engine.QUESTS[EXCHANGE_QUEST]
    assert "守卫长" in quest["follow_up_hint"]
    assert "守卫长" in engine.ITEMS["断魂精铁"]["desc"]


def test_night_walker_uses_l15_elite_template_and_low_frequency_respawn():
    enemy = engine.ENEMIES["断魂岭夜行客"]
    assert (enemy["hp"], enemy["atk"], enemy["defense"]) == (672, 70, 22)
    assert (enemy["exp"], enemy["gold"], enemy["level"], enemy["tier"]) == (396, 160, 15, "elite")
    assert enemy["respawn_seconds"] == 240
    assert 240 > world_lifecycle.NORMAL_SECONDS
    assert enemy["equipment_drop_chance"] == 0.05
    assert enemy["equipment"]["weapon"] in engine.ITEMS
    assert enemy["equipment"]["armor"] in engine.ITEMS

    drops = {drop["item"]: drop for drop in enemy["drops"]}
    assert drops["断魂精铁"]["chance"] == 1.0
    assert drops["断魂精铁"]["guaranteed"] is True
    for drop in enemy["drops"]:
        assert drop["item"] in engine.ITEMS

    rooms = engine.ROOMS
    assert "断魂岭夜行客" in rooms["duanhun_cliff"]["enemies"]
    profile = combat.get_enemy_profile("断魂岭夜行客", "duanhun_cliff")
    assert profile["level"] == 15
    assert profile["growth_levels"] == 0
    assert (profile["base_hp"], profile["base_atk"], profile["base_defense"], profile["exp"]) == (672, 70, 22, 396)
    assert profile["equipment_bonus"] == {"atk": 6, "defense": 4}
    assert (profile["hp"], profile["atk"], profile["defense"]) == (672, 76, 26)


def test_per_enemy_timers_override_defaults_without_touching_other_tiers():
    player = Player()
    world_lifecycle.record_death(
        player, "duanhun_cliff", "断魂岭夜行客", tier="elite", now=1000.0,
        respawn_seconds=240, corpse_seconds=30,
    )
    assert world_lifecycle.entity_state(player, "duanhun_cliff", "断魂岭夜行客", now=1029.9)[0] == "corpse"
    assert world_lifecycle.entity_state(player, "duanhun_cliff", "断魂岭夜行客", now=1030.0)[0] == "dead"
    assert world_lifecycle.entity_state(player, "duanhun_cliff", "断魂岭夜行客", now=1239.9)[0] == "dead"
    assert world_lifecycle.entity_state(player, "duanhun_cliff", "断魂岭夜行客", now=1240.0)[0] == "alive"

    world_lifecycle.record_death(player, "mistwood_trail", "山贼", tier="normal", now=0.0)
    assert world_lifecycle.entity_state(player, "mistwood_trail", "山贼", now=59.9)[0] == "corpse"
    assert world_lifecycle.entity_state(player, "mistwood_trail", "山贼", now=60.0)[0] == "alive"

    world_lifecycle.record_death(player, "bandit_zone", "山贼大当家", tier="boss", now=0.0)
    assert world_lifecycle.entity_state(player, "bandit_zone", "山贼大当家", now=299.9)[0] == "dead"
    assert world_lifecycle.entity_state(player, "bandit_zone", "山贼大当家", now=300.0)[0] == "alive"


def test_four_sect_quests_are_gated_l15_repeatables_without_permanent_repeat_growth():
    npcs = _data("npcs.json")
    for name, expected in SECT_QUESTS.items():
        quest = engine.QUESTS[name]
        assert quest["npc"] == expected["npc"]
        assert quest["turn_in_npc"] == expected["npc"]
        assert quest["target_type"] == "kill"
        assert quest["target_name"] == expected["target"]
        assert quest["required_cnt"] == expected["count"]
        assert quest["repeatable"] is True and quest["retryable"] is True
        assert quest["repeat_cooldown_ticks"] == 48
        assert quest["requires"] == {
            "sect": expected["sect"],
            "level": 15,
            "completed_quests": ["断魂岭·破堡除凶"],
        }
        assert quest["reward"] == {
            "exp": 260,
            "gold": 110,
            "items": [{"item": "断魂精铁", "quantity": 1}],
            "sect_reputation": {
                "少林": 8 if expected["sect"] == "少林" else -2,
                "武当": 8 if expected["sect"] == "武当" else -2,
                "华山": 8 if expected["sect"] == "华山" else -2,
                "铁衣门": 8 if expected["sect"] == "铁衣门" else -2,
            },
            "honor_delta": 1,
        }
        assert quest["on_complete"] == {
            "set_flags": {
                {
                    "少林": "world:sect_l15:shaolin",
                    "武当": "world:sect_l15:wudang",
                    "华山": "world:sect_l15:huashan",
                    "铁衣门": "world:sect_l15:tieyi",
                }[expected["sect"]]: True
            }
        }
        assert quest["repeat_reward"] == {
            "exp": 200,
            "gold": 90,
            "items": [{"item": "断魂精铁", "quantity": 1}],
        }
        assert set(quest["repeat_reward"]) == {"exp", "gold", "items"}
        assert name in npcs[expected["npc"]]["quests"]


def test_first_sect_completion_pays_reputation_and_honor_but_repeat_does_not(monkeypatch):
    monkeypatch.setattr(Player, "save_to_file", lambda self, filename=None: True)
    name = "少林·伏魔护寺"

    first = _ready_player()
    first.active_quests[name] = 2
    honor_before = first._jianghu_profile()["honor"]
    rep_before = first.get_sect_reputation("少林")
    output = _deliver(first, name)
    assert "恭喜完成任务" in output
    assert first.exp == 260
    assert first.gold == 210
    assert first.get_sect_reputation("少林") == rep_before + 8
    assert first._jianghu_profile()["honor"] == honor_before + 1
    assert first.inventory.count("断魂精铁") == 1
    assert name in first.completed_quests
    assert first.get_sect_reputation("武当") == -2
    assert first.get_flag("world:sect_l15:shaolin", False) is True
    assert "武当 门派声望 -2" in output

    repeat = _ready_player()
    repeat.completed_quests.append(name)
    repeat.set_var("quest_clock", 100)
    repeat.set_var(f"quest_repeat_last_completed:{name}", 40)
    repeat.active_quests[name] = 2
    honor_before = repeat._jianghu_profile()["honor"]
    rep_before = repeat.get_sect_reputation("少林")
    other_before = repeat.get_sect_reputation("武当")
    _deliver(repeat, name)
    assert repeat.exp == 200
    assert repeat.gold == 190
    assert repeat.inventory.count("断魂精铁") == 1
    assert repeat.get_sect_reputation("少林") == rep_before
    assert repeat.get_sect_reputation("武当") == other_before
    assert repeat._jianghu_profile()["honor"] == honor_before
    assert repeat.get_var(f"quest_repeat_last_completed:{name}") == repeat.get_quest_clock()


def test_iron_exchange_consumes_three_pieces_for_medicine_and_gold(monkeypatch):
    monkeypatch.setattr(Player, "save_to_file", lambda self, filename=None: True)
    quest = engine.QUESTS[EXCHANGE_QUEST]
    assert quest["target_type"] == "collect"
    assert quest["target_name"] == "断魂精铁"
    assert quest["required_cnt"] == 3
    assert quest["npc"] == quest["turn_in_npc"] == "守岭猎户"
    assert quest["requires"] == {"level": 15, "flags": ["quest_completed:断魂岭·破堡除凶"]}
    assert quest["reward"] == {"gold": 30, "item": "大还丹"}
    assert quest["repeat_reward"] == {"gold": 30, "item": "大还丹"}
    assert quest["repeat_cooldown_ticks"] == 12

    player = _ready_player(sect="散人", location="duanhun_camp")
    player.inventory = ["断魂精铁", "断魂精铁", "断魂精铁"]
    player.active_quests[EXCHANGE_QUEST] = 3
    output = _deliver(player, EXCHANGE_QUEST)
    assert "恭喜完成任务" in output
    assert player.gold == 130
    assert player.inventory.count("断魂精铁") == 0
    assert player.inventory.count("大还丹") == 1
    assert EXCHANGE_QUEST in player.completed_quests

    short = _ready_player(sect="散人", location="duanhun_camp")
    short.inventory = ["断魂精铁", "断魂精铁"]
    short.active_quests[EXCHANGE_QUEST] = 3
    output = _deliver(short, EXCHANGE_QUEST)
    assert "交付失败" in output
    assert short.inventory.count("断魂精铁") == 2
    assert EXCHANGE_QUEST in short.active_quests


def test_endgame_panel_reports_progress_without_mutating_player():
    player = Player("终局面板验收", "华山")
    player.level = 15
    player.completed_quests = ["少林·伏魔护寺", "武当·夜巡断魂"]
    player.inventory = ["断魂精铁", "断魂精铁", "断魂精铁", "断魂精铁"]
    player.world_state["flags"]["duanhun_ridge:fort_cleared"] = True
    snapshot = (list(player.completed_quests), list(player.inventory), dict(player.world_state["flags"]))

    _, output = _capture(show_status, player, "endgame")
    assert "========== 终局目标 ==========" in output
    assert "断魂堡：" in output and "已攻破，岭上残匪仍在" in output
    assert "门派终局委托：" in output and "已完成 2/4（复做冷却 48 刻）" in output
    assert "断魂精铁：" in output and "4 块（3 块可在守岭猎户处换大还丹）" in output
    assert "装备强化：" in output and "兵刃 +0 / 防具 +0" in output
    assert "已达设计上限，可继续积累经验" in output
    assert "L15 为当前内容封顶" not in output
    assert snapshot == (player.completed_quests, player.inventory, player.world_state["flags"])

    no_flag = Player("终局面板验收", "华山")
    _, output = _capture(show_status, no_flag, "endgame")
    assert "尚未攻破" in output
    assert "已完成 0/4" in output
    assert "0 块" in output
    assert "L15 为当前设计上限，达到后可继续积累经验" in output
    assert "已达设计上限" not in output


def test_endgame_panel_navigation_prompt_and_width():
    player = Player("一位姓名比较长的终局测试侠客", "少林")
    state, output = _capture(handle_status_panel_input, "5", player, "main")
    assert state == "endgame" and "终局目标" in output
    state, output = _capture(handle_status_panel_input, "0", player, "endgame")
    assert state == "main" and "侠客状态" in output

    assert make_prompt(player) == "> "
    assert make_prompt(player, "main") == "状态面板> "
    assert make_prompt(player, "endgame") == "状态面板/终局目标> "

    for panel in ("main", "endgame"):
        _, output = _capture(show_status, player, panel)
        for line in output.splitlines():
            visible = re.sub(r"\x1b\[[0-9;]*m", "", line)
            width = sum(2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1 for ch in visible)
            assert width <= 80, (panel, width, line)


def test_v12_roundtrip_preserves_l15_endgame_progress(tmp_path):
    player = Player("满级存档回归", "武当")
    player.level = 15
    player.exp = 120
    player.exp_to_level = player_module.exp_needed_for_level(15)
    player.location = "duanhun_cliff"
    player.inventory = ["断魂精铁", "断魂精铁", "断魂精铁"]
    player.active_quests = {"武当·夜巡断魂": 1}
    player.quest_states = {
        "武当·夜巡断魂": {"stage": 0, "progress": 1, "branch_pending": False, "accepted_at": 88}
    }
    player.completed_quests = ["少林·伏魔护寺"]
    player.world_state["flags"]["duanhun_ridge:fort_cleared"] = True
    player.set_var("quest_repeat_last_completed:少林·伏魔护寺", 64)

    path = tmp_path / "alpha291_endgame.json"
    assert player.save_to_file(str(path)) is True
    loaded = Player.load_from_file(str(path))
    assert loaded is not None
    assert engine.SAVE_VERSION == 12
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["version"] == 12
    assert loaded.level == 15
    assert loaded.location == "duanhun_cliff"
    assert loaded.inventory.count("断魂精铁") == 3
    assert loaded.active_quests == player.active_quests
    assert loaded.quest_states == player.quest_states
    assert loaded.completed_quests == player.completed_quests
    assert loaded.world_state["flags"]["duanhun_ridge:fort_cleared"] is True
    assert loaded.get_var("quest_repeat_last_completed:少林·伏魔护寺") == 64
