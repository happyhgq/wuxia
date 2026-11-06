"""新人引导通过世界内人物与场景提供，不依赖强制弹窗。"""
import unittest

import engine
from player import Player
from main import show_first_entry_guide


class DiegeticOnboardingTests(unittest.TestCase):
    def test_newcomer_guide_and_notice_board_are_in_village_square(self):
        square = engine.ROOMS["village_square"]
        self.assertIn("青石村接引人", square.get("npcs", []))
        self.assertIn("公告栏", square.get("desc", ""))
        self.assertIn("接引人", square.get("desc", ""))

    def test_gate_guard_can_direct_player_to_guide_and_board(self):
        guard = engine.NPCS["守卫"]
        info = guard.get("info", {})
        self.assertIn("村中广场", info)
        self.assertIn("接引人", info)
        choices = guard.get("dialogue_choices", [])
        choice = next(row for row in choices if row.get("id") == "guard_guide_square")
        self.assertTrue({"村中广场", "接引人", "公告栏"}.intersection(choice.get("keywords", [])))

    def test_new_character_starts_as_roamer_without_forced_intro_popup(self):
        player = Player("初入江湖测试", "散人")
        self.assertEqual(player.location, "village_gate")
        self.assertEqual(player.sect if hasattr(player, "sect") else "散人", "散人")
        self.assertNotIn("p252_intro_seen", player.world_state.get("flags", {}))

    def test_legacy_intro_guide_hook_is_silent(self):
        import contextlib
        import io
        player = Player("兼容测试", "散人")
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            show_first_entry_guide(player)
        self.assertEqual(output.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
