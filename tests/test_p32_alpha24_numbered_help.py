import contextlib
import io
import unittest

import help_system
from main import show_help


class Alpha24NumberedHelpTests(unittest.TestCase):
    def render(self, topic=None):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            show_help(topic)
        return help_system._ANSI_RE.sub("", out.getvalue())

    def test_top_menu_has_numbered_categories_only(self):
        text = self.render()
        for label, name in (("一", "查看与移动"), ("二", "交谈与人物"), ("十三", "系统与帮助")):
            self.assertIn(f"【{label}】{name}", text)
        self.assertNotIn("【看】", text)

    def test_numbered_path_opens_category_then_command_details(self):
        category = self.render("1")
        self.assertIn("【一 查看与移动】", category)
        self.assertIn("1【看】", category)
        detail = self.render("1 1")
        self.assertIn("【看】", detail)
        self.assertIn("用途：", detail)
        self.assertIn("用法：看 [对象名称]", detail)

    def test_gathering_details_use_uniform_format(self):
        for number in (3, 4, 5):
            text = self.render(f"8 {number}")
            self.assertIn("用途：", text)
            self.assertIn("用法：", text)
        self.assertIn("【采集】", self.render("8 3"))
        self.assertIn("【伐木】", self.render("8 4"))
        self.assertIn("【采矿】", self.render("8 5"))

    def test_direct_lookup_supports_interaction_commands(self):
        for topic, usage in [("穿戴", "用法：穿戴 物品名称"), ("使用", "用法：使用 物品名称"), ("比较", "用法：比较 物品名称"), ("交谈", "用法：交谈 人物名称")]:
            with self.subTest(topic=topic):
                text = self.render(topic)
                self.assertIn("用途：", text)
                self.assertIn(usage, text)

    def test_existing_named_help_and_alpha23_help_tests_remain_compatible(self):
        self.assertIn("竹影幽谷", self.render("采集"))
        self.assertIn("交谈与人物", self.render())


if __name__ == "__main__":
    unittest.main()
