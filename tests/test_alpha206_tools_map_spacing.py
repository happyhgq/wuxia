"""Alpha206：地图列宽不应被远处的长道路名撑开，采集工具有真实配置入口。"""
import json
from pathlib import Path

import engine
from ui_output import _ANSI_RE

ROOT = Path(__file__).resolve().parents[1]


def test_village_shop_row_is_compact_even_with_long_road_labels_elsewhere():
    rendered = _ANSI_RE.sub("", engine.MAP_ENGINE.render("village_square"))
    row = next(line for line in rendered.splitlines() if "百草堂" in line and "打铁铺" in line)
    # 连接线与节点相邻；不能再出现由另一坐标行的长道路名造成的空白带。
    assert "百草堂" in row and "村中广场" in row and "打铁铺" in row
    assert "          ──[打铁铺]" not in row
    assert "]          ──" not in row


def test_resource_tools_are_sellable_and_have_action_specific_effects():
    items = json.loads((ROOT / "data" / "items.json").read_text(encoding="utf-8"))
    npcs = json.loads((ROOT / "data" / "npcs.json").read_text(encoding="utf-8"))
    assert items["采药小锄"]["tool_effect"] == {"action": "gather", "chance_bonus": 0.2}
    assert items["砍柴斧"]["tool_effect"] == {"action": "chop", "yield_bonus": 1}
    assert items["矿镐"]["tool_effect"] == {"action": "mine", "yield_bonus": 1}
    assert "采药小锄" in npcs["杂货铺老板"]["shop"]
    assert "采药小锄" not in npcs["药铺老板"]["shop"]
    assert {"砍柴斧", "矿镐"} <= set(npcs["铁匠"]["shop"])


def test_tools_do_not_change_save_version_or_become_equip_slots():
    items = json.loads((ROOT / "data" / "items.json").read_text(encoding="utf-8"))
    assert engine.SAVE_VERSION == 12
    assert all(items[name]["type"] == "tool" for name in ("采药小锄", "砍柴斧", "矿镐"))


def test_tool_bonus_is_read_from_item_data_and_does_not_stack():
    from main import _resource_tool_bonus
    from types import SimpleNamespace
    player = SimpleNamespace(inventory=["矿镐", "矿镐", "砍柴斧"])
    assert _resource_tool_bonus(player, "mine", "yield_bonus") == 1
    assert _resource_tool_bonus(player, "chop", "yield_bonus") == 1
    assert _resource_tool_bonus(player, "gather", "chance_bonus") == 0


def test_vertical_connectors_share_center_with_short_and_long_nodes():
    rooms = {
        "top": {"name": "短名", "zone": "main", "coord": [0, 1], "exits": {"南": "middle"}},
        "middle": {"name": "这是一个很长的场景名称", "zone": "main", "coord": [0, 0], "exits": {"北": "top", "南": "bottom"}},
        "bottom": {"name": "井", "zone": "main", "coord": [0, -1], "exits": {"北": "middle"}},
    }
    rendered = _ANSI_RE.sub("", engine.MapEngine(rooms).render("middle"))
    lines = rendered.splitlines()

    def terminal_column(prefix):
        return engine.get_display_width(prefix)

    node_centers = []
    for name in ("短名", "这是一个很长的场景名称", "井"):
        row = next(line for line in lines if name in line and "[" in line)
        start = row.index("[")
        end = row.index("]", start) + 1
        node_centers.append(terminal_column(row[:start]) + engine.get_display_width(row[start:end]) // 2)

    vertical_columns = [terminal_column(line[:line.index("│")]) for line in lines if "│" in line]
    assert len(vertical_columns) == 2
    assert len(set(node_centers)) == 1
    assert set(vertical_columns) == set(node_centers)


def test_vertical_alignment_survives_mixed_horizontal_and_vertical_branches():
    rooms = {
        "top": {"name": "山门", "zone": "main", "coord": [0, 1], "exits": {"南": "center"}},
        "center": {"name": "村中广场", "zone": "main", "coord": [0, 0], "exits": {"北": "top", "南": "bottom", "东": "east"}},
        "bottom": {"name": "很长很长的南侧道路场景", "zone": "main", "coord": [0, -1], "exits": {"北": "center"}},
        "east": {"name": "东街", "zone": "main", "coord": [1, 0], "exits": {"西": "center"}},
    }
    rendered = _ANSI_RE.sub("", engine.MapEngine(rooms).render("center"))
    lines = rendered.splitlines()
    center_row = next(line for line in lines if "村中广场" in line)
    start = center_row.index("[")
    end = center_row.index("]", start) + 1
    center_col = engine.get_display_width(center_row[:start]) + engine.get_display_width(center_row[start:end]) // 2
    vertical_columns = [engine.get_display_width(line[:line.index("│")]) for line in lines if "│" in line]
    assert vertical_columns and all(col == center_col for col in vertical_columns)
    assert "村中广场" in center_row and "东街" in center_row
