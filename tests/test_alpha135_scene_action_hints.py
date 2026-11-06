"""Alpha135：场景操作提示应与实际资源命令一致且不重复。"""
import json
from pathlib import Path

from actions import _scene_action_hints

ROOT = Path(__file__).resolve().parents[1]
ROOMS = json.loads((ROOT / "data" / "rooms.json").read_text(encoding="utf-8"))
RESOURCES = json.loads((ROOT / "data" / "economy" / "resources.json").read_text(encoding="utf-8"))


def test_gather_hint_uses_search_once_for_herbs():
    room_id = "mistwood_stream"
    hints = _scene_action_hints(room_id, ROOMS[room_id], RESOURCES, economy_state={})
    assert hints.count("搜索（获取草药）") == 1
    assert "采集/搜索" not in hints


def test_gather_hint_names_the_actual_gatherable_item():
    room_id = "mountain_path"
    hints = _scene_action_hints(room_id, ROOMS[room_id], RESOURCES, economy_state={})
    assert "搜索（获取蛇胆）" in hints
    assert "搜索（获取草药）" not in hints


def test_logging_and_mining_hints_keep_their_canonical_commands():
    for room_id, expected in (("mistwood_trail", "伐木"), ("abandoned_iron_mine", "采矿")):
        if room_id not in ROOMS or room_id not in RESOURCES:
            continue
        hints = _scene_action_hints(room_id, ROOMS[room_id], RESOURCES, economy_state={})
        assert expected in hints
