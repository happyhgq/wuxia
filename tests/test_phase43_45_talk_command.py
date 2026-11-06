import contextlib
import io
import json
import tempfile
import os
import unittest
from unittest.mock import patch

import engine
from actions import handle_talk_and_ask
from main import parse_command, command_will_be_handled
from player import Player


class TalkCommandResolutionTests(unittest.TestCase):
    def test_chinese_and_english_aliases_parse_to_talk(self):
        for raw in ("交谈 村长", "聊天 村长", "对话 村长", "打听 村长", "talk 村长", "chat 村长", "ask 村长", "t 村长"):
            with self.subTest(raw=raw):
                self.assertEqual(parse_command(raw), ("talk", ["村长"]))

    def test_talk_is_accepted_by_main_command_preflight(self):
        self.assertTrue(command_will_be_handled("talk", {"exits": {}}))

    def test_multi_token_npc_name_keeps_topic_separate(self):
        p = Player("交谈解析测试", "散人")
        p.location = "mistwood_stream"
        output = io.StringIO()
        # 模拟当前房间中存在该 NPC，确保测试聚焦于命令解析而不受动态巡逻影响。
        with patch.object(p, "get_npcs_in_room", return_value=["采药人阿芷"]), contextlib.redirect_stdout(output):
            handle_talk_and_ask(p, ["采药人", "阿芷", "雾露草"])
        rendered = output.getvalue()
        self.assertIn("雾隐溪谷岩缝间常有生长", rendered)
        self.assertNotIn("关于‘阿芷 雾露草’", rendered)
        self.assertGreaterEqual(p.get_talk_relation_gain("采药人阿芷"), 1)

    def test_full_name_and_topic_are_supported_in_one_argument(self):
        p = Player("交谈完整姓名测试", "散人")
        p.location = "mistwood_stream"
        output = io.StringIO()
        with patch.object(p, "get_npcs_in_room", return_value=["采药人阿芷"]), contextlib.redirect_stdout(output):
            handle_talk_and_ask(p, ["采药人阿芷", "雾露草"])
        self.assertIn("雾隐溪谷岩缝间常有生长", output.getvalue())

    def test_named_npc_outside_room_is_not_silently_retargeted(self):
        p = Player("交谈目标校验", "散人")
        p.location = "village_gate"
        before = p.get_relation("守卫")
        output = io.StringIO()
        with patch.object(p, "get_npcs_in_room", return_value=["守卫"]), contextlib.redirect_stdout(output):
            handle_talk_and_ask(p, ["村长", "安慰"])
        rendered = output.getvalue()
        self.assertIn("当前地点没有【村长】", rendered)
        self.assertNotIn("关于‘村长 安慰’", rendered)
        self.assertEqual(p.get_relation("守卫"), before)

    def test_unknown_location_has_clear_no_npc_response(self):
        p = Player("空房交谈测试", "散人")
        p.location = "village_head_house"
        output = io.StringIO()
        with patch.object(p, "get_npcs_in_room", return_value=[]), contextlib.redirect_stdout(output):
            handle_talk_and_ask(p, ["村长"])
        self.assertIn("此地空无一人", output.getvalue())

    def test_talk_command_does_not_change_save_schema(self):
        self.assertEqual(engine.SAVE_VERSION, 12)
        p = Player("交谈存档兼容测试", "散人")
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "save.json")
            with contextlib.redirect_stdout(io.StringIO()):
                p.save_to_file(path)
            with open(path, encoding="utf-8") as handle:
                raw = json.load(handle)
        self.assertEqual(raw.get("version"), 12)
        self.assertNotIn("dialogue_state", raw)


if __name__ == "__main__":
    unittest.main()
