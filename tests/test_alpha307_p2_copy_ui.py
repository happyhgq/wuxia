# -*- coding: utf-8 -*-
"""Alpha307 P2：天色天气取词、移动播报顺序与界面文案一致性。"""

import builtins
import contextlib
import io
from unittest.mock import patch

import actions
import engine
import main
import rewards
import world_ambience
from player import Player


def _phase_player(room, tick=2):
    player = Player("取词验收")
    player.location = room
    player.set_var("quest_clock", tick)
    world_ambience._state(player)["phase"] = "dawn"
    return player


# ==================== 天色与天气取词 ====================

def test_outdoor_phase_copy_does_not_assume_town_scenery():
    for text in world_ambience.PHASE_MESSAGES.values():
        assert "屋脊" not in text
        assert "街巷" not in text
        assert "更鼓" not in text
        assert "檐" not in text


def test_outdoor_phase_uses_weather_wording_only_when_clear_does_not_cover_it():
    player = _phase_player("village_gate")
    assert world_ambience._time_message(player, 2, "clear") == world_ambience.PHASE_MESSAGES["morning"]

    player = _phase_player("village_gate")
    assert world_ambience._time_message(player, 2, "rain") == world_ambience._WEATHER_PHASE_MESSAGES["rain"]["morning"]

    player = _phase_player("general_shop")
    assert world_ambience._time_message(player, 2, "rain") == world_ambience._INDOOR_PHASE_MESSAGES["morning"]


def test_outdoor_weather_transition_avoids_eaves_and_indoor_keeps_them():
    outdoor = _phase_player("village_gate")
    indoor = _phase_player("general_shop")
    assert world_ambience._weather_message(outdoor, "rain") == "细雨落了下来，四下很快有了水声。"
    assert world_ambience._weather_message(indoor, "rain") == "檐外传来细密的雨声。"


# ==================== 移动播报顺序 ====================

def test_movement_is_recognized_from_direction_alias_and_room_exit():
    gate = engine.ROOMS["village_gate"]
    assert main.is_movement_command("n", gate)
    assert main.is_movement_command("北", gate)
    assert main.is_movement_command("上楼", {"exits": {"上楼": "inn_upper"}})
    assert not main.is_movement_command("查看", gate)


def test_ambience_is_announced_after_arriving_at_destination():
    player = Player("播报顺序")
    player.location = "village_gate"
    seen = []

    def record_location(current, blocked=False, include_traffic=False):
        seen.append(current.location)
        return []

    with patch.object(main.os.path, "exists", return_value=True), \
         patch.object(main.Player, "load_from_file", return_value=player), \
         patch.object(main.Player, "save_to_file", lambda self, filename=None: True), \
         patch.object(builtins, "input", return_value="y"), \
         patch.object(main, "read_command", side_effect=["北", "退出"]), \
         patch.object(main, "clear_screen"), \
         patch.object(main, "look"), \
         patch.object(main, "announce_pending_npc_movement", side_effect=record_location), \
         patch.object(main, "announce_pending_caravan_arrivals"), \
         patch.object(main, "select_random_encounter", return_value=None), \
         contextlib.redirect_stdout(io.StringIO()):
        main.main()

    assert seen == ["village_south_street"]


# ==================== 文案与提示一致性 ====================

def test_enemy_list_uses_chinese_enumeration():
    player = Player("威胁显示")
    player.location = "wild_fields"
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        actions.look(player)
    threats = [line for line in output.getvalue().splitlines() if line.startswith("出没的威胁：")]
    assert threats
    assert "野狼、野猪" in threats[0]
    assert "野狼, 野猪" not in threats[0]


class _ShopPlayer:
    def __init__(self):
        self.location = "medicine_shop"
        self.economy_state = {}
        self.gold = 0

    def get_npcs_in_room(self, location):
        return ["药铺老板"]

    def get_npc_state(self, name):
        return "normal"


def test_shop_prompt_example_uses_chinese_verb():
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        assert actions.handle_trading(_ShopPlayer(), "buy", []) is False
    rendered = output.getvalue()
    assert "例如：购买 金创药 3。" in rendered
    assert "例如：buy" not in rendered


def test_equipment_upgrade_reports_full_width_scores_and_equip_hint():
    player = Player("装备提示")
    player.evaluate_equipment = lambda name: {
        "recommendation": "upgrade", "score": 90, "current_score": 60,
        "score_delta": 30, "build_before": {}, "build_after": {},
    }
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        result = rewards.apply_reward_bundle(player, {"item": "金创药"}, source="测试")
    assert result["ok"] is True
    rendered = output.getvalue()
    assert "（当前 60，+30）" in rendered
    assert "输入“装备 金创药”即可换上。" in rendered
