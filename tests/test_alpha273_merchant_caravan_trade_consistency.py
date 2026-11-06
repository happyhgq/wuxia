# -*- coding: utf-8 -*-
"""Alpha273：商人/商队交易资格、真实库存、资金扣增与报价一致性回归。"""
import contextlib
import copy
import io
import re

import pytest

import actions
import engine
import player as player_module
from economy import EconomyManager, TradeService
from player import Player


@pytest.fixture(autouse=True)
def _isolate_save(monkeypatch):
    original = Player.save_to_file

    def guarded(self, filename=player_module.SAVE_PATH):
        # 交易动作触发的自动存档写向正式存档路径，测试中一律拦截；显式路径仍真实写入。
        if filename == player_module.SAVE_PATH:
            return True
        return original(self, filename)

    monkeypatch.setattr(Player, "save_to_file", guarded)


def _economy_player(name="交易验收", ticks=30):
    player = Player(name, "散人")
    manager = EconomyManager()
    manager.update(ticks)
    player.economy_state = copy.deepcopy(manager.export_state())
    player.inventory = []
    return player


def _run(func, *args):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        result = func(*args)
    return result, out.getvalue()


def _shelf_price(text, item, side="买入"):
    match = re.search(rf"{re.escape(item)} - {side} (\d+) 两", text)
    assert match, text
    return int(match.group(1))


def _activate_caravan(player, caravan_id="北路商队", room="village_square"):
    events = player.economy_state.setdefault("events", {})
    events.setdefault("active_caravans", {})[f"{caravan_id}:{room}"] = {
        "name": caravan_id, "room": room, "until_tick": 9999,
    }
    player.location = room
    return player.economy_state.setdefault("caravans", {}).setdefault(caravan_id, {
        "gold": 500, "capacity": 20, "inventory": {},
    })


def test_pharmacy_shelf_reports_real_stock_for_simulated_goods():
    player = _economy_player()
    player.location = "medicine_shop"
    stock = player.economy_state["npc_inventory"]["药铺老板"]["疗伤药"]
    assert stock > 0
    ok, text = _run(actions.handle_trading, player, "shop", [])
    assert ok
    assert f"疗伤药 - 买入" in text
    assert f"余 {stock} 件" in text


def test_sold_out_simulated_good_is_marked_and_cannot_be_bought():
    player = _economy_player()
    player.location = "medicine_shop"
    player.gold = 500
    player.economy_state["npc_inventory"]["药铺老板"]["疗伤药"] = 0
    ok, text = _run(actions.handle_trading, player, "shop", [])
    assert ok
    assert re.search(r"疗伤药 - 暂无现货", text)
    assert "疗伤药 - 买入" not in text

    before = copy.deepcopy(player.economy_state)
    ok, message = _run(actions.handle_trading, player, "buy", ["疗伤药", "1"])
    assert not ok
    assert "暂无现货" in message
    assert player.gold == 500
    assert player.inventory == []
    assert player.economy_state == before


def test_shop_shelf_quote_matches_actual_payment_for_real_stock_goods():
    player = _economy_player()
    player.location = "medicine_shop"
    player.gold = 500
    _, text = _run(actions.handle_trading, player, "shop", [])
    quoted = _shelf_price(text, "疗伤药")
    stock_before = player.economy_state["npc_inventory"]["药铺老板"]["疗伤药"]

    ok, _ = _run(actions.handle_trading, player, "buy", ["疗伤药", "1"])
    assert ok
    assert player.gold == 500 - quoted
    assert player.economy_state["npc_inventory"]["药铺老板"]["疗伤药"] == stock_before - 1


def test_regular_shop_goods_of_economy_merchant_stay_available():
    """非模拟生产的常备药沿用静态商店规则，不能再被经济库存校验误锁。"""
    player = _economy_player()
    player.location = "medicine_shop"
    player.gold = 500
    _, text = _run(actions.handle_trading, player, "shop", [])
    quoted = _shelf_price(text, "回内丹")

    ok, message = _run(actions.handle_trading, player, "buy", ["回内丹", "1"])
    assert ok, message
    assert player.gold == 500 - quoted
    assert player.inventory.count("回内丹") == 1
    assert "回内丹" not in player.economy_state["npc_inventory"]["药铺老板"]


def test_selling_recipe_output_back_restores_stock_up_to_capacity():
    player = _economy_player()
    player.location = "medicine_shop"
    stock = player.economy_state["npc_inventory"]["药铺老板"]
    stock["疗伤药"] = 10
    player.inventory = ["疗伤药", "疗伤药", "疗伤药"]
    wallet_before = player.economy_state["npc_gold"]["药铺老板"]
    gold_before = player.gold

    ok, message = _run(actions.handle_trading, player, "sell", ["疗伤药", "2"])
    assert ok, message
    assert stock["疗伤药"] == 12
    paid = player.gold - gold_before
    assert paid > 0
    assert player.economy_state["npc_gold"]["药铺老板"] == wallet_before - paid

    ok, message = _run(actions.handle_trading, player, "sell", ["疗伤药", "1"])
    assert not ok
    assert "库存已满" in message
    assert player.inventory == ["疗伤药"]


