from unittest.mock import patch

from economy.manager import EconomyManager


def _quiet_manager(state):
    manager = EconomyManager(state, real_time_regen=True)
    manager.gatherers = {}
    manager.recipes = {}
    manager.caravan_config = {}
    return manager


def test_resource_regen_pauses_while_player_remains_in_resource_room():
    manager = _quiet_manager({
        "resources": {
            "wild_fields": {
                "remaining": 2,
                "last_tick": 0,
                "regen_due": [120.0],
                "regen_check_at": 100.0,
            }
        },
        "events": {"last_player_location": "wild_fields"},
    })
    with patch("economy.manager.time.time", return_value=130.0):
        manager.update(1, player_location="wild_fields")
    row = manager.state.resources["wild_fields"]
    assert row["remaining"] == 2
    assert row["regen_due"] == [150.0]


def test_resource_regen_counts_from_leaving_room_not_while_staying():
    manager = _quiet_manager({
        "resources": {
            "wild_fields": {
                "remaining": 2,
                "last_tick": 0,
                "regen_due": [120.0],
                "regen_check_at": 100.0,
            }
        },
        "events": {"last_player_location": "wild_fields"},
    })
    with patch("economy.manager.time.time", return_value=130.0):
        manager.update(1, player_location="village_square")
    row = manager.state.resources["wild_fields"]
    assert row["remaining"] == 2
    assert row["regen_due"] == [150.0]
    # 130 秒离开时剩余 20 秒，资源应在离开后 20 秒恢复。
    with patch("economy.manager.time.time", return_value=149.9):
        manager.update(1, player_location="village_square")
    assert row["remaining"] == 2
    with patch("economy.manager.time.time", return_value=150.0):
        manager.update(1, player_location="village_square")
    assert row["remaining"] == 3
    assert row["regen_due"] == []


def test_player_location_pause_state_survives_economy_state_export_and_reload():
    manager = _quiet_manager({
        "resources": {
            "wild_fields": {
                "remaining": 2,
                "last_tick": 0,
                "regen_due": [120.0],
                "regen_check_at": 100.0,
            }
        },
        "events": {"last_player_location": "wild_fields"},
    })
    with patch("economy.manager.time.time", return_value=130.0):
        manager.update(1, player_location="wild_fields")
    resumed = _quiet_manager(manager.export_state())
    with patch("economy.manager.time.time", return_value=149.0):
        resumed.update(1, player_location="village_square")
    assert resumed.state.resources["wild_fields"]["remaining"] == 2


def test_new_harvest_timer_starts_at_harvest_time_while_standing_in_room():
    manager = _quiet_manager({
        "resources": {
            "wild_fields": {
                "remaining": 3,
                "last_tick": 0,
                "regen_due": [120.0],
                "regen_check_at": 100.0,
            }
        },
        "events": {"last_player_location": "wild_fields"},
    })
    with patch("economy.manager.time.time", return_value=130.0):
        ok, _ = manager.gather("wild_fields", 1)
    assert ok
    assert manager.state.resources["wild_fields"]["regen_due"] == [150.0, 160.0]
