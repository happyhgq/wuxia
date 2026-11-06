"""Alpha250：门派专属武器不仅有数值差异，也有低概率、可实战触发的兵刃特性。"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_items():
    return json.loads((ROOT / 'data' / 'items.json').read_text(encoding='utf-8'))


def test_sect_reward_weapons_have_distinct_bounded_combat_effects():
    import engine
    items = load_items()
    expected = {
        '少林戒棍': ('armor_break', 0.12),
        '武当云纹剑': ('stun', 0.06),
        '华山松纹剑': ('bleed', 0.13),
    }
    for name, (status, chance) in expected.items():
        item = items[name]
        effect = item.get('weapon_effect')
        assert item['type'] == 'weapon'
        assert effect and effect['type'] == 'status'
        assert effect['status'] == status
        assert effect['chance'] == chance
        assert 0 < effect['chance'] <= 0.15
        assert effect['status'] in engine.STATUS_EFFECTS
        assert effect['turns'] in range(1, 4)
        assert effect['value'] >= 0
        assert effect.get('description')


def test_sect_weapon_effects_really_apply_in_combat(monkeypatch):
    import combat
    import engine
    from player import Player

    cases = [
        ('少林戒棍', 'armor_break'),
        ('武当云纹剑', 'stun'),
        ('华山松纹剑', 'bleed'),
    ]
    monkeypatch.setattr(combat.random, 'random', lambda: 0.0)
    for name, expected_status in cases:
        player = Player(f'Alpha250-{name}', '散人')
        player.equipment['weapon'] = name
        statuses = {}
        messages = combat.apply_weapon_combat_effect(player, statuses, target_hit=True)
        assert expected_status in statuses, (name, statuses)
        assert messages and name in messages[0]
        # 未命中不能触发兵刃特效。
        untouched = {}
        assert combat.apply_weapon_combat_effect(player, untouched, target_hit=False) == []
        assert untouched == {}


def test_old_weapons_without_special_effect_remain_compatible():
    import combat
    from player import Player

    player = Player('Alpha250-legacy-weapon', '散人')
    player.equipment['weapon'] = '铁剑'
    statuses = {}
    assert combat.apply_weapon_combat_effect(player, statuses, target_hit=True) == []
    assert statuses == {}