def test_selling_unrelated_goods_does_not_pollute_workshop_stock():
    player = _economy_player()
    player.location = "village_square"
    player.inventory = ["草药", "草药"]
    ok, message = _run(actions.handle_trading, player, "sell", ["草药", "2", "给", "木匠老许"])
    assert ok, message
    assert "草药" not in player.economy_state["npc_inventory"].get("木匠老许", {})
    assert player.inventory == []


def test_named_merchant_absent_from_scene_never_trades_with_bystander():
    player = _economy_player(ticks=5)
    player.location = "village_square"
    player.inventory = ["草药"]
    player.gold = 100
    before = copy.deepcopy(player.economy_state)

    ok, message = _run(actions.handle_trading, player, "sell", ["草药", "1", "给", "药铺老板"])
    assert not ok
    assert "不在此处" in message
    assert player.gold == 100
    assert player.inventory == ["草药"]
    assert player.economy_state == before


def test_shop_shelf_marks_merchant_without_ready_cash():
    player = _economy_player()
    player.location = "medicine_shop"
    player.economy_state["npc_gold"]["药铺老板"] = 0
    ok, text = _run(actions.handle_trading, player, "shop", [])
    assert ok
    assert "店家现银不足" in text


def test_caravan_shelf_prices_are_readable_and_match_actual_purchase():
    player = _economy_player(ticks=5)
    caravan = _activate_caravan(player)
    caravan["inventory"] = {"铁矿石": 5, "木材": 4}
    caravan["gold"] = 800
    caravan["capacity"] = 20
    player.gold = 300

    ok, text = _run(actions.handle_trading, player, "shop", ["给", "北路商队"])
    assert ok
    assert "每件售价" in text and "每件收购" in text
    assert "相关内容" not in text
    assert "六成折价收购" in text
    quoted = int(re.search(r"【木材】×4，每件售价 (\d+) 两", text).group(1))

    ok, message = _run(actions.handle_trading, player, "buy", ["木材", "2", "给", "北路商队"])
    assert ok, message
    assert player.gold == 300 - quoted * 2
    assert caravan["inventory"]["木材"] == 2


def test_caravan_ambiguous_goods_list_candidates_and_exact_name_trades():
    player = _economy_player(ticks=5)
    caravan = _activate_caravan(player)
    caravan["inventory"] = {"铁剑": 3, "铁矿石": 6}
    caravan["capacity"] = 20
    player.gold = 500

    ok, message = _run(actions.handle_trading, player, "buy", ["铁", "1", "给", "北路商队"])
    assert not ok
    assert "铁剑" in message and "铁矿石" in message
    assert player.gold == 500
    assert caravan["inventory"] == {"铁剑": 3, "铁矿石": 6}

    ok, message = _run(actions.handle_trading, player, "buy", ["铁矿石", "2", "给", "北路商队"])
    assert ok, message
    assert caravan["inventory"]["铁矿石"] == 4
    assert caravan["inventory"]["铁剑"] == 3
    assert player.inventory.count("铁矿石") == 2


def test_caravan_oversized_purchase_reports_remaining_without_side_effects():
    player = _economy_player(ticks=5)
    caravan = _activate_caravan(player)
    caravan["inventory"] = {"木材": 2}
    player.gold = 500
    before = copy.deepcopy(player.economy_state)

    ok, message = _run(actions.handle_trading, player, "buy", ["木材", "3", "给", "北路商队"])
    assert not ok
    assert "只剩 2 件" in message
    assert player.gold == 500
    assert player.economy_state == before


def test_trade_stock_changes_survive_v12_save_roundtrip(tmp_path):
    player = _economy_player()
    player.location = "medicine_shop"
    player.inventory = ["疗伤药"]
    stock_before = player.economy_state["npc_inventory"]["药铺老板"]["疗伤药"]
    ok, message = _run(actions.handle_trading, player, "sell", ["疗伤药", "1"])
    assert ok, message
    expected = stock_before + 1

    path = tmp_path / "save.json"
    assert player.save_to_file(str(path)) is True
    loaded = Player.load_from_file(str(path))
    assert loaded is not None
    assert loaded.economy_state["npc_inventory"]["药铺老板"]["疗伤药"] == expected
    assert loaded.get_quest_clock() == player.get_quest_clock()


def test_non_simulated_items_are_not_required_to_have_stock():
    player = _economy_player()
    assert player.economy_state["npc_inventory"].get("药铺老板", {}).get("回内丹") is None
    assert TradeService.sells_from_real_stock("药铺老板", "疗伤药") is True
    assert TradeService.sells_from_real_stock("药铺老板", "回内丹") is False
    assert TradeService.stockable_items("木匠老许") == {"木材", "木剑"}
    assert "草药" in TradeService.stockable_items("普通商家")
    assert engine.NPCS["药铺老板"]["shop"]
