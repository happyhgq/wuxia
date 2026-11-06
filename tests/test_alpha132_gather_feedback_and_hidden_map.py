"""Alpha132: precise gathering failure feedback and hidden-exit map clues."""
import contextlib
import io
import unittest

import engine
from main import gather_search_failure_text, show_map, resolve_room_exit
from player import Player


class Alpha132GatherFeedbackTests(unittest.TestCase):
    def test_random_search_failure_does_not_claim_resource_is_depleted(self):
        message = gather_search_failure_text([])
        self.assertIn("这次没有找到", message)
        self.assertIn("仍可能有剩余资源", message)
        self.assertNotIn("已经采尽", message)

    def test_confirmed_depletion_uses_depleted_message(self):
        message = gather_search_failure_text(["雾露草", "雾露草"])
        self.assertIn("雾露草已经采尽", message)
        self.assertNotIn("仍可能有剩余资源", message)

    def test_hidden_exit_map_shows_clue_without_revealing_target_before_discovery(self):
        player = Player("测试侠客")
        player.location = "sunken_channel"
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            show_map(player)
        text = output.getvalue()
        self.assertIn("尚未查明的隐蔽线索", text)
        self.assertIn("输入“探索”调查", text)
        self.assertNotIn("沉河暗库", text)
        destination, message = resolve_room_exit(player, engine.ROOMS["sunken_channel"], "东")
        self.assertIsNone(destination)
        self.assertIn("先在地下暗渠输入", message)

    def test_hidden_exit_map_shows_destination_after_discovery(self):
        player = Player("测试侠客")
        player.location = "sunken_channel"
        player.set_flag("explore:sunken_channel:cache_found", True)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            show_map(player)
        text = output.getvalue()
        self.assertIn("已发现的隐蔽出口", text)
        self.assertIn("沉河暗库", text)
        self.assertNotIn("尚未查明的隐蔽线索", text)


if __name__ == "__main__":
    unittest.main()
