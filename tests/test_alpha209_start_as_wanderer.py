"""Alpha209：角色创建不再提前选择门派，门派身份由游戏过程取得。"""
from main import create_new_player
from player import Player


def test_new_character_starts_as_wanderer_without_sect_bonus():
    player = create_new_player("初入江湖")
    assert player.get_sect() == "散人"
    assert player.get_sect_official_rank() in ("散人", "无门无派", "江湖散人")
    assert player.max_hp == 100
    assert player.max_mp == 50
    assert player.atk == 10
    assert player.defense == 5


def test_new_character_can_join_sect_through_gameplay_later():
    player = create_new_player("待拜师侠客")
    player.level = max(player.level, 3)
    ok, reason = player.join_sect("少林")
    assert ok, reason
    assert player.get_sect() == "少林"


def test_legacy_explicit_sect_constructor_remains_compatible():
    legacy = Player("旧角色", "武当")
    assert legacy.get_sect() == "武当"
    assert legacy.atk == 12
