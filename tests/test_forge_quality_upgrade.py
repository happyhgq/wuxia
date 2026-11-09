# -*- coding: utf-8 -*-
"""打造炉品质升阶：确定性升阶、成本、强化保留与 V12 往返。"""
import builtins
import io
import os
import tempfile
from contextlib import redirect_stdout
from unittest.mock import patch

import engine
from actions import handle_forge
from player import Player
from ui_output import _ANSI_RE


def _no_official_save(monkeypatch):
    monkeypatch.setattr(Player, "save_to_file", lambda self, filename=None, verbose=True: True)


def _capture(callback, *args):
    stream = io.StringIO()
    with redirect_stdout(stream):
        result = callback(*args)
    return result, _ANSI_RE.sub("", stream.getvalue())


def _forge(player, monkeypatch, choice):
    monkeypatch.setattr(builtins, "input", lambda *_: choice)
    return _capture(handle_forge, player, [])


def _forge_player(weapon="铁剑", armor="皮甲", ore=10, gold=1000, enhance=None):
    player = Player("品质升阶验收", "散人")
    player.location = "blacksmith"
    player.equipment = {"weapon": weapon, "armor": armor}
    player.equip_enhance = dict(enhance or {"weapon": 0, "armor": 0})
    player.inventory = ["铁矿石"] * ore
    player.gold = gold
    return player


def test_quality_preview_is_side_effect_free():
    player = _forge_player(weapon="铁剑", enhance={"weapon": 2, "armor": 0})
    before = (player.gold, list(player.inventory), dict(player.equip_enhance), player.equipment["weapon"])

    preview = player.get_quality_upgrade_preview("weapon")

    assert preview["available"] is True
    assert preview["quality"] == "普通"
    assert preview["next_quality"] == "精良"
    assert preview["next_item"] == "铁剑·精良"
    assert preview["current_stat"] == 12 + 6
    assert preview["next_stat"] == 15 + 6
    assert preview["stat_delta"] == 3
    assert preview["enhance"] == 2
    assert (preview["ore_cost"], preview["gold_cost"]) == (3, 80)
    assert (player.gold, player.inventory, player.equip_enhance, player.equipment["weapon"]) == before


def test_quality_preview_reports_max_missing_variant_and_empty():
    player = _forge_player(weapon="铁剑·稀有", armor="布衣")
    assert player.get_quality_upgrade_preview("weapon")["reason"] == "max"
    assert player.get_quality_upgrade_preview("armor")["reason"] == "no_variant"

    player.equipment["weapon"] = None
    assert player.get_quality_upgrade_preview("weapon")["reason"] == "empty"


def test_forge_upgrade_weapon_quality_consumes_materials_and_keeps_enhance(monkeypatch):
    _no_official_save(monkeypatch)
    player = _forge_player(weapon="铁剑", ore=3, gold=80, enhance={"weapon": 1, "armor": 0})

    result, output = _forge(player, monkeypatch, "3")

    assert result is True
    assert player.equipment["weapon"] == "铁剑·精良"
    assert player.equip_enhance["weapon"] == 1
    assert player.inventory.count("铁矿石") == 0
    assert player.gold == 0
    assert "升阶为【铁剑·精良】" in output
    assert "品质：普通 → 精良" in output
    assert "强化 +1 保留" in output
    assert "消耗：铁矿石 ×3（剩余 0）" in output


def test_forge_upgrade_can_continue_to_later_tier(monkeypatch):
    _no_official_save(monkeypatch)
    player = _forge_player(weapon="铁剑·精良", ore=6, gold=240)

    result, output = _forge(player, monkeypatch, "3")

    assert result is True
    assert player.equipment["weapon"] == "铁剑·稀有"
    assert player.inventory.count("铁矿石") == 0
    assert player.gold == 0
    assert "铁剑·稀有" in output


def test_forge_upgrade_armor_uses_defense(monkeypatch):
    _no_official_save(monkeypatch)
    player = _forge_player(weapon="铁剑", armor="锁子甲", ore=3, gold=120)

    result, output = _forge(player, monkeypatch, "4")

    assert result is True
    assert player.equipment["armor"] == "锁子甲·精良"
    assert player.gold == 0
    assert "防御：15 → 18 (+3)" in output


