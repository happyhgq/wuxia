import unittest
from player import Player


class Alpha185SectSkillGrowthGuardTests(unittest.TestCase):
    def test_left_sect_skill_mastery_does_not_grow_after_switch(self):
        p = Player("退门武学熟练度", "少林")
        before = p.get_skill_progress("罗汉拳")
        self.assertTrue(p.leave_sect()[0])
        self.assertTrue(p.join_sect("武当")[0])
        after = p.record_skill_use("罗汉拳")
        self.assertEqual(after["mastery"], before["mastery"])

    def test_current_sect_skill_mastery_still_grows(self):
        p = Player("本门武学熟练度", "武当")
        before = p.get_skill_progress("太极剑")
        after = p.record_skill_use("太极剑")
        self.assertGreater(after["mastery"], before["mastery"])

    def test_failed_skill_use_does_not_grow_mastery(self):
        p = Player("失败不涨熟练度", "华山")
        before = p.get_skill_progress("华山剑法")
        after = p.record_skill_use("华山剑法", success=False)
        self.assertEqual(after["mastery"], before["mastery"])


if __name__ == "__main__":
    unittest.main()
