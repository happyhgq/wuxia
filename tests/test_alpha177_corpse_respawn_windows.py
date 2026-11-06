"""Alpha177：尸体展示时长与敌人复活时长分开计算。"""
from world_lifecycle import record_death, entity_state, visible_enemies

class FakePlayer:
    def __init__(self):
        self.world_state = {"variables": {}}

def test_normal_enemy_corpse_remains_until_one_minute_respawn():
    player = FakePlayer()
    record_death(player, "mistwood_trail", "山贼", tier="normal", now=100.0)
    assert entity_state(player, "mistwood_trail", "山贼", now=159.9)[0] == "corpse"
    alive, corpses = visible_enemies(player, "mistwood_trail", ["山贼"], now=159.9)
    assert alive == []
    assert len(corpses) == 1
    assert entity_state(player, "mistwood_trail", "山贼", now=160.0)[0] == "alive"

def test_boss_corpse_remains_until_five_minute_respawn():
    player = FakePlayer()
    record_death(player, "bandit_zone", "山贼大当家", tier="boss", now=50.0)
    assert entity_state(player, "bandit_zone", "山贼大当家", now=169.9)[0] == "corpse"
    assert entity_state(player, "bandit_zone", "山贼大当家", now=349.9)[0] == "dead"
    assert entity_state(player, "bandit_zone", "山贼大当家", now=350.0)[0] == "alive"
