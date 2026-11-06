"""Alpha55：新增门派与散人武学必须进入实际学习/战斗数据管线。"""
import json
import os
import unittest
import contextlib
import io
from actions import handle_talk_and_ask
from player import Player

BASE = os.path.dirname(os.path.dirname(__file__))


class Alpha55MartialContentTests(unittest.TestCase):
    def test_new_skills_are_referenced_by_their_sect_and_have_distinct_effects(self):
        with open(os.path.join(BASE, "data", "skills.json"), encoding="utf-8") as f:
            skills = json.load(f)
        with open(os.path.join(BASE, "data", "sects.json"), encoding="utf-8") as f:
            sects = json.load(f)
        expected = {
            "少林": ("金刚伏魔拳", "status"),
            "武当": ("两仪剑诀", "self_status"),
            "华山": ("破玉剑式", "combo"),
            "散人": ("行云流水掌", "self_status"),
        }
        for sect, (name, effect_type) in expected.items():
            rows = {row["name"]: row for row in skills[sect]}
            self.assertIn(name, rows)
            self.assertIn(name, sects[sect]["exclusive_skills"])
            self.assertEqual(rows[name]["effect"]["type"], effect_type)
            self.assertGreater(rows[name]["mp_cost"], 0)

    def test_player_skill_summary_includes_new_wuxia_moves(self):
        expected = {
            "少林": "金刚伏魔拳",
            "武当": "两仪剑诀",
            "华山": "破玉剑式",
            "散人": "行云流水掌",
        }
        for sect, skill_name in expected.items():
            player = Player("测试侠客", sect=sect)
            names = {row["name"] for row in player.get_skill_summary()}
            self.assertIn(skill_name, names)

    def test_trusted_martial_hall_relationship_unlocks_one_time_mentorship(self):
        player = Player("测试侠客")
        player.location = "guiyun_martial_hall"
        player.set_var("quest_clock", 5)
        player.change_relation("归云武馆馆主", 35)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            handle_talk_and_ask(player, ["归云武馆馆主"])
        self.assertTrue(player.get_flag("mentor:guiyun_martial_hall:lesson_received"))
        self.assertIn("练功札记", out.getvalue())
        self.assertIn("回内丹", player.inventory)
        first = (player.exp, player.gold, player.inventory.count("回内丹"))
        with contextlib.redirect_stdout(io.StringIO()):
            handle_talk_and_ask(player, ["归云武馆馆主"])
        self.assertEqual((player.exp, player.gold, player.inventory.count("回内丹")), first)

    def test_new_skill_effects_use_supported_combat_effect_types(self):
        supported = {"status", "self_status", "combo", "mp_restore"}
        with open(os.path.join(BASE, "data", "skills.json"), encoding="utf-8") as f:
            skills = json.load(f)
        for sect in ("少林", "武当", "华山", "散人"):
            for skill in skills[sect]:
                effect = skill.get("effect", {})
                if effect:
                    self.assertIn(effect.get("type"), supported)


if __name__ == "__main__":
    unittest.main()
