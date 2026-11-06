import unittest
from unittest.mock import patch

import engine
from player import Player
from region_activity import (
    get_region_delta, get_security_incident, process_region_security_events,
    record_patrol, get_config,
)


class FakePlayer:
    def __init__(self, clock=100):
        self.world_state = {"variables": {}}
        self.clock = clock

    def get_quest_clock(self):
        return self.clock

    def get_region_ecology(self, zone=None):
        zone = zone or "main"
        base = (engine.WORLD_REGIONS.get(zone, {}).get("region_ecology", {}) or {}).get("security_base", 70)
        delta = get_region_delta(self, zone)["security"]
        return {"security": max(0, min(100, int(base) + delta))}


class Alpha85SecurityEventTests(unittest.TestCase):
    def test_low_security_starts_configured_region_incident(self):
        player = FakePlayer()
        player.world_state["variables"]["region_activity"] = {
            "main": {"security": -45, "commerce": 0, "travel": 0, "events": {}}
        }
        started = process_region_security_events(player, 100)
        self.assertTrue(any(row.get("zone") == "main" and row.get("status") == "active" for row in started))
        incident = get_security_incident(player, "main")
        self.assertEqual(incident["status"], "active")
        self.assertEqual(incident["progress"], 0)

    def test_patrols_progress_and_complete_incident_once(self):
        player = FakePlayer()
        player.world_state["variables"]["region_activity"] = {
            "main": {
                "security": -45, "commerce": 0, "travel": 0,
                "events": {},
                "security_incident": {
                    "title": "青石村周边治安巡查", "status": "active",
                    "started_clock": 90, "expires_clock": 120,
                    "progress": 0, "required_patrols": 2, "contributors": [],
                },
            }
        }
        room = "village_gate"
        self.assertTrue(record_patrol(player, "守卫", room))
        self.assertEqual(get_security_incident(player, "main")["progress"], 1)
        player.clock += 6
        self.assertTrue(record_patrol(player, "守卫", room))
        incident = get_security_incident(player, "main")
        self.assertEqual(incident["status"], "completed")
        self.assertEqual(incident["progress"], 2)
        self.assertEqual(get_region_delta(player, "main")["security"], -41)
        self.assertEqual(get_region_delta(player, "main")["commerce"], 1)
        self.assertFalse(record_patrol(player, "守卫", room))

    def test_expired_incident_does_not_reward_security(self):
        player = FakePlayer(130)
        player.world_state["variables"]["region_activity"] = {
            "main": {
                "security": -45, "commerce": 0, "travel": 0,
                "events": {},
                "security_incident": {
                    "title": "青石村周边治安巡查", "status": "active",
                    "started_clock": 90, "expires_clock": 120,
                    "progress": 0, "required_patrols": 2, "contributors": [],
                },
            }
        }
        process_region_security_events(player, 130)
        incident = get_security_incident(player, "main")
        self.assertEqual(incident["status"], "expired")
        self.assertEqual(get_region_delta(player, "main")["security"], -45)

    def test_player_defeating_local_criminal_advances_active_security_incident(self):
        from region_activity import record_criminal_defeat
        player = FakePlayer(100)
        room = next(k for k, v in engine.ROOMS.items() if v.get("zone") == "main")
        player.world_state["variables"]["region_activity"] = {
            "main": {
                "security": -45, "commerce": 0, "travel": 0, "events": {},
                "security_incident": {
                    "title": "青石村周边治安巡查", "status": "active",
                    "started_clock": 90, "expires_clock": 120,
                    "progress": 0, "required_patrols": 2, "contributors": [],
                },
            }
        }
        result = record_criminal_defeat(player, room, "山贼", engine.ENEMIES.get("山贼"))
        self.assertTrue(result["applied"])
        self.assertTrue(result["incident_progressed"])
        self.assertEqual(get_security_incident(player, "main")["progress"], 1)

    def test_governance_command_displays_local_security_status(self):
        from unittest.mock import patch
        import actions
        player = Player()
        player.location = "village_gate"
        with patch("builtins.print") as output:
            actions.handle_security_governance(player, [])
        rendered = "\n".join(str(call.args[0]) for call in output.call_args_list if call.args)
        self.assertIn("地区治安治理", rendered)
        self.assertIn("安全度", rendered)

    def test_region_events_reference_existing_patrol_npcs(self):
        for zone, rule in get_config().get("security_events", {}).items():
            self.assertIn(zone, engine.WORLD_REGIONS)
            for npc in rule.get("patrol_npcs", []):
                self.assertIn(npc, engine.NPCS)

    def test_real_world_tick_can_start_security_event(self):
        player = Player()
        player.world_state.setdefault("variables", {}).setdefault("region_activity", {})["main"] = {
            "security": -50, "commerce": 0, "travel": 0, "events": {}
        }
        with patch.object(player, "get_quest_clock", return_value=100):
            player.process_region_ecology()
        incident = get_security_incident(player, "main")
        self.assertEqual(incident.get("status"), "active")


if __name__ == "__main__":
    unittest.main()
