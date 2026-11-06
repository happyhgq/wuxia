"""Alpha55：确保 NPC 竞争在每次世界 Tick 中只处理一次。"""
import unittest
from unittest.mock import patch
from player import Player


class Alpha55WorldTickDedupTests(unittest.TestCase):
    def test_npc_competitions_are_processed_once_per_world_tick(self):
        player = Player("测试侠客")
        with patch.object(player, "process_npc_competitions", wraps=player.process_npc_competitions) as process:
            player.tick_quest_clock(1)
        self.assertEqual(process.call_count, 1)

    def test_zero_step_does_not_duplicate_competition_processing(self):
        player = Player("测试侠客")
        with patch.object(player, "process_npc_competitions", wraps=player.process_npc_competitions) as process:
            player.tick_quest_clock(0)
        # 0 步仍会执行既有世界刷新入口，但竞争只在自主行动入口中评估一次。
        self.assertEqual(process.call_count, 1)


if __name__ == "__main__":
    unittest.main()
