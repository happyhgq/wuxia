import unittest
from main import command_will_be_handled, expand_alias, handle_alias_command
from player import Player
from unittest.mock import patch


class CommandSafetyPhase3133Tests(unittest.TestCase):
    def test_unknown_command_is_rejected_before_clock_tick(self):
        p = Player("无效指令测试", "散人")
        room = {"exits": {"北": "room_north"}}
        before = p.get_var("quest_clock", 0)
        self.assertFalse(command_will_be_handled("not_a_real_command", room))
        # 主循环只会对 command_will_be_handled 返回 True 的命令推进任务时钟。
        self.assertEqual(p.get_var("quest_clock", 0), before)

    def test_real_direction_and_registered_commands_remain_valid(self):
        room = {"exits": {"北": "room_north"}}
        self.assertTrue(command_will_be_handled("n", room))
        self.assertTrue(command_will_be_handled("北", room))
        self.assertTrue(command_will_be_handled("look", room))
        self.assertFalse(command_will_be_handled("东", room))

    def test_official_command_has_priority_over_same_named_saved_alias(self):
        p = Player("命令优先级测试", "散人")
        p.set_var("command_aliases", {"看": "南;南;西", "自定义": "看"})
        self.assertEqual(expand_alias("看", p), "看")
        self.assertEqual(expand_alias("自定义", p), "看")

    def test_alias_definition_does_not_execute_embedded_chain(self):
        p = Player("别名定义安全测试", "散人")
        with patch("builtins.print"):
            handle_alias_command(p, ["安全回村", "=", "南;南;西"])
        self.assertEqual(p.get_var("command_aliases", {})["安全回村"], "南;南;西")


if __name__ == "__main__":
    unittest.main()
