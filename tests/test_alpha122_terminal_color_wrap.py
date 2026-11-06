"""Alpha122：终端长文本折行后，颜色与可见内容保持一致。"""
import unicodedata
import unittest

from ui_output import _ANSI_RE, wrap_player_text


class Alpha122TerminalColorWrapTests(unittest.TestCase):
    def test_wrapped_continuation_reapplies_active_color(self):
        text = "\x1b[32m青石村的道路旁边有一片茂密的树林，树林里可以采集草药。\x1b[0m"
        wrapped = wrap_player_text(text, width=24)
        lines = wrapped.splitlines()
        self.assertGreater(len(lines), 1)
        self.assertTrue(all("\x1b[32m" in line for line in lines))
        self.assertIn("\x1b[0m", lines[-1])
        self.assertEqual(_ANSI_RE.sub("", wrapped).replace("\n", ""), "青石村的道路旁边有一片茂密的树林，树林里可以采集草药。")

    def test_wrapped_lines_respect_display_width(self):
        wrapped = wrap_player_text("\x1b[36m青石村南门外的长街入口与天衡广场相连，沿途可见商旅和行人。\x1b[0m", width=24)
        for line in wrapped.splitlines():
            visible = _ANSI_RE.sub("", line)
            width = sum(2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1 for ch in visible)
            self.assertLessEqual(width, 24)

    def test_uncolored_text_stays_uncolored(self):
        wrapped = wrap_player_text("这是一段普通说明文字，用于检查折行后不会凭空出现颜色。", width=24)
        self.assertNotIn("\x1b[", wrapped)
        self.assertEqual(_ANSI_RE.sub("", wrapped).replace("\n", ""), "这是一段普通说明文字，用于检查折行后不会凭空出现颜色。")


if __name__ == "__main__":
    unittest.main()
