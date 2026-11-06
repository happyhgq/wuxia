"""Alpha178：兼容缺少完整计时字段的旧死亡记录。"""
from world_lifecycle import entity_state


class FakePlayer:
    def __init__(self, records):
        self.world_state = {"variables": {"dead_entities": records}}


def test_legacy_normal_record_uses_death_time_to_restore_timers():
    key = "enemy:mistwood_trail:山贼"
    player = FakePlayer({key: {
        "name": "山贼", "room_id": "mistwood_trail", "kind": "enemy",
        "tier": "normal", "death_at": 100.0,
    }})
    assert entity_state(player, "mistwood_trail", "山贼", now=159.9)[0] == "corpse"
    assert entity_state(player, "mistwood_trail", "山贼", now=160.0)[0] == "alive"


def test_legacy_boss_record_uses_longer_timer():
    key = "enemy:bandit_zone:山贼大当家"
    player = FakePlayer({key: {
        "name": "山贼大当家", "room_id": "bandit_zone", "kind": "enemy",
        "tier": "boss", "death_at": 50.0,
    }})
    assert entity_state(player, "bandit_zone", "山贼大当家", now=169.9)[0] == "corpse"
    assert entity_state(player, "bandit_zone", "山贼大当家", now=349.9)[0] == "dead"
    assert entity_state(player, "bandit_zone", "山贼大当家", now=350.0)[0] == "alive"


def test_invalid_legacy_timestamp_is_discarded_safely():
    key = "enemy:mistwood_trail:山贼"
    player = FakePlayer({key: {"name": "山贼", "death_at": "not-a-time"}})
    assert entity_state(player, "mistwood_trail", "山贼", now=100.0)[0] == "alive"
    assert key not in player.world_state["variables"]["dead_entities"]
