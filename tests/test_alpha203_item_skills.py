"""Alpha203：战斗型物品技能应正确命中、施加状态并遵守消耗规则。"""
from types import SimpleNamespace

import engine
from actions import apply_consumable


def _player(item):
    return SimpleNamespace(
        inventory=[item], economy_state={"events": {}},
        world_state={"variables": {"quest_clock": 1}},
        hp=50, max_hp=100, mp=20, max_mp=100,
    )


def test_battle_only_item_does_not_consume_outside_combat():
    player = _player("飞蝗石")
    assert apply_consumable(player, "飞蝗石") is False
    assert player.inventory == ["飞蝗石"]


def test_throwing_stone_damages_current_enemy_and_is_consumed():
    player = _player("飞蝗石")
    context = {"enemy_hp": 80, "enemy_statuses": {}, "enemy_name": "山贼"}
    assert apply_consumable(player, "飞蝗石", context) is True
    assert context["enemy_hp"] == 45
    assert player.inventory == []


def test_poison_dart_applies_damage_and_poison_status():
    player = _player("透骨钉")
    statuses = {}
    context = {"enemy_hp": 80, "enemy_statuses": statuses, "enemy_name": "山贼"}
    assert apply_consumable(player, "透骨钉", context) is True
    assert context["enemy_hp"] == 60
    assert statuses["poison"] == {"turns": 3, "value": 4}


def test_smoke_pellet_stuns_without_direct_damage():
    player = _player("迷烟弹")
    context = {"enemy_hp": 80, "enemy_statuses": {}, "enemy_name": "山贼"}
    assert apply_consumable(player, "迷烟弹", context) is True
    assert context["enemy_hp"] == 80
    assert context["enemy_statuses"]["stun"]["turns"] == 1


def test_item_skill_definitions_use_supported_statuses():
    for name in ("飞蝗石", "透骨钉", "迷烟弹"):
        item = engine.ITEMS[name]
        assert item["type"] == "consumable"
        effect = item["effect"]
        if "target_status" in effect:
            assert effect["target_status"]["name"] in engine.STATUS_EFFECTS
