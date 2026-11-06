"""Alpha252：候选装备预览按候选装备自身属性计算 Build 门槛。"""
from player import Player


def test_candidate_armor_can_supply_attribute_to_activate_build_preview():
    player = Player("预览激活", "散人")
    player.equipment["armor"] = None
    player.attributes["agility"] = 1

    preview = player.get_build_preview_for_item("皮甲")

    assert player.equipment["armor"] is None
    assert preview["after"] is not None
    assert preview["after"]["name"] == "轻灵游身"
    assert preview["changed"] is True


def test_candidate_armor_removal_preview_does_not_keep_old_armor_bonus():
    player = Player("预览解除", "散人")
    player.equipment["armor"] = "皮甲"
    player.attributes["agility"] = 1

    preview = player.get_build_preview_for_item("锁子甲")

    assert player.equipment["armor"] == "皮甲"
    assert preview["before"]["name"] == "轻灵游身"
    assert preview["after"] is None
    assert preview["changed"] is True
