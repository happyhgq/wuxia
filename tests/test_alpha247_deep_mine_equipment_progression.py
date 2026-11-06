"""Alpha247：深矿清障解锁村中精铁剑生产，保留城内基础铁剑供应。"""
import json
from pathlib import Path

from economy import EconomyManager

BASE = Path(__file__).resolve().parents[1]


def test_deep_mine_flag_unlocks_real_refined_sword_recipe_only_for_village_smith():
    base = EconomyManager({
        "tick": 0,
        "npc_inventory": {
            "铁匠": {"铁矿石": 32, "铁剑": 0, "精铁剑": 0},
            "百炼铁铺铁匠": {"铁矿石": 32, "铁剑": 0, "精铁剑": 0},
        },
        "npc_gold": {"铁匠": 500, "百炼铁铺铁匠": 500},
    })
    assert base.recipes["铁匠"]["outputs"] == {"铁剑": 1}

    base.apply_world_progress({"flags": {"world:main:deep_iron_gallery_cleared": True,
                                           "world:main:abandoned_mine_supply_secured": True}})
    village_recipe = base.recipes["铁匠"]
    city_recipe = base.recipes["百炼铁铺铁匠"]
    assert village_recipe["inputs"] == {"铁矿石": 8}
    assert village_recipe["outputs"] == {"精铁剑": 1}
    assert village_recipe["output_capacity"] == {"精铁剑": 3}
    assert city_recipe["outputs"] == {"铁剑": 1}

    base.update(240, player_location="village_square")
    state = base.export_state()
    village = state["npc_inventory"]["铁匠"]
    city = state["npc_inventory"]["百炼铁铺铁匠"]
    # 商队可能及时采购成品，所以验证真实生产流水而非要求货物永远滞留库存。
    produced = [row for row in state["events"].get("world_activity", [])
                if row.get("kind") == "制作" and row.get("item") == "精铁剑"
                and row.get("actor") == "铁匠"]
    assert produced, state
    city_produced = [row for row in state["events"].get("world_activity", [])
                     if row.get("kind") == "制作" and row.get("item") == "铁剑"
                     and row.get("actor") == "百炼铁铺铁匠"]
    assert city_produced, state
    assert state["market"]["精铁剑"]["last_price"] >= 150
    assert state["regional_market"]["main"]["精铁剑"]["last_price"] >= 150


def test_deep_mine_equipment_unlock_does_not_change_save_schema_or_item_stats():
    items = json.loads((BASE / "data" / "items.json").read_text(encoding="utf-8"))
    assert items["铁剑"]["atk"] < items["精铁剑"]["atk"]
    assert items["精铁剑"]["price"] == 150
    # This progression is derived from existing world flags and recipes; it introduces no save fields.
    from player import Player
    p = Player("Alpha247验收", "散人")
    before_keys = set(vars(p).keys())
    p.set_flag("world:main:deep_iron_gallery_cleared", True)
    after_keys = set(vars(p).keys())
    assert after_keys == before_keys
