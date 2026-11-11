"""Alpha175：胜利结算入口具备幂等保护，避免重复发奖。"""
import unittest
from unittest.mock import patch

import combat
from player import Player
from world_lifecycle import entity_state


class DuplicateVictorySettlementTests(unittest.TestCase):
    def test_same_enemy_cannot_award_rewards_twice_during_corpse_period(self):
        player = Player("重复结算测试", "散人")
        player.location = "village_square"
        enemy = {"tier": "normal"}
        reward = {"exp": 3, "gold": 2, "drops": []}

        with patch("combat.resolve_enemy_rewards", return_value=reward), \
             patch("rewards.apply_reward_bundle", return_value={"ok": True}) as apply_rewards, \
             patch.object(player, "update_quest_progress") as quest_progress, \
             patch("region_activity.record_criminal_defeat", return_value={"applied": False}), \
             patch.object(player, "save_to_file") as save:
            combat._finish_combat_victory(player, "village_square", "测试敌人", enemy)
            self.assertEqual(entity_state(player, "village_square", "测试敌人")[0], "corpse")
            combat._finish_combat_victory(player, "village_square", "测试敌人", enemy)

        apply_rewards.assert_called_once_with(player, reward, source="战斗奖励")
        quest_progress.assert_called_once_with("测试敌人")
        save.assert_called_once()


if __name__ == "__main__":
    unittest.main()
