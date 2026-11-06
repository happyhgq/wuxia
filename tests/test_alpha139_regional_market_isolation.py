"""Alpha139：区域行情首次创建时不继承全局或其他地区的供给值。"""
from economy.manager import _adjust_regional_market_supply, _record_regional_market_trade
from economy import EconomyManager


def test_first_regional_trade_starts_from_neutral_supply_not_global_supply():
    manager = EconomyManager({
        "market": {"木材": {"traded": 500, "last_price": 9, "supply": 180}},
        "regional_market": {"other_region": {"木材": {"traded": 50, "last_price": 9, "supply": 170}}},
    })
    rooms = {"forest_edge": {"zone": "new_region"}}

    _record_regional_market_trade(manager.state, rooms, "forest_edge", "木材", 3, 3, 9)

    row = manager.state.regional_market["new_region"]["木材"]
    assert row["supply"] == 23
    assert row["traded"] == 3
    assert manager.state.regional_market["other_region"]["木材"]["supply"] == 170
    assert manager.state.market["木材"]["supply"] == 180


def test_first_regional_production_adjustment_starts_from_neutral_supply():
    manager = EconomyManager({
        "market": {"铁剑": {"traded": 100, "last_price": 30, "supply": 160}},
        "regional_market": {"other_region": {"铁剑": {"traded": 20, "last_price": 30, "supply": 140}}},
    })
    rooms = {"local_forge": {"zone": "new_region"}}

    _adjust_regional_market_supply(manager.state, rooms, "local_forge", "铁剑", 2)

    row = manager.state.regional_market["new_region"]["铁剑"]
    assert row["supply"] == 22
    assert row["traded"] == 0
    assert manager.state.regional_market["other_region"]["铁剑"]["supply"] == 140
    assert manager.state.market["铁剑"]["supply"] == 160
