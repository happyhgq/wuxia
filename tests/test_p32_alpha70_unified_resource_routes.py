import json
from collections import deque
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_all_resource_nodes_have_valid_action_capacity_and_recovery_rules():
    rooms = load(ROOT / "data" / "rooms.json")
    resources = load(ROOT / "data" / "economy" / "resources.json")
    actions = {"gather", "chop", "mine"}
    seen_actions = set()
    for room_id, cfg in resources.items():
        assert room_id in rooms, f"资源点缺少场景：{room_id}"
        assert cfg.get("action", "mine") in actions, f"操作类型不统一：{room_id}"
        seen_actions.add(cfg.get("action", "mine"))
        assert int(cfg.get("capacity", 0)) > 0, room_id
        assert 1 <= int(cfg.get("yield_max", 0)) <= int(cfg.get("capacity", 0)), room_id
        assert int(cfg.get("regen_interval", 0)) > 0, room_id
        assert int(cfg.get("regen_amount", 0)) > 0, room_id
        assert str(cfg.get("item", "")).strip(), room_id
    assert seen_actions == actions


def test_woodcutting_and_mining_have_independent_multi_stop_routes():
    rooms = load(ROOT / "data" / "rooms.json")
    resources = load(ROOT / "data" / "economy" / "resources.json")
    expected = {
        "chop": {"mistwood_trail", "bamboo_hollow", "old_woodlot"},
        "mine": {"abandoned_iron_mine", "deep_iron_gallery", "collapsed_quarry"},
    }
    for action, nodes in expected.items():
        assert nodes <= set(resources)
        assert all(resources[node].get("action", "mine") == action for node in nodes)
        for start in nodes:
            seen = {start}
            queue = deque([(start, 0)])
            found = set()
            while queue:
                current, distance = queue.popleft()
                cfg = resources.get(current, {})
                if cfg.get("action", "mine") == action and current in nodes:
                    found.add(current)
                if distance >= 3:
                    continue
                for target in rooms[current].get("exits", {}).values():
                    if target in rooms and target not in seen:
                        seen.add(target)
                        queue.append((target, distance + 1))
            assert found == nodes, f"{action} route from {start} cannot reach all nodes: {found}"


def test_stock_display_uses_same_recovery_language_for_all_three_resource_types():
    from actions import _resource_stock_line
    resources = {
        "herb": {"item": "草药", "action": "gather", "capacity": 8, "regen_interval": 5, "regen_amount": 2},
        "forest": {"item": "木材", "action": "chop", "capacity": 18, "regen_interval": 7, "regen_amount": 3},
        "mine": {"item": "铁矿石", "action": "mine", "capacity": 24, "regen_interval": 9, "regen_amount": 4},
    }
    for room_id, cfg in resources.items():
        state = {"tick": 10, "resources": {room_id: {"remaining": 0, "last_tick": 8}}}
        line = _resource_stock_line(room_id, state, resources)
        assert f"0/{cfg['capacity']}" in line
        assert "暂时耗尽" in line
        assert "等待自然恢复" in line
        assert f"每{cfg['regen_interval']}个世界时刻恢复{cfg['regen_amount']}份" in line
        assert "下一次约" in line


def test_harvest_depletion_and_regeneration_are_independent_for_all_actions():
    from economy import EconomyManager
    resources = {
        "herb": {"item": "草药", "action": "gather", "capacity": 2, "yield_max": 1, "regen_interval": 2, "regen_amount": 1},
        "forest": {"item": "木材", "action": "chop", "capacity": 2, "yield_max": 1, "regen_interval": 3, "regen_amount": 1},
        "mine": {"item": "铁矿石", "action": "mine", "capacity": 2, "yield_max": 1, "regen_interval": 4, "regen_amount": 1},
    }
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as tmp:
        Path(tmp, "resources.json").write_text(json.dumps(resources, ensure_ascii=False), encoding="utf-8")
        Path(tmp, "recipes.json").write_text("{}", encoding="utf-8")
        Path(tmp, "caravans.json").write_text("{}", encoding="utf-8")
        Path(tmp, "gatherers.json").write_text("{}", encoding="utf-8")
        manager = EconomyManager({"tick": 0}, data_dir=tmp)
        methods = {"gather": manager.gather, "chop": manager.chop, "mine": manager.mine}
        for room_id, cfg in resources.items():
            ok, _ = methods[cfg["action"]](room_id, 1)
            assert ok
            ok, _ = methods[cfg["action"]](room_id, 1)
            assert ok
            assert manager.state.resources[room_id]["remaining"] == 0
            ok, message = methods[cfg["action"]](room_id, 1)
            assert not ok and "耗尽" in message
        manager.update(2)
        assert manager.state.resources["herb"]["remaining"] == 1
        assert manager.state.resources["forest"]["remaining"] == 0
        assert manager.state.resources["mine"]["remaining"] == 0
        manager.update(2)
        assert manager.state.resources["forest"]["remaining"] == 1
        assert manager.state.resources["mine"]["remaining"] == 1


def test_route_suggestions_name_real_nearby_places_for_each_resource_action(capsys):
    from types import SimpleNamespace
    import engine
    from main import _print_resource_route_suggestions
    resources = load(ROOT / "data" / "economy" / "resources.json")

    class State:
        resources = {}

    manager = SimpleNamespace(resources=resources, state=State())
    cases = [
        ("wild_fields", "gather", "草药", ("采药溪谷", "黄土官道")),
        ("mistwood_trail", "chop", "木材", ("竹影幽谷",)),
        ("abandoned_iron_mine", "mine", "铁矿石", ("铁脉长廊", "坍塌采石坑")),
    ]
    for room_id, action, item, expected_names in cases:
        player = SimpleNamespace(location=room_id)
        _print_resource_route_suggestions(player, manager, action, item)
        output = capsys.readouterr().out
        assert "输入“地图”查看路线" in output
        for expected in expected_names:
            assert expected in output, (room_id, output)