def test_forge_upgrade_skips_missing_tier_on_heavysword(monkeypatch):
    _no_official_save(monkeypatch)
    player = _forge_player(weapon="玄铁重剑", ore=6, gold=800)

    result, output = _forge(player, monkeypatch, "3")

    assert result is True
    assert player.equipment["weapon"] == "玄铁重剑·稀有"
    assert "玄铁重剑·稀有" in output


def test_forge_upgrade_blocks_when_materials_are_short(monkeypatch):
    _no_official_save(monkeypatch)
    player = _forge_player(weapon="铁剑", ore=2, gold=1000)

    result, output = _forge(player, monkeypatch, "3")

    assert result is False
    assert "品质升阶材料不足" in output
    assert player.equipment["weapon"] == "铁剑"
    assert player.inventory.count("铁矿石") == 2
    assert player.gold == 1000

    player.inventory = ["铁矿石"] * 3
    player.gold = 79
    result, output = _forge(player, monkeypatch, "3")
    assert result is False
    assert "品质升阶材料不足" in output
    assert player.equipment["weapon"] == "铁剑"
    assert player.gold == 79


def test_forge_upgrade_refuses_max_quality_and_missing_variants(monkeypatch):
    _no_official_save(monkeypatch)
    player = _forge_player(weapon="铁剑·稀有")
    result, output = _forge(player, monkeypatch, "3")
    assert result is False
    assert "已经达到最高品质" in output
    assert player.equipment["weapon"] == "铁剑·稀有"

    player = _forge_player(weapon="黑风刀")
    result, output = _forge(player, monkeypatch, "3")
    assert result is False
    assert "没有可升的品质变体" in output
    assert player.equipment["weapon"] == "黑风刀"


def test_forge_upgrade_requires_forge_location(monkeypatch):
    _no_official_save(monkeypatch)
    player = _forge_player(weapon="铁剑")
    player.location = "village_square"

    result, output = _forge(player, monkeypatch, "3")

    assert result is False
    assert "只有在打铁铺才可以强化或升阶装备" in output
    assert player.equipment["weapon"] == "铁剑"


def test_forge_preview_shows_quality_line(monkeypatch):
    _no_official_save(monkeypatch)
    player = _forge_player(weapon="铁剑", armor="布衣")

    _, output = _capture(handle_forge, player, ["preview"])

    assert "强化与升阶预览" in output
    assert "兵刃品质：铁剑 [普通] → 精良「铁剑·精良」" in output
    assert "强化 +0 保留" in output
    assert "防具品质：布衣 [普通] —— 该装备没有品质变体" in output


def test_forge_upgrade_records_consumption(monkeypatch):
    _no_official_save(monkeypatch)
    player = _forge_player(weapon="精铁剑", ore=3, gold=150)

    with patch("economy.flow.record_player_consumption") as record:
        result, _ = _forge(player, monkeypatch, "3")

    assert result is True
    record.assert_called_once_with(player, "铁矿石", 3, source="装备品质升阶", gold=150)


def test_forge_upgraded_quality_survives_v12_round_trip(monkeypatch):
    player = _forge_player(weapon="铁剑", ore=3, gold=80, enhance={"weapon": 1, "armor": 0})
    monkeypatch.setattr(builtins, "input", lambda *_: "3")
    with patch("actions.request_autosave"):
        result, _ = _capture(handle_forge, player, [])
    assert result is True

    fd, path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    try:
        assert player.save_to_file(path) is True
        loaded = Player.load_from_file(path)
        assert loaded.equipment["weapon"] == "铁剑·精良"
        assert loaded.equip_enhance["weapon"] == 1
        assert engine.ITEMS[loaded.equipment["weapon"]]["quality"] == "精良"
        assert loaded.get_equipment_stats("weapon")["atk"] == 15 + 3
    finally:
        os.remove(path)
