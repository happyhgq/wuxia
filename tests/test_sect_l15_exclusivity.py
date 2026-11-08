# -*- coding: utf-8 -*-
"""门派 L15 委托互斥后果：替本门出手会在别派留下小额负声望，退门转投不抹旧账。"""
import contextlib
import io
import json
from pathlib import Path

import engine
import player as player_module
from actions import handle_quest
from data_validator import main as validate_data
from player import Player

ROOT = Path(__file__).resolve().parents[1]

SECT_ORDER = ("少林", "武当", "华山", "铁衣门")

SECT_QUESTS = {
    "少林·伏魔护寺": ("少林", "shaolin", "shaolin_dharma_hall", 2),
    "武当·夜巡断魂": ("武当", "wudang", "wudang_outer_court", 2),
    "华山·绝壁试锋": ("华山", "huashan", "huashan_training_ground", 1),
    "铁衣门·断魂护镖": ("铁衣门", "tieyi", "tieyi_outer_court", 3),
}

FLAG_KEYS = {sect: f"world:sect_l15:{prefix}" for sect, prefix, _room, _cnt in SECT_QUESTS.values()}


def _ready_player(sect, location, name, count):
    player = Player("门派互斥验收", sect)
    player.level = 15
    player.exp = 0
    player.exp_to_level = player_module.exp_needed_for_level(15)
    player.gold = 100
    player.location = location
    player.active_quests[name] = count
    return player


def _deliver(player, name):
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        handle_quest(player, "jiaofu", [name])
    return output.getvalue()


def test_first_completion_costs_small_reputation_with_other_sects(monkeypatch):
    monkeypatch.setattr(Player, "save_to_file", lambda self, filename=None: True)
    for name, (sect, prefix, room, count) in SECT_QUESTS.items():
        player = _ready_player(sect, room, name, count)
        output = _deliver(player, name)

        assert "恭喜完成任务" in output, name
        assert player.get_sect_reputation(sect) == 8, name
        for other in SECT_ORDER:
            if other == sect:
                continue
            assert player.get_sect_reputation(other) == -2, (name, other)
            assert f"{other} 门派声望 -2" in output, (name, other)
        assert player.get_flag(FLAG_KEYS[sect], False) is True, name


def test_repeat_completion_keeps_cross_sect_reputation_frozen(monkeypatch):
    monkeypatch.setattr(Player, "save_to_file", lambda self, filename=None: True)
    name = "少林·伏魔护寺"
    sect, _prefix, room, count = SECT_QUESTS[name]
    player = _ready_player(sect, room, name, count)
    player.completed_quests.append(name)
    player.set_var("quest_clock", 100)
    player.set_var(f"quest_repeat_last_completed:{name}", 40)
    before = {sect_name: player.get_sect_reputation(sect_name) for sect_name in SECT_ORDER}

    output = _deliver(player, name)

    assert player.exp == 200 and player.gold == 190
    assert player.get_sect_reputation(sect) == before[sect]
    for other in SECT_ORDER:
        if other == sect:
            continue
        assert player.get_sect_reputation(other) == before[other], other
    assert "门派声望" not in output


def test_l15_repeat_rewards_stay_within_the_repeat_contract():
    for name, (sect, _prefix, _room, _count) in SECT_QUESTS.items():
        quest = engine.QUESTS[name]
        assert "region_effects" not in quest["repeat_reward"], name
        assert set(quest["repeat_reward"]) == {"exp", "gold", "items"}, name
        assert "sect_reputation" not in quest["repeat_reward"], name
        assert "honor_delta" not in quest["repeat_reward"], name
        assert list(quest["on_complete"]) == ["set_flags"], name
        assert list(quest["on_complete"]["set_flags"]) == [FLAG_KEYS[sect]], name


def test_leave_sect_warns_about_the_cross_sect_record():
    player = Player("退门旧账验收", "少林")
    player.set_flag(FLAG_KEYS["少林"], True)
    for other in SECT_ORDER:
        if other != "少林":
            player.change_sect_reputation(other, -2)

    ok, message = player.leave_sect()

    assert ok
    assert "替【少林】在断魂岭出手" in message
    assert "武当-2" in message and "华山-2" in message and "铁衣门-2" in message
    assert "转投他门时" in message and "一笔勾销" in message
    assert player.get_flag(FLAG_KEYS["少林"], False) is True

    untouched = Player("未替门派出手", "武当")
    untouched.change_sect_reputation("少林", -2)
    ok, message = untouched.leave_sect()
    assert ok
    assert "旧账" not in message


def test_joining_another_sect_keeps_negative_standing_narrative():
    player = Player("转投验收", "少林")
    player.level = 15
    player.set_flag(FLAG_KEYS["少林"], True)
    player.change_sect_reputation("武当", -2)
    assert player.leave_sect()[0]

    ok, message = player.join_sect("武当")

    assert ok
    assert "武当对你的声望为 -2" in message
    assert "修复这段嫌隙" in message

    clean = Player("无旧账转投", "散人")
    clean.level = 15
    ok, message = clean.join_sect("武当")
    assert ok
    assert "旧档" not in message


def test_switching_sects_accumulates_costs_but_never_resets_them(monkeypatch):
    monkeypatch.setattr(Player, "save_to_file", lambda self, filename=None: True)
    player = Player("连投两门验收", "少林")
    player.level = 15
    player.exp = 0
    player.exp_to_level = player_module.exp_needed_for_level(15)
    player.gold = 100
    player.location = "shaolin_dharma_hall"
    player.active_quests["少林·伏魔护寺"] = 2
    assert "恭喜完成任务" in _deliver(player, "少林·伏魔护寺")

    assert player.leave_sect()[0]
    assert player.join_sect("武当")[0]
    player.location = "wudang_outer_court"
    player.active_quests["武当·夜巡断魂"] = 2
    assert "恭喜完成任务" in _deliver(player, "武当·夜巡断魂")

    assert player.get_sect_reputation("少林") == 6
    assert player.get_sect_reputation("武当") == 6
    assert player.get_sect_reputation("华山") == -4
    assert player.get_sect_reputation("铁衣门") == -4
    assert player.get_flag(FLAG_KEYS["少林"], False) is True
    assert player.get_flag(FLAG_KEYS["武当"], False) is True


def test_v12_roundtrip_preserves_stance_flags_and_cross_sect_reputation(tmp_path):
    player = Player("门派旧账存档", "散人")
    player.set_flag(FLAG_KEYS["少林"], True)
    player.set_flag(FLAG_KEYS["武当"], True)
    player.change_sect_reputation("少林", 6)
    player.change_sect_reputation("武当", 6)
    player.change_sect_reputation("华山", -4)
    player.change_sect_reputation("铁衣门", -4)

    path = tmp_path / "sect_l15_exclusivity.json"
    assert player.save_to_file(str(path)) is True
    loaded = Player.load_from_file(str(path))

    assert loaded is not None
    assert engine.SAVE_VERSION == 12
    assert json.loads(path.read_text(encoding="utf-8"))["version"] == 12
    assert loaded.get_flag(FLAG_KEYS["少林"], False) is True
    assert loaded.get_flag(FLAG_KEYS["武当"], False) is True
    assert loaded.get_sect_reputation("少林") == 6
    assert loaded.get_sect_reputation("武当") == 6
    assert loaded.get_sect_reputation("华山") == -4
    assert loaded.get_sect_reputation("铁衣门") == -4


def test_data_validator_accepts_cross_sect_penalties():
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        result = validate_data()
    assert result == 0, output.getvalue()
    assert "DATA VALIDATION: PASS" in output.getvalue()
