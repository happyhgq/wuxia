import contextlib
import io
import unittest

import help_system
from main import CMD_MAP, show_help


class Alpha25HelpNavigationConsistencyTests(unittest.TestCase):
    def render(self, topic=None):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            show_help(topic)
        return help_system._ANSI_RE.sub("", out.getvalue())

    def test_zero_returns_to_top_menu(self):
        self.assertIn("江湖帮助", self.render("0"))
        self.assertIn("江湖帮助", self.render("返回"))

    def test_zero_after_category_returns_to_category(self):
        text = self.render("2 0")
        self.assertIn("【二 交谈与人物】", text)
        self.assertIn("【交谈】", text)

    def test_invalid_numeric_path_has_actionable_message(self):
        text = self.render("2 99")
        self.assertIn("帮助菜单编号无效", text)

    def test_gathering_help_only_advertises_registered_commands(self):
        text = self.render("8 2")
        self.assertIn("【搜索】", text)
        self.assertIn("用法：搜索", text)
        self.assertIn("发现当前场景可采集的资源", text)
        self.assertIn("获取已发现的草药等有限资源", self.render("8 3"))
        self.assertNotIn("用法：查看资源", text)
        for command in ("采集", "搜索", "伐木", "采矿"):
            self.assertIn(command, CMD_MAP)

    def test_common_interaction_commands_have_explanation_and_usage(self):
        for topic, command in [("穿戴", "穿戴"), ("使用", "使用"), ("比较", "比较"), ("查看", "看"), ("交谈", "交谈"), ("装备", "装备"), ("卸下", "卸下")]:
            with self.subTest(topic=topic):
                text = self.render(topic)
                self.assertIn("用途：", text)
                self.assertIn("用法：", text)
                self.assertIn(command, text)


if __name__ == "__main__":
    unittest.main()
