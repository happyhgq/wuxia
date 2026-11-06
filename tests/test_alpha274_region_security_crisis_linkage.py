"""Alpha274：区域治安、敌人刷新、官府巡逻与外部危机的联动一致性。"""
import time
import unittest
from unittest.mock import patch

import engine
import main
from player import Player
from region_activity import (
    extra_enemies, get_permanent_region_delta, get_region_delta, get_security_incident,
    process_natural_recovery, process_region_security_events, record_patrol,
)
from world_lifecycle import record_death


class _FakePlayer:
    def __init__(self, clock=100):
        self.world_state = {"variables": {}}
        self.clock = clock

    def get_quest_clock(self):
        return self.clock

    def get_region_ecology(self, zone=None):
        zone = zone or "main"
        base = (engine.WORLD_REGIONS[zone]["region_ecology"] or {}).get("security_base", 70)
        delta = get_region_delta(self, zone)["security"]
        return {"security": max(0, min(100, int(base) + delta))}


def _seed_region(player, zone="main", **rows):
    row = {
        "security": 0, "commerce": 0, "travel": 0,
        "events": {}, "last_recovery": 0, "last_crime_clock": -999999,
    }
    row.update(rows)
    player.world_state.setdefault("variables", {})["region_activity"] = {zone: row}
    return row


def _seed_crisis(player, zone="main", security=-20, expires=200):
    player.world_state.setdefault("variables", {})["world_crises"] = {
        "alpha274_test": {
            "id": "alpha274_test", "title": "测试局势", "status": "active",
            "started_clock": 0, "expires_clock": expires,
            "effects": {zone: {"security": security}},
            "npc_relief": 0.0, "player_relief": 0.0,
        }
    }


def _row(player, zone="main"):
    return player.world_state["variables"]["region_activity"][zone]


class Alpha274RegionSecurityCrisisLinkageTests(unittest.TestCase):
    def test_natural_recovery_does_not_turn_crisis_penalty_into_permanent_bonus(self):
        player = _FakePlayer(24)
        _seed_region(player, security=0)
        _seed_crisis(player, security=-20, expires=200)
        process_natural_recovery(player, 24)
        self.assertEqual(_row(player)["security"], 0)
        self.assertEqual(get_region_delta(player, "main")["security"], -20)

        _row(player)["security"] = -4
        _row(player)["last_recovery"] = 0
        process_natural_recovery(player, 24)
        self.assertEqual(_row(player)["security"], -3)
        self.assertEqual(get_region_delta(player, "main")["security"], -23)

    def test_patrol_bonus_cap_ignores_crisis_penalty(self):
        player = _FakePlayer(100)
        _seed_region(player, security=0)
        _seed_crisis(player, security=-20, expires=999)
        applied = 0
        for step in range(16):
            player.clock = 100 + step * 6
            if record_patrol(player, "守卫", "village_gate"):
                applied += 1
        self.assertEqual(applied, 15)
        self.assertEqual(_row(player)["security"], 15)
        self.assertEqual(get_region_delta(player, "main")["security"], -5)

    def test_patrol_cannot_complete_incident_after_deadline(self):
        player = _FakePlayer(100)
        _seed_region(player, security=-45, security_incident={
            "title": "青石村周边治安巡查", "status": "active",
            "started_clock": 80, "expires_clock": 100,
            "progress": 1, "required_patrols": 2, "contributors": [],
        })
        self.assertTrue(record_patrol(player, "守卫", "village_gate"))
        incident = get_security_incident(player, "main")
        self.assertEqual(incident["progress"], 1)
        self.assertEqual(incident["status"], "active")
        process_region_security_events(player, 100)
        self.assertEqual(get_security_incident(player, "main")["status"], "expired")

    def test_crisis_driven_low_security_starts_governance_incident(self):
        player = _FakePlayer(100)
        _seed_region(player, security=0)
        _seed_crisis(player, security=-40, expires=200)
        changed = process_region_security_events(player, 100)
        self.assertTrue(any(row.get("zone") == "main" and row.get("status") == "active" for row in changed))
        self.assertEqual(get_security_incident(player, "main")["status"], "active")

    def test_crisis_penalty_unlocks_extra_criminal_pool(self):
        player = _FakePlayer(100)
        _seed_region(player, security=0)
        _seed_crisis(player, security=-30, expires=200)
        base = int(engine.WORLD_REGIONS["main"]["region_ecology"]["security_base"])
        effective = max(0, min(100, base + get_region_delta(player, "main")["security"]))
        self.assertEqual(effective, 42)
        self.assertNotIn("山贼", extra_enemies("main", base))
        self.assertIn("山贼", extra_enemies("main", effective))

    def test_dead_ambush_enemy_does_not_respawn_immediately(self):
        player = Player("遭遇刷新验收", "散人")
        player.location = "alpha274_ambush_room"
        room = {"safe": False, "enemies": ["山贼"]}
        with patch("main.random.random", return_value=0.0), \
                patch("main.random.choice", side_effect=lambda rows: rows[0]):
            self.assertEqual(main.select_random_encounter(player, room, "main", 50, 100), "山贼")
            record_death(player, player.location, "山贼", now=time.time())
            self.assertIsNone(main.select_random_encounter(player, room, "main", 50, 100))

    def test_dead_street_criminal_is_not_selected_by_urban_encounter(self):
        player = Player("街头刷新验收", "散人")
        player.location = "guiyun_qiqu_lane_1"
        room = {"safe": True, "enemies": []}
        with patch("main.random.random", return_value=0.0), \
                patch("main.random.choice", side_effect=lambda rows: rows[0]):
            self.assertEqual(main.select_random_encounter(player, room, "guiyun_city", 20, 80), "小偷")
            record_death(player, player.location, "小偷", now=time.time())
            self.assertEqual(main.select_random_encounter(player, room, "guiyun_city", 20, 80), "流氓")
        for name in ("小偷", "流氓", "黑市打手"):
            record_death(player, player.location, name, now=time.time())
        with patch("main.random.random", return_value=0.0):
            self.assertIsNone(main.select_random_encounter(player, room, "guiyun_city", 20, 80))

    def test_permanent_delta_remains_clamped_and_matches_stored_state(self):
        player = _FakePlayer(100)
        _seed_region(player, security=-200)
        self.assertEqual(get_permanent_region_delta(player, "main")["security"], -60)
        _seed_crisis(player, security=-60, expires=200)
        self.assertEqual(get_region_delta(player, "main")["security"], -60)
        self.assertEqual(engine.SAVE_VERSION, 12)


if __name__ == "__main__":
    unittest.main()
