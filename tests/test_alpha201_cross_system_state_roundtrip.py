"""Alpha201：任务、世界状态、经济状态与 V12 存读档联动验收。"""
import json

import engine
from player import Player


def test_active_quest_progress_world_flags_and_economy_survive_v12_roundtrip(tmp_path, capsys):
    player = Player("跨系统存档验收", "散人")
    quest_name = "铁衣门历练·护路除匪"
    player.active_quests[quest_name] = 2
    player.quest_states[quest_name] = {"stage": 1, "progress": 2, "branch": "护送商旅"}
    player.completed_quests = ["村口初识"]
    player.world_state.setdefault("flags", {})["alpha201_test_flag"] = True
    player.world_state.setdefault("variables", {})["alpha201_test_clock"] = 123
    player.economy_state = {
        "tick": 123,
        "npc_gold": {"测试商人": 321},
        "npc_inventory": {"测试商人": {"草药": 4}},
    }
    player.inventory = ["草药", "铁矿石"]
    player.gold = 456

    path = tmp_path / "alpha201_cross_system_v12.json"
    assert player.save_to_file(str(path))
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["version"] == 12

    loaded = Player.load_from_file(str(path))
    capsys.readouterr()
    assert loaded is not None
    assert loaded.active_quests == player.active_quests
    assert loaded.quest_states == player.quest_states
    assert loaded.completed_quests == player.completed_quests
    assert loaded.world_state["flags"]["alpha201_test_flag"] is True
    assert loaded.world_state["variables"]["alpha201_test_clock"] == 123
    assert loaded.economy_state == player.economy_state
    assert loaded.inventory == player.inventory
    assert loaded.gold == 456


def test_missing_quest_state_is_reconstructed_for_active_staged_quest(tmp_path, capsys):
    player = Player("任务状态兼容验收", "散人")
    quest_name = next(
        (name for name, quest in engine.QUESTS.items() if quest.get("stages")),
        None,
    )
    assert quest_name is not None, "测试数据应至少包含一个分阶段任务"
    player.active_quests[quest_name] = 3
    player.quest_states.pop(quest_name, None)

    path = tmp_path / "alpha201_missing_quest_state_v12.json"
    assert player.save_to_file(str(path))
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["quest_states"] = {}
    path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")

    loaded = Player.load_from_file(str(path))
    capsys.readouterr()
    assert loaded is not None
    assert loaded.quest_states[quest_name]["stage"] == 0
    assert loaded.quest_states[quest_name]["progress"] == 3
