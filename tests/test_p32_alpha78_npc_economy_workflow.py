import unittest
from economy.manager import EconomyManager
from actions import _npc_economy_context


class Alpha78NpcEconomyWorkflowTests(unittest.TestCase):
    def test_real_maker_has_localized_rest_status_outside_work_hours(self):
        manager = EconomyManager({"tick": 20})
        status = manager.npc_work_status("百炼铁铺铁匠")
        self.assertEqual(status["status"], "已歇工")
        self.assertIn("时辰", status["detail"])

    def test_gatherer_full_stock_status_and_no_extra_harvest(self):
        manager = EconomyManager({"tick": 1, "npc_inventory": {"采药人阿芷": {"草药": 16}}})
        status = manager.npc_work_status("采药人阿芷")
        self.assertEqual(status["status"], "货物已满")
        before = manager.state.resources.get("mistwood_stream", {}).get("remaining", 20)
        manager.update(4)
        self.assertLessEqual(manager.state.npc_inventory["采药人阿芷"]["草药"], 16)
        self.assertLessEqual(manager.state.resources["mistwood_stream"]["remaining"], before)

    def test_recipe_without_work_hours_keeps_legacy_all_day_behavior(self):
        manager = EconomyManager({
            "npc_inventory": {"测试铁匠": {"铁矿石": 5}},
        })
        manager.recipes = {
            "测试铁匠": {"interval": 1, "inputs": {"铁矿石": 5}, "outputs": {"铁剑": 1}}
        }
        manager.update(1)
        self.assertEqual(manager.state.npc_inventory["测试铁匠"].get("铁剑"), 1)
        self.assertEqual(manager.state.npc_inventory["测试铁匠"].get("铁矿石"), 0)

    def test_maker_does_not_consume_inputs_outside_work_hours(self):
        manager = EconomyManager({
            "tick": 16,
            "npc_inventory": {"测试铁匠": {"铁矿石": 5}},
        })
        manager.recipes = {
            "测试铁匠": {"interval": 1, "work_hours": [7, 18],
                         "inputs": {"铁矿石": 5}, "outputs": {"铁剑": 1}}
        }
        manager.update(1)
        self.assertEqual(manager.state.npc_inventory["测试铁匠"].get("铁矿石"), 5)
        self.assertNotIn("铁剑", manager.state.npc_inventory["测试铁匠"])

    def test_dialogue_reports_real_gatherer_full_stock_without_fake_activity(self):
        state = {"tick": 1, "npc_inventory": {"采药人阿芷": {"草药": 16}}}
        text = _npc_economy_context("采药人阿芷", state, "mistwood_trail")
        self.assertIn("草药已存满", text)
        self.assertNotIn("采集了", text)

    def test_dialogue_reports_maker_waiting_for_material(self):
        state = {"npc_inventory": {"药铺老板": {"草药": 0, "疗伤药": 0}}}
        text = _npc_economy_context("药铺老板", state, "medicine_shop")
        self.assertTrue("草药不足" in text or "等待进货" in text)

    def test_maker_status_reports_missing_material(self):
        manager = EconomyManager({"npc_inventory": {"测试铁匠": {"铁矿石": 1}}})
        manager.recipes = {
            "测试铁匠": {"inputs": {"铁矿石": 5}, "outputs": {"铁剑": 1}}
        }
        status = manager.npc_work_status("测试铁匠")
        self.assertEqual(status["status"], "缺少原料")
        self.assertIn("铁矿石", status["detail"])


if __name__ == "__main__":
    unittest.main()
