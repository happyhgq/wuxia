import engine


def test_status_expires_after_exact_number_of_processing_ticks():
    statuses = {}
    engine.add_status(statuses, "stun", 2, 0)
    _, stunned, _ = engine.process_status_effects(statuses)
    assert stunned is True
    assert statuses["stun"]["turns"] == 1
    _, stunned, messages = engine.process_status_effects(statuses)
    assert stunned is True
    assert "stun" not in statuses
    assert any("状态解除" in msg for msg in messages)


def test_status_refresh_keeps_longer_duration_and_stronger_value():
    statuses = {}
    engine.add_status(statuses, "poison", 3, 5)
    engine.add_status(statuses, "poison", 1, 2)
    assert statuses["poison"] == {"turns": 3, "value": 5}
    engine.add_status(statuses, "poison", 5, 8)
    assert statuses["poison"] == {"turns": 5, "value": 8}


def test_damage_over_time_applies_on_the_expiration_tick():
    statuses = {}
    engine.add_status(statuses, "poison", 1, 7)
    hp_change, stunned, messages = engine.process_status_effects(statuses)
    assert hp_change == -7
    assert stunned is False
    assert "poison" not in statuses
    assert any("损失 7 点气血" in msg for msg in messages)


def test_clearing_statuses_removes_all_player_combat_statuses():
    engine.p_statuses_global.clear()
    engine.add_status(engine.p_statuses_global, "shield", 2, 10)
    engine.add_status(engine.p_statuses_global, "stun", 1, 0)
    engine.clear_statuses()
    assert engine.p_statuses_global == {}
