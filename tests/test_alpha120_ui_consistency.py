import contextlib
import io
import unittest

from player import Player
from main import show_status
from actions import look
from ui_output import _ANSI_RE, wrap_player_text


class Alpha120UIConsistencyTests(unittest.TestCase):
    def test_wrap_uses_display_width_for_chinese(self):
        wrapped = wrap_player_text("青石村的道路旁边有一片茂密的树林，树林里可以采集草药。", width=24)
        lines = wrapped.splitlines()
        self.assertGreater(len(lines), 1)
        for line in lines:
            visible = _ANSI_RE.sub("", line)
            width = sum(2 if __import__("unicodedata").east_asian_width(ch) in ("W", "F") else 1 for ch in visible)
            self.assertLessEqual(width, 24)

    def test_wrap_preserves_color_controls_and_visible_text(self):
        original = "\x1b[32m可采集草药\x1b[0m"
        wrapped = wrap_player_text(original, width=24)
        self.assertIn("\x1b[32m", wrapped)
        self.assertIn("\x1b[0m", wrapped)
        self.assertEqual(_ANSI_RE.sub("", wrapped), "可采集草药")

    def test_status_has_consistent_reading_sections(self):
        player = Player("界面测试", "散人")
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            show_status(player)
        visible = _ANSI_RE.sub("", output.getvalue())
        self.assertIn("侠客状态", visible)
        self.assertIn("气血：", visible)
        self.assertIn("内力：", visible)
        self.assertNotIn("银两：", visible)
        details = io.StringIO()
        with contextlib.redirect_stdout(details):
            show_status(player, "combat")
        self.assertIn("身上状态：", _ANSI_RE.sub("", details.getvalue()))

    def test_scene_long_description_is_wrapped(self):
        player = Player("界面测试", "散人")
        player.location = "village_square"
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            look(player, None, True)
        visible = _ANSI_RE.sub("", output.getvalue())
        self.assertIn("【环境】", visible)
        self.assertIn("【下一步可以做什么】", visible)


if __name__ == "__main__":
    unittest.main()
