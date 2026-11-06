# -*- coding: utf-8 -*-
"""Alpha172：持续伤害击倒敌人时仍须完整结算战斗结果。"""
import unittest
from unittest.mock import patch

import combat
import engine
from player import Player


class DotVictorySettlementTests(unittest.TestCase):
    def setUp(self):
        engine.clear_statuses()

    def tearDown(self):
        engine.clear_statuses()

    def _enemy(self):
        return {
            "hp": 5, "atk": 1, "defense": 0, "exp": 3, "gold": 2,
            "hit": 0.0, "crit": 0.0, "dodge": 0.0,
            "skills": [], "drops": [], "tier": "normal",
        }

    def test_dot_kill_uses_full_victory_settlement(self):
        player = Player("持续伤害测试", "散人")
        player.location = "test_room"
        rewards = {"drops": [], "exp": 3, "gold": 2}
        with patch("world_lifecycle.entity_state", return_value=("alive", None)), \
             patch("world_lifecycle.record_death") as record_death, \
             patch("combat.get_enemy_profile", return_value=self._enemy()), \
             patch("combat.apply_world_combat_pressure", return_value=0), \
             patch("combat._enemy_combat_stats", return_value=(0.0, 0.0, 0.0)), \
             patch("combat._player_combat_stats", return_value=(0.0, 0.0, 0.0)), \
             patch("combat.process_status_effects", side_effect=[(0, False, []), (-5, False, ["中毒损失 5 点气血"])]), \
             patch("combat.resolve_enemy_rewards", return_value=rewards), \
             patch("rewards.apply_reward_bundle", return_value={"ok": True}) as apply_rewards, \
             patch.object(player, "update_quest_progress") as quest_progress, \
             patch.object(player, "save_to_file", return_value=True):
            combat.combat(player, "持续伤害测试敌人")

        apply_rewards.assert_called_once_with(player, rewards, source="战斗奖励")
        quest_progress.assert_called_once_with("持续伤害测试敌人")
        record_death.assert_called_once_with(player, "test_room", "持续伤害测试敌人", tier="normal", kind="enemy")

    def test_simultaneous_player_and_enemy_death_does_not_award_victory(self):
        player = Player("同时倒地测试", "散人")
        player.location = "test_room"
        with patch("world_lifecycle.entity_state", return_value=("alive", None)), \
             patch("combat.get_enemy_profile", return_value=self._enemy()), \
             patch("combat.apply_world_combat_pressure", return_value=0), \
             patch("combat._enemy_combat_stats", return_value=(0.0, 0.0, 0.0)), \
             patch("combat._player_combat_stats", return_value=(0.0, 0.0, 0.0)), \
             patch("combat.process_status_effects", side_effect=[(-player.hp, False, ["玩家倒地"]), (-5, False, ["敌人倒地"])]), \
             patch("combat._defeat_recovery", return_value="已恢复"), \
             patch("combat.resolve_enemy_rewards") as resolve_rewards, \
             patch.object(player, "save_to_file", return_value=True):
            combat.combat(player, "同时倒地敌人")

        resolve_rewards.assert_not_called()


if __name__ == "__main__":
    unittest.main()
