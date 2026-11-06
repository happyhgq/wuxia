import unittest
from unittest.mock import patch

import engine
from region_activity import (
    record_criminal_defeat, record_patrol, extra_enemies,
    urban_crime_chance, urban_crime_enemies, process_crime_pressure,
    process_natural_recovery, get_region_delta, get_config,
)
from player import Player


class FakePlayer:
    def __init__(self, clock=0):
        self.world_state = {"variables": {}}
        self.clock = clock

    def get_quest_clock(self):
        return self.clock

    def get_region_ecology(self, zone=None):
        info = engine.WORLD_REGIONS.get(zone, {})
        base = (info.get("region_ecology", {}) or {}).get("security_base", 70)
        delta = get_region_delta(self, zone or "main")["security"]
        return {"security": max(0, min(100, int(base) + delta))}


class Alpha84RegionActivityTests(unittest.TestCase):
    def setUp(self):
        self.player = FakePlayer(100)

    def test_criminal_defeat_improves_security_and_trade_only_once_per_cooldown(self):
        room = next(k for k, v in engine.ROOMS.items() if v.get("zone") == "guiyun_city")
        result = record_criminal_defeat(self.player, room, "劫镖山贼", engine.ENEMIES.get("劫镖山贼"))
        self.assertTrue(result["applied"])
        self.assertEqual(result["security"], 2)
        self.assertEqual(get_region_delta(self.player, "guiyun_city")["security"], 2)
        repeated = record_criminal_defeat(self.player, room, "劫镖山贼", engine.ENEMIES.get("劫镖山贼"))
        self.assertFalse(repeated["applied"])
        self.player.clock += 24
        repeated = record_criminal_defeat(self.player, room, "劫镖山贼", engine.ENEMIES.get("劫镖山贼"))
        self.assertTrue(repeated["applied"])

    def test_wildlife_does_not_count_as_criminal_activity(self):
        room = next(k for k, v in engine.ROOMS.items() if v.get("zone") == "mistwood")
        result = record_criminal_defeat(self.player, room, "野狼", engine.ENEMIES.get("野狼"))
        self.assertFalse(result["applied"])
        self.assertEqual(get_region_delta(self.player, "mistwood")["security"], 0)

    def test_guard_patrol_contributes_with_cooldown(self):
        room = next(k for k, v in engine.ROOMS.items() if v.get("zone") == "guiyun_city")
        self.assertTrue(record_patrol(self.player, "捕头", room))
        self.assertFalse(record_patrol(self.player, "捕头", room))
        self.assertEqual(get_region_delta(self.player, "guiyun_city")["security"], 1)
        self.player.clock += 6
        self.assertTrue(record_patrol(self.player, "捕头", room))

    def test_low_security_unlocks_more_dangerous_local_enemy_pool(self):
        self.assertIn("山贼", extra_enemies("main", 50))
        self.assertIn("山贼二当家", extra_enemies("bandit_zone", 20))
        self.assertIn("黑市护卫", extra_enemies("guiyun_city", 20))
        self.assertEqual(extra_enemies("guiyun_city", 80), [])

    def test_street_crime_only_occurs_in_configured_city_streets_at_low_security(self):
        room = "guiyun_qiqu_lane_1"
        self.assertEqual(urban_crime_chance("guiyun_city", room, 60), 0.0)
        self.assertGreater(urban_crime_chance("guiyun_city", room, 20), 0.0)
        self.assertIn("小偷", urban_crime_enemies("guiyun_city", room, 20))
        self.assertEqual(urban_crime_enemies("main", room, 20), [])

    def test_sustained_crime_pressure_lowers_security_only_after_interval(self):
        room = next(k for k, v in engine.ROOMS.items() if v.get("zone") == "bandit_zone")
        self.player.world_state["variables"]["region_activity"] = {
            "bandit_zone": {"security": -10, "commerce": 0, "travel": 0, "events": {}, "last_crime_clock": 0}
        }
        # Fake the current value as low enough to activate pressure.
        with patch.object(self.player, "get_region_ecology", return_value={"security": 30}):
            self.player.clock = 11
            process_crime_pressure(self.player, self.player.clock)
            self.assertEqual(get_region_delta(self.player, "bandit_zone")["security"], -10)
            self.player.clock = 12
            process_crime_pressure(self.player, self.player.clock)
        self.assertEqual(get_region_delta(self.player, "bandit_zone")["security"], -11)


    def test_actual_npc_patrol_updates_region_security(self):
        player = Player()
        player.location = "village_gate"
        # tick 8 = 14:00，守卫按日程在村口值守；在岗巡逻只巡查四周，不擅离值守地点。
        player.set_var("quest_clock", 8)
        player.refresh_npc_schedules()
        before = player.get_region_ecology("main")["security"]
        action = player._execute_npc_autonomous_action("守卫", "patrol")
        self.assertEqual(action.get("action"), "patrol")
        self.assertEqual(action.get("to"), "village_gate")
        player.process_region_ecology()
        self.assertEqual(player.get_region_ecology("main")["security"], before + 1)

    def test_activity_configuration_references_existing_game_data(self):
        config = get_config()
        for name in config.get("criminal_enemies", {}):
            self.assertIn(name, engine.ENEMIES)
        for name in config.get("patrol_npcs", {}):
            self.assertIn(name, engine.NPCS)
        for zone, pools in config.get("extra_enemy_pools", {}).items():
            self.assertIn(zone, engine.WORLD_REGIONS)
            for pool in pools:
                for name in pool.get("enemies", []):
                    self.assertIn(name, engine.ENEMIES)
        for room in config.get("urban_crime", {}).get("rooms", []):
            self.assertIn(room, engine.ROOMS)

    def test_natural_recovery_is_slow_and_does_not_raise_above_base(self):
        self.player.world_state["variables"]["region_activity"] = {
            "main": {"security": -4, "commerce": 0, "travel": 0, "events": {}, "last_recovery": 0, "last_crime_clock": -999999}
        }
        self.player.clock = 24
        process_natural_recovery(self.player, self.player.clock)
        self.assertEqual(get_region_delta(self.player, "main")["security"], -3)


if __name__ == "__main__":
    unittest.main()
