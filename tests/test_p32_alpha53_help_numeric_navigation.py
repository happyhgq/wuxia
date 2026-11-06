import contextlib
import io
import unittest

import help_system
from main import CMD_MAP, resolve_help_menu_input, next_help_navigation_state, show_help


class Alpha53HelpNumericNavigationTests(unittest.TestCase):
    def test_standalone_number_selects_category_from_top_menu(self):
        self.assertEqual(resolve_help_menu_input("1", "top"), "帮助 1")
        self.assertEqual(resolve_help_menu_input("5", "top"), "帮助 5")

    def test_standalone_number_selects_entry_from_category(self):
        self.assertEqual(resolve_help_menu_input("1", "category:view_move:1"), "帮助 1 1")
        self.assertEqual(resolve_help_menu_input("6", "category:system:1"), "帮助 13 6")

    def test_zero_returns_to_category_from_detail_page(self):
        self.assertEqual(resolve_help_menu_input("0", "detail:view_move:1"), "帮助 1 页1")
        self.assertEqual(next_help_navigation_state("help", ["1", "0"]), "category:view_move:1")

    def test_numbers_outside_help_navigation_remain_game_input(self):
        self.assertEqual(resolve_help_menu_input("1", None), "1")
        self.assertEqual(resolve_help_menu_input("1", ""), "1")

    def test_help_command_keeps_both_numeric_arguments(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            show_help("3 1")
        rendered = help_system._ANSI_RE.sub("", output.getvalue())
        self.assertIn("【任务】", rendered)
        self.assertIn("用途：", rendered)

    def test_advertised_common_shortcuts_are_registered(self):
        for alias in ("查", "图", "状", "包", "武", "任", "装", "商", "势", "局", "区", "存", "读", "退"):
            with self.subTest(alias=alias):
                self.assertIn(alias, CMD_MAP)

    def test_navigation_state_transitions(self):
        self.assertEqual(next_help_navigation_state("help", []), "top")
        self.assertEqual(next_help_navigation_state("help", ["0"]), "top")
        self.assertEqual(next_help_navigation_state("help", ["2"]), "category:talk_people:1")
        self.assertEqual(next_help_navigation_state("help", ["2", "2"]), "detail:talk_people:2")
        self.assertIsNone(next_help_navigation_state("look", []))
        self.assertEqual(next_help_navigation_state("help", ["采集"]), "detail:gather:3")

    def test_detail_numeric_hint_keeps_current_detail_state(self):
        resolved = resolve_help_menu_input("2", "detail:system:13")
        self.assertEqual(resolved, "帮助 __help_detail_hint__ system newbie")
        self.assertEqual(
            next_help_navigation_state("help", resolved.split()[1:]),
            "detail:system:13",
        )


if __name__ == "__main__":
    unittest.main()
