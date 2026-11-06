import unittest
from unittest.mock import patch

from economy.manager import EconomyManager
from world_lifecycle import record_death, entity_state, visible_enemies, calculate_encounter_chance, random_encounter_candidates


class FakePlayer:
    def __init__(self):
        self.world_state = {"variables": {}}


class Alpha81LifecycleTests(unittest.TestCase):
    def test_resource_regeneration_uses_per_unit_real_time_due_dates(self):
        manager = EconomyManager({"resources": {"wild_fields": {"remaining": 3, "last_tick": 0}}}, real_time_regen=True)
        manager.gatherers = {}
        manager.recipes = {}
        manager.caravan_config = {}
        with patch("economy.manager.time.time", return_value=1000.0):
            ok, result = manager.gather("wild_fields", 1)
        self.assertTrue(ok)
        self.assertEqual(result, ("草药", 1))
        row = manager.state.resources["wild_fields"]
        self.assertEqual(row["remaining"], 2)
        self.assertEqual(row["regen_due"], [1030.0])
        with patch("economy.manager.time.time", return_value=1029.0):
            manager.update(1)
        self.assertEqual(row["remaining"], 2)
        with patch("economy.manager.time.time", return_value=1030.0):
            manager.update(1)
        self.assertEqual(row["remaining"], 3)
        self.assertEqual(row["regen_due"], [])

    def test_later_harvest_does_not_reset_earlier_due_time(self):
        manager = EconomyManager({"resources": {"wild_fields": {"remaining": 3, "last_tick": 0}}}, real_time_regen=True)
        manager.gatherers = {}; manager.recipes = {}; manager.caravan_config = {}
        with patch("economy.manager.time.time", return_value=100.0):
            manager.gather("wild_fields", 1)
        with patch("economy.manager.time.time", return_value=110.0):
            manager.gather("wild_fields", 1)
        due = manager.state.resources["wild_fields"]["regen_due"]
        self.assertEqual(due, [130.0, 140.0])
        with patch("economy.manager.time.time", return_value=130.0):
            manager.update(1)
        self.assertEqual(manager.state.resources["wild_fields"]["remaining"], 2)
        self.assertEqual(manager.state.resources["wild_fields"]["regen_due"], [140.0])

    def test_enemy_corpse_and_respawn_use_death_event_time(self):
        player = FakePlayer()
        record_death(player, "mistwood_trail", "山贼", tier="normal", now=100.0)
        self.assertEqual(entity_state(player, "mistwood_trail", "山贼", now=100.5)[0], "corpse")
        alive, corpses = visible_enemies(player, "mistwood_trail", ["山贼"], now=100.5)
        self.assertEqual(alive, [])
        self.assertEqual(corpses[0]["name"], "山贼")
        self.assertEqual(entity_state(player, "mistwood_trail", "山贼", now=160.0)[0], "alive")

    def test_boss_has_five_minute_respawn_timer(self):
        player = FakePlayer()
        record_death(player, "bandit_zone", "山贼大当家", tier="boss", now=50.0)
        self.assertEqual(entity_state(player, "bandit_zone", "山贼大当家", now=169.9)[0], "corpse")
        self.assertEqual(entity_state(player, "bandit_zone", "山贼大当家", now=349.9)[0], "dead")
        self.assertEqual(entity_state(player, "bandit_zone", "山贼大当家", now=350.0)[0], "alive")

    def test_security_and_travel_affect_encounter_chance(self):
        calm = calculate_encounter_chance(90, 90)
        ordinary = calculate_encounter_chance(70, 70)
        dangerous = calculate_encounter_chance(20, 20)
        extreme = calculate_encounter_chance(0, 0)
        self.assertLess(calm, ordinary)
        self.assertLess(ordinary, dangerous)
        self.assertLessEqual(calm, 0.10)
        self.assertGreaterEqual(calm, 0.05)
        self.assertLessEqual(extreme, 0.45)

    def test_random_encounters_do_not_pick_boss_when_regular_enemy_is_present(self):
        enemies = {
            "山贼": {"tier": "normal"},
            "山贼二当家": {"tier": "boss"},
            "山贼大当家": {"tier": "boss"},
        }
        self.assertEqual(random_encounter_candidates(list(enemies), enemies), ["山贼"])

    def test_single_boss_room_remains_encounterable(self):
        enemies = {"山贼大当家": {"tier": "boss"}}
        self.assertEqual(random_encounter_candidates(["山贼大当家"], enemies), ["山贼大当家"])

    def test_multi_boss_room_does_not_force_random_boss_encounter(self):
        enemies = {"山贼二当家": {"tier": "boss"}, "山贼大当家": {"tier": "boss"}}
        self.assertEqual(random_encounter_candidates(list(enemies), enemies), [])


if __name__ == "__main__":
    unittest.main()
