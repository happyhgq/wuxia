import unittest

from economy import EconomyManager
from player import Player


class Alpha92CaravanCrisisLinkTests(unittest.TestCase):
    def make_manager(self, penalty=18):
        manager = EconomyManager({
            "caravans": {"甲": {"position": 0, "gold": 500, "inventory": {}, "capacity": 8, "visits": 0}},
            "events": {
                "world_crises": {
                    "danger_zone": {"id": "north_route_robbery", "title": "北境商路遭劫", "travel_penalty": penalty}
                }
            },
        })
        manager.caravan_config = {"甲": {"route": ["safe_stop", "danger_stop"], "gold": 500, "inventory": {}, "capacity": 8}}
        manager.resources = {}
        manager.recipes = {}
        manager.gatherers = {}
        manager.world_rooms = {
            "safe_stop": {"zone": "safe_zone"},
            "danger_stop": {"zone": "danger_zone"},
        }
        return manager

    def test_severe_crisis_delays_caravan_and_announces_once(self):
        manager = self.make_manager(18)
        manager.update(1)  # tick 1 + one-character caravan name triggers deterministic delay
        caravan = manager.state.caravans["甲"]
        self.assertEqual(caravan["position"], 0)
        self.assertEqual(caravan["crisis_delayed_ticks"], 1)
        messages = manager.state.events.get("pending_world_announcements", [])
        self.assertEqual(sum("商路受阻" in message for message in messages), 1)
        manager.update(1)  # next tick resumes travel
        self.assertEqual(caravan["position"], 1)
        manager.update(1)
        messages = manager.state.events.get("pending_world_announcements", [])
        self.assertEqual(sum("商路受阻" in message for message in messages), 1)

    def test_mild_or_absent_crisis_does_not_delay_caravan(self):
        manager = self.make_manager(9)
        manager.update(1)
        self.assertEqual(manager.state.caravans["甲"]["position"], 1)
        self.assertNotIn("crisis_delayed_ticks", manager.state.caravans["甲"])

    def test_crisis_delay_state_is_json_serializable_for_v12_save(self):
        import json
        manager = self.make_manager(18)
        manager.update(1)
        payload = manager.export_state()
        self.assertEqual(json.loads(json.dumps(payload, ensure_ascii=False))["caravans"]["甲"]["crisis_delayed_ticks"], 1)

    def test_player_world_crisis_snapshot_reaches_economy_state(self):
        player = Player("联动测试", "散人")
        player.world_state.setdefault("variables", {})["world_crises"] = {
            "north_route_robbery": {
                "id": "north_route_robbery", "title": "北境商路遭劫", "status": "active",
                "expires_clock": 30,
                "effects": {"northfront_town": {"security": -10, "commerce": -16, "travel": -14}},
            }
        }
        player.tick_quest_clock(1)
        crisis_map = player.economy_state.get("events", {}).get("world_crises", {})
        self.assertEqual(crisis_map["northfront_town"]["travel_penalty"], 14)
        self.assertEqual(crisis_map["northfront_town"]["id"], "north_route_robbery")


if __name__ == "__main__":
    unittest.main()
