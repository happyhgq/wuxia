"""Alpha117：战败恢复反馈必须与实际角色状态一致。"""
from types import SimpleNamespace

from combat import _defeat_recovery


def test_defeat_recovery_reports_actual_hp_and_return_location():
    player = SimpleNamespace(hp=0, max_hp=101, location="mistwood")
    message = _defeat_recovery(player)
    assert player.hp == 50
    assert player.location == "temple"
    assert "50/101" in message
    assert "古庙" in message


def test_defeat_recovery_never_leaves_character_at_zero_hp():
    player = SimpleNamespace(hp=0, max_hp=1, location="main")
    message = _defeat_recovery(player)
    assert player.hp == 1
    assert player.hp <= player.max_hp
    assert "1/1" in message


def test_defeat_recovery_caps_invalid_or_overlarge_max_hp_input():
    player = SimpleNamespace(hp=-10, max_hp=10, location="main")
    _defeat_recovery(player, "temple")
    assert player.hp == 5
    assert 1 <= player.hp <= player.max_hp
