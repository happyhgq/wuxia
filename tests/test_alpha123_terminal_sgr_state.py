"""Alpha123：终端折行正确处理颜色的选择性复位。"""
import unittest

from ui_output import _ANSI_RE, wrap_player_text


class Alpha123TerminalSgrStateTests(unittest.TestCase):
    def test_foreground_reset_does_not_cancel_other_active_styles(self):
        text = "\x1b[1;31m红色加粗文字，先结束前景色\x1b[39m随后仍然加粗并继续很长的一段普通文字用于触发折行。\x1b[0m"
        wrapped = wrap_player_text(text, width=24)
        lines = wrapped.splitlines()
        self.assertGreater(len(lines), 1)
        # 选择性复位后续行不能重新染红，但仍应延续加粗样式。
        reset_index = next(i for i, line in enumerate(lines) if "\x1b[39m" in line)
        self.assertTrue(any("\x1b[1m" in line or "\x1b[1;" in line for line in lines[reset_index + 1:]))
        visible = _ANSI_RE.sub("", wrapped).replace("\n", "")
        self.assertEqual(visible, "红色加粗文字，先结束前景色随后仍然加粗并继续很长的一段普通文字用于触发折行。")

    def test_256_color_is_preserved_across_wrap(self):
        text = "\x1b[38;5;123m这是一段使用二百五十六色前景色的较长文本，折行后颜色仍然需要保持一致。\x1b[0m"
        lines = wrap_player_text(text, width=24).splitlines()
        self.assertGreater(len(lines), 1)
        self.assertTrue(all("38;5;123" in line for line in lines))
        self.assertEqual(_ANSI_RE.sub("", "\n".join(lines)).replace("\n", ""), "这是一段使用二百五十六色前景色的较长文本，折行后颜色仍然需要保持一致。")

    def test_selective_foreground_reset_is_not_reapplied_on_next_line(self):
        text = "\x1b[31m前景色文本\x1b[39m后续文字足够长以确保折行后不应再次启用红色前景色。\x1b[0m"
        lines = wrap_player_text(text, width=24).splitlines()
        reset_index = next(i for i, line in enumerate(lines) if "\x1b[39m" in line)
        self.assertTrue(all("\x1b[31m" not in line for line in lines[reset_index + 1:]))


if __name__ == "__main__":
    unittest.main()
