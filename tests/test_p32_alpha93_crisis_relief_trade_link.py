import json
import unittest

from player import Player
from economy import EconomyManager


class Alpha93CrisisReliefTradeLinkTests(unittest.TestCase):
    def make_player(self, player_relief=0.0, npc_relief=0.0):
        p = Player("商路联动测试", "散人")
        p.world_state.setdefault("variables", {})["world_crises"] = {
            "north_route_robbery": {
                "id": "north_route_robbery",
                "title": "北境商路遭劫",
                "status": "active",
                "started_clock": 0,
                "expires_clock": 50,
                "effects": {"northfront_town": {"security": -10, "commerce": -16, "travel": -14}},
                "npc_relief": npc_relief,
                "player_relief": player_relief,
                "player_actions": 0,
            }
        }
        return p

    def test_player_relief_reduces_effective_caravan_travel_penalty(self):
        p = self.make_player(player_relief=0.44)
        p.tick_quest_clock(1)
        snapshot = p.economy_state["events"]["world_crises"]["northfront_town"]
        self.assertEqual(snapshot["travel_penalty"], 8)
        self.assertEqual(snapshot["relief_applied"], 0.44)

    def test_npc_relief_also_reduces_penalty_but_unrelieved_crisis_stays_severe(self):
        p_unrelieved = self.make_player()
        p_unrelieved.tick_quest_clock(1)
        self.assertEqual(p_unrelieved.economy_state["events"]["world_crises"]["northfront_town"]["travel_penalty"], 14)
        p_npc = self.make_player(npc_relief=0.36)
        p_npc.tick_quest_clock(1)
        self.assertEqual(p_npc.economy_state["events"]["world_crises"]["northfront_town"]["travel_penalty"], 9)

    def test_reduced_penalty_changes_actual_caravan_movement(self):
        def manager_for(penalty):
            manager = EconomyManager({
                "caravans": {"甲": {"position": 0, "gold": 500, "inventory": {}, "capacity": 8, "visits": 0}},
                "events": {"world_crises": {"danger_zone": {"id": "north_route_robbery", "title": "北境商路遭劫", "travel_penalty": penalty}}},
            })
            manager.caravan_config = {"甲": {"route": ["safe_stop", "danger_stop"], "gold": 500, "inventory": {}, "capacity": 8}}
            manager.resources = {}
            manager.recipes = {}
            manager.gatherers = {}
            manager.world_rooms = {"safe_stop": {"zone": "safe_zone"}, "danger_stop": {"zone": "danger_zone"}}
            return manager
        blocked = manager_for(14)
        relieved = manager_for(8)
        blocked.update(1)
        relieved.update(1)
        self.assertEqual(blocked.state.caravans["甲"]["position"], 0)
        self.assertEqual(relieved.state.caravans["甲"]["position"], 1)

    def test_state_remains_json_serializable_and_v12_compatible(self):
        import engine
        p = self.make_player(player_relief=0.22)
        p.tick_quest_clock(1)
        json.dumps(p.economy_state, ensure_ascii=False)
        self.assertEqual(engine.SAVE_VERSION, 12)


if __name__ == "__main__":
    unittest.main()
