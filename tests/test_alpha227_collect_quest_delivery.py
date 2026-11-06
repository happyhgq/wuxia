"""Alpha227：采集任务必须实际交付物品，结算失败则退还物品。"""
from contextlib import redirect_stdout
from io import StringIO

import engine
from actions import handle_quest
from player import Player

QUEST = "新手采药·认识资源"


def _player_with_completed_progress():
    player = Player("采集交付验收", "散人")
    player.location = "medicine_shop"
    player.active_quests[QUEST] = 2
    player.quest_states[QUEST] = {"stage": 0, "progress": 2}
    return player


def _run_turn_in(player):
    output = StringIO()
    with redirect_stdout(output):
        handle_quest(player, "jiaofu", [QUEST])
    return output.getvalue()


def test_collect_quest_cannot_be_rewarded_when_required_items_are_missing(monkeypatch):
    player = _player_with_completed_progress()
    monkeypatch.setattr(Player, "save_to_file", lambda self, filename=None: True)
    before = (player.exp, player.gold, list(player.inventory))

    output = _run_turn_in(player)

    assert "交付失败" in output and "草药 ×2" in output
    assert QUEST in player.active_quests
    assert QUEST not in player.completed_quests
    assert (player.exp, player.gold, list(player.inventory)) == before


def test_collect_quest_consumes_actual_items_only_on_success(monkeypatch):
    player = _player_with_completed_progress()
    player.inventory.extend(["草药", "草药", "木材"])
    initial_herbs = player.inventory.count("草药")
    monkeypatch.setattr(Player, "save_to_file", lambda self, filename=None: True)
    gold_before = player.gold

    output = _run_turn_in(player)

    assert "恭喜完成任务" in output
    assert QUEST not in player.active_quests
    assert QUEST in player.completed_quests
    assert player.inventory.count("草药") == initial_herbs - 2
    assert player.inventory.count("木材") == 1
    assert player.gold == gold_before + engine.QUESTS[QUEST]["reward"]["gold"]


def test_collect_quest_returns_items_when_reward_bundle_is_invalid(monkeypatch):
    player = _player_with_completed_progress()
    player.inventory.extend(["草药", "草药"])
    monkeypatch.setattr(Player, "save_to_file", lambda self, filename=None: True)
    original = engine.QUESTS[QUEST]
    broken = dict(original)
    broken["reward"] = {"item": "不存在的奖励物品"}
    monkeypatch.setitem(engine.QUESTS, QUEST, broken)
    before_inventory = list(player.inventory)
    before_gold = player.gold

    output = _run_turn_in(player)

    assert "交付物已退还" in output
    assert QUEST in player.active_quests
    assert QUEST not in player.completed_quests
    assert player.inventory == before_inventory
    assert player.gold == before_gold


def test_separate_turn_in_npc_can_complete_quest_through_dialogue(monkeypatch):
    from actions import handle_talk_and_ask

    quest_name = "失踪信使"
    quest = engine.QUESTS[quest_name]
    player = Player("异人交付入口验收", "散人")
    player.location = next(
        room_id for room_id, room in engine.ROOMS.items()
        if quest["turn_in_npc"] in room.get("npcs", [])
    )
    player.active_quests[quest_name] = 1
    player.quest_states[quest_name] = {"stage": 2, "progress": 1}
    monkeypatch.setattr(Player, "save_to_file", lambda self, filename=None: True)
    output = StringIO()
    with redirect_stdout(output):
        handle_talk_and_ask(player, [quest["turn_in_npc"], f"交付委托 {quest['title']}"])

    assert "恭喜完成任务" in output.getvalue()
    assert quest_name not in player.active_quests
    assert quest_name in player.completed_quests


def test_collect_quest_state_survives_save_load_and_cannot_be_rewarded_twice(monkeypatch, tmp_path):
    """交付前读档保留进度；交付后读档保留完成状态，不能重复领取。"""
    original_save = Player.save_to_file
    player = _player_with_completed_progress()
    player.inventory.extend(["草药", "草药"])
    save_path = tmp_path / "quest_round_trip.json"
    monkeypatch.setattr(Player, "save_to_file", lambda self, filename=None: original_save(self, str(save_path)))

    # 先保存尚未交付的任务，再从存档恢复。
    assert original_save(player, str(save_path))
    loaded = Player.load_from_file(str(save_path))
    assert loaded is not None
    assert loaded.active_quests[QUEST] == 2
    assert loaded.inventory.count("草药") == 3  # 新角色初始携带一株，另加两株交付物

    gold_before = loaded.gold
    _run_turn_in(loaded)
    assert QUEST not in loaded.active_quests
    assert QUEST in loaded.completed_quests
    assert loaded.gold == gold_before + engine.QUESTS[QUEST]["reward"]["gold"]

    # 交付后的完成状态再次读档，不应允许非重复任务再次领奖。
    reloaded = Player.load_from_file(str(save_path))
    assert reloaded is not None
    assert QUEST in reloaded.completed_quests
    assert QUEST not in reloaded.active_quests
    gold_after_first_delivery = reloaded.gold
    with redirect_stdout(StringIO()):
        handle_quest(reloaded, "jiaofu", [QUEST])
    assert reloaded.gold == gold_after_first_delivery
    assert reloaded.inventory.count("草药") == 1  # 仅保留新角色初始携带的一株
