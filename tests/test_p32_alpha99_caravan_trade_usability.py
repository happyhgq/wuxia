"""Alpha99：村中商队到场、收购额度与指定交易对象。"""
import json
from pathlib import Path
from types import SimpleNamespace

import actions
import engine
from economy import TradeService


ROOT = Path(__file__).resolve().parents[1]


def test_village_merchant_has_larger_cargo_and_pays_reference_herb_price():
    configs = json.loads((ROOT / "data" / "economy" / "caravans.json").read_text(encoding="utf-8"))
    merchant = configs["村镇行商"]
    assert merchant["capacity"] >= 30
    assert merchant["gold"] >= 1200
    assert merchant["buy_prices"]["草药"] == 8
    # 默认供需条件下，行商对草药的收购报价与配置的 8 两基准一致。
    player = SimpleNamespace(economy_state={"market": {}, "regional_market": {}, "events": {}}, location="village_square")
    assert TradeService.market_price(player, "草药", merchant["buy_prices"]["草药"], "sell", 1.0, 1.0) == 8


def test_village_square_appearance_is_spaced_out_and_route_is_preserved():
    configs = json.loads((ROOT / "data" / "economy" / "caravans.json").read_text(encoding="utf-8"))
    merchant = configs["村镇行商"]
    appearance = next(row for row in merchant["appearances"] if row["room"] == "village_square")
    assert appearance["interval"] >= 12
    assert appearance["offset"] > 0
    assert "village_square" in merchant["route"]


def test_player_can_explicitly_choose_caravan_for_sell(monkeypatch):
    calls = []
    monkeypatch.setattr(actions, "_handle_caravan_trading",
                        lambda player, cmd, args, caravan_id, cfg: calls.append((cmd, list(args), caravan_id)) or True)
    player = SimpleNamespace(
        location="village_square",
        economy_state={
            "tick": 10,
            "caravans": {"村镇行商": {"gold": 1200, "inventory": {}, "capacity": 30}},
            "events": {"active_caravans": {"村镇行商:village_square": {
                "name": "村镇行商", "room": "village_square", "until_tick": 13
            }}},
        },
        get_npcs_in_room=lambda room: [],
    )
    assert actions.handle_trading(player, "sell", ["草药", "6", "给", "村镇行商"])
    assert calls == [("sell", ["草药", "6"], "村镇行商")]
