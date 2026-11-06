"""Alpha51: validate produced goods can flow from NPC workshops into caravans."""
import json
import os
import unittest
from economy import EconomyManager

BASE = os.path.dirname(os.path.dirname(__file__))


class Alpha51NpcProductionCaravanLoopTests(unittest.TestCase):
    def test_medicine_recipe_declares_real_shop_and_trade_price(self):
        with open(os.path.join(BASE, "data", "economy", "recipes.json"), encoding="utf-8") as f:
            recipes = json.load(f)
        pharmacy = recipes["药铺老板"]
        self.assertEqual(pharmacy["room_id"], "medicine_shop")
        self.assertEqual(pharmacy["trade_prices"]["疗伤药"], 12)
        self.assertEqual(pharmacy["inputs"], {"草药": 3})
        self.assertEqual(pharmacy["outputs"], {"疗伤药": 1})

    def test_caravan_buys_only_real_pharmacy_stock_and_pays_npc(self):
        state = {
            "tick": 0,
            "npc_inventory": {"药铺老板": {"草药": 0, "疗伤药": 2}},
            "npc_gold": {"药铺老板": 100},
            "caravans": {
                "药材测试商队": {
                    "position": 0, "gold": 100, "capacity": 5,
                    "inventory": {}, "visits": 0,
                }
            },
        }
        manager = EconomyManager(state)
        manager.caravan_config = {
            "药材测试商队": {
                "route": ["village_square", "medicine_shop"],
                "gold": 100, "capacity": 5, "inventory": {},
                "sale_prices": {}, "buy_prices": {},
            }
        }
        manager.update(1)
        result = manager.export_state()
        caravan = result["caravans"]["药材测试商队"]
        # 该 Tick 到达药铺；购买量不得超过真实库存、资金或货舱容量。
        self.assertEqual(caravan["inventory"].get("疗伤药", 0), 2)
        self.assertEqual(result["npc_inventory"]["药铺老板"].get("疗伤药", 0), 0)
        self.assertEqual(caravan["gold"], 76)
        self.assertEqual(result["npc_gold"]["药铺老板"], 124)
        self.assertLessEqual(sum(caravan["inventory"].values()), caravan["capacity"])
        # 读档后交易结果保持一致，不会把已售出的药重新生成。
        resumed = EconomyManager(result).export_state()
        self.assertEqual(resumed["caravans"]["药材测试商队"]["inventory"]["疗伤药"], 2)
        self.assertEqual(resumed["npc_inventory"]["药铺老板"]["疗伤药"], 0)

    def test_caravan_does_not_buy_when_npc_has_no_product(self):
        state = {
            "npc_inventory": {"药铺老板": {"草药": 0, "疗伤药": 0}},
            "npc_gold": {"药铺老板": 100},
            "caravans": {"药材测试商队": {"position": 0, "gold": 100, "capacity": 5, "inventory": {}, "visits": 0}},
        }
        manager = EconomyManager(state)
        manager.caravan_config = {"药材测试商队": {"route": ["village_square", "medicine_shop"], "gold": 100, "capacity": 5, "inventory": {}}}
        manager.update(1)
        caravan = manager.export_state()["caravans"]["药材测试商队"]
        self.assertEqual(caravan["inventory"], {})
        self.assertEqual(caravan["gold"], 100)
        self.assertEqual(manager.state.npc_gold["药铺老板"], 100)


if __name__ == "__main__":
    unittest.main()
