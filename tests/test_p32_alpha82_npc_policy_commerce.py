import unittest
from world_lifecycle import (
    NPC_POLICY_PROTECTED, NPC_POLICY_RESPAWN, NPC_POLICY_NONE,
    npc_death_policy, record_npc_death, entity_state,
)
from economy.trade import TradeService


class FakePlayer:
    def __init__(self, commerce, location='mistwood_trail'):
        self.location = location
        self.economy_state = {'market': {'草药': {'supply': 20}}}
        self.commerce = commerce
    def get_region_ecology(self, zone=None):
        return {'commerce': self.commerce}


class Alpha82NpcPolicyCommerceTests(unittest.TestCase):
    def test_npc_defaults_to_protected(self):
        self.assertEqual(npc_death_policy({}), NPC_POLICY_PROTECTED)
        self.assertEqual(npc_death_policy({'quest_giver': True}), NPC_POLICY_PROTECTED)

    def test_only_explicit_respawn_npc_can_enter_lifecycle(self):
        p = type('P', (), {'world_state': {'variables': {}}})()
        ok, policy = record_npc_death(p, 'village_square', '村民甲', {}, now=100)
        self.assertFalse(ok)
        self.assertEqual(policy, NPC_POLICY_PROTECTED)
        self.assertEqual(entity_state(p, 'village_square', '村民甲', 'npc', now=101)[0], 'alive')
        ok, policy = record_npc_death(p, 'village_square', '巡路民兵', {'death_policy': 'respawn'}, now=100)
        self.assertTrue(ok)
        self.assertEqual(policy, NPC_POLICY_RESPAWN)
        self.assertEqual(entity_state(p, 'village_square', '巡路民兵', 'npc', now=101)[0], 'corpse')

    def test_explicit_no_respawn_policy_is_not_auto_recorded(self):
        p = type('P', (), {'world_state': {'variables': {}}})()
        ok, policy = record_npc_death(p, 'room', '剧情人物', {'death_policy': 'none'}, now=100)
        self.assertFalse(ok)
        self.assertEqual(policy, NPC_POLICY_NONE)

    def test_low_commerce_raises_prices_and_high_commerce_lowers_them(self):
        low = TradeService.market_price(FakePlayer(30), '草药', 100, 'buy')
        neutral = TradeService.market_price(FakePlayer(70), '草药', 100, 'buy')
        high = TradeService.market_price(FakePlayer(100), '草药', 100, 'buy')
        self.assertGreater(low, neutral)
        self.assertLess(high, neutral)

    def test_commerce_price_modifier_is_capped(self):
        low = TradeService.market_price(FakePlayer(-1000), '草药', 100, 'buy')
        high = TradeService.market_price(FakePlayer(1000), '草药', 100, 'buy')
        self.assertLessEqual(low, 115)
        self.assertGreaterEqual(high, 85)

if __name__ == '__main__':
    unittest.main()
