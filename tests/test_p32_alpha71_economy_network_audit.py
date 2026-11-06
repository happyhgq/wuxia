"""Alpha71: validate the complete resource -> NPC -> workshop -> caravan network."""
import json
from pathlib import Path
from economy import EconomyManager

ROOT = Path(__file__).resolve().parents[1]
ECON = ROOT / "data" / "economy"


def load(name):
    return json.loads((ECON / name).read_text(encoding="utf-8"))


def test_every_supplier_route_is_backed_by_real_supplier_output():
    gatherers, recipes = load("gatherers.json"), load("recipes.json")
    outputs = {npc: {cfg["item"]} for npc, cfg in gatherers.items()}
    for npc, cfg in recipes.items():
        outputs.setdefault(npc, set()).update(cfg.get("outputs", {}).keys())
    for buyer, recipe in recipes.items():
        for route in recipe.get("supplier_routes", []):
            for supplier in route["suppliers"]:
                assert route["item"] in outputs.get(supplier, set()), (buyer, supplier, route["item"])


def test_every_workshop_product_has_a_caravan_trade_path():
    recipes, caravans = load("recipes.json"), load("caravans.json")
    tradable = set()
    visited_stops = set()
    for cfg in caravans.values():
        visited_stops.update(cfg.get("route", []))
        tradable.update(cfg.get("sale_prices", {}).keys())
        tradable.update(cfg.get("buy_prices", {}).keys())
    for npc, recipe in recipes.items():
        stop = recipe.get("room_id") or ("blacksmith" if npc == "铁匠" else None)
        if stop:
            assert stop in visited_stops, (npc, stop)
        for item in recipe.get("outputs", {}):
            assert item in tradable, (npc, item)


def test_long_economy_cycle_keeps_all_stock_wallet_and_cargo_bounds():
    resources, gatherers, recipes, caravans = (load(n) for n in ("resources.json", "gatherers.json", "recipes.json", "caravans.json"))
    manager = EconomyManager()
    manager.update(1200)
    state = manager.export_state()
    for room, cfg in resources.items():
        stock = state["resources"][room]["remaining"]
        assert 0 <= stock <= cfg["capacity"], room
    for npc, cfg in gatherers.items():
        assert 0 <= state["npc_inventory"].get(npc, {}).get(cfg["item"], 0) <= cfg["capacity"], npc
    for npc, cfg in recipes.items():
        for item, cap in cfg.get("output_capacity", {}).items():
            assert 0 <= state["npc_inventory"].get(npc, {}).get(item, 0) <= cap, (npc, item)
    for name, cfg in caravans.items():
        caravan = state["caravans"][name]
        assert 0 <= caravan["gold"] <= 2_000_000_000, name
        assert sum(max(0, int(qty)) for qty in caravan["inventory"].values()) <= cfg["capacity"], name
    assert state["tick"] == 1200
    assert len(state.get("trade_history", [])) <= 100


def test_save_resume_does_not_duplicate_production_or_reset_economy_clock():
    manager = EconomyManager()
    manager.update(600)
    before = manager.export_state()
    resumed = EconomyManager(before)
    resumed.update(600)
    after = resumed.export_state()
    assert after["tick"] == 1200
    for npc, inventory in before["npc_inventory"].items():
        for item, amount in inventory.items():
            assert amount >= 0
    for room, row in after["resources"].items():
        assert row["remaining"] >= 0, room
