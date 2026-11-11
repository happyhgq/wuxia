"""Alpha174：战斗奖励结算失败时，不提交永久战斗结果。"""
import unittest
from unittest.mock import patch

import combat
import engine
from player import Player


class CombatRewardFailureAtomicityTests(unittest.TestCase):
    def setUp(self):
        engine.clear_statuses()

    def tearDown(self):
        engine.clear_statuses()

    def test_failed_reward_does_not_commit_death_or_quest_progress(self):
        player = Player("奖励失败测试", "散人")
        player.location = "test_room"
        enemy_data = {"tier": "elite"}
        with patch("world_lifecycle.record_death") as record_death, \
             patch("rewards.apply_reward_bundle", return_value={"ok": False, "message": "invalid"}), \
             patch.object(player, "update_quest_progress") as quest_progress, \
             patch("region_activity.record_criminal_defeat") as criminal_defeat, \
             patch.object(player, "save_to_file") as save:
            combat._finish_combat_victory(player, "test_room", "测试敌人", enemy_data)
        record_death.assert_not_called()
        quest_progress.assert_not_called()
        criminal_defeat.assert_not_called()
        save.assert_not_called()

    def test_successful_reward_commits_death_quest_and_save(self):
        player = Player("奖励成功测试", "散人")
        player.location = "village_square"
        enemy_data = {"tier": "normal"}
        with patch("world_lifecycle.record_death") as record_death, \
             patch("rewards.apply_reward_bundle", return_value={"ok": True}), \
             patch.object(player, "update_quest_progress") as quest_progress, \
             patch("region_activity.record_criminal_defeat", return_value={"applied": False}), \
             patch.object(player, "save_to_file") as save:
            combat._finish_combat_victory(player, "village_square", "测试敌人", enemy_data)
        record_death.assert_called_once_with(player, "village_square", "测试敌人", tier="normal", kind="enemy")
        quest_progress.assert_called_once_with("测试敌人")
        save.assert_called_once()


if __name__ == "__main__":
    unittest.main()
