# -*- coding: utf-8 -*-
"""Alpha288：敌人装备/秘籍掉落梯度与一次性探索秘籍来源。"""
import contextlib
import io
import json
from pathlib import Path

import engine
from actions import handle_explore
from player import Player

ROOT = Path(__file__).resolve().parents[1]

EQUIPMENT_BANDS = {"normal": 0.02, "ranged": 0.02, "elite": 0.05, "boss": 0.12}
MANUAL_HOLDERS = {"山贼大当家", "黑风寨守关首领"}
MANUAL_ITEM = "黑风刀法秘笈"
MANUAL_FLAG = "explore:bandit_treasury:manual_found"


def _data(name):
    return json.loads((ROOT / "data" / name).read_text(encoding="utf-8"))


def test_alpha288_equipment_drop_chance_is_tiered():
    for name, enemy in engine.ENEMIES.items():
        if "equipment_drop_chance" not in enemy:
            continue
        expected = EQUIPMENT_BANDS[enemy["tier"]]
        assert enemy["equipment_drop_chance"] == expected, (name, enemy["equipment_drop_chance"], expected)


def test_alpha288_only_bosses_keep_manual_trophies():
    holders = {name for name, enemy in engine.ENEMIES.items() if enemy.get("manual_drop")}
    assert holders == MANUAL_HOLDERS
    for name in holders:
        manual = engine.ENEMIES[name]["manual_drop"]
        assert manual == {"item": MANUAL_ITEM, "chance": 0.002}, name


def test_alpha288_manual_is_a_one_time_treasury_exploration_reward():
    sources = []
    for room_id, room in engine.ROOMS.items():
        for event in room.get("exploration_events", []):
            if isinstance(event, dict) and event.get("item") == MANUAL_ITEM:
                sources.append((room_id, event))
    assert [room_id for room_id, _ in sources] == ["bandit_treasury"]
    event = sources[0][1]
    assert event["requires"] == {"not_flags": [MANUAL_FLAG]}
    assert event["effects"] == {"set_flags": {MANUAL_FLAG: True}}
    assert engine.ITEMS[MANUAL_ITEM]["teaches_skill"] == "黑风刀法"


def test_alpha288_treasury_manual_cannot_be_farmed():
    player = Player("掉落复测", "散人")
    player.location = "bandit_treasury"
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        for _ in range(8):
            handle_explore(player)
    assert player.inventory.count(MANUAL_ITEM) == 1
    assert player.world_state["flags"].get(MANUAL_FLAG) is True
    assert "旧刀谱" in output.getvalue()


def test_alpha288_guaranteed_material_drops_and_quest_equipment_are_unchanged():
    enemies = engine.ENEMIES
    assert enemies["山贼二当家"]["drops"] == [
        {"item": "金创药", "chance": 1.0, "guaranteed": True},
        {"item": "铁矿石", "chance": 0.6},
    ]
    assert enemies["山贼大当家"]["drops"] == [{"item": "大还丹", "chance": 0.8, "guaranteed": True}]
    assert enemies["黑风寨守关首领"]["drops"] == [
        {"item": "黑风寨军械残片", "chance": 1.0, "guaranteed": True, "quantity": 1},
        {"item": "黑风寨军械残片", "chance": 0.5, "quantity": 1},
    ]
    quests = _data("quests.json")
    assert quests["清剿黑风山"]["reward"]["item"] == "玄铁重剑"
