"""统一未开放任务提示：详情页、NPC 对话与公告栏共用自然语言前置说明。"""
import contextlib
import io

import engine
from actions import (
    _print_npc_quest_offers,
    _quest_npc_status,
    handle_notice_board,
    handle_quest,
)
from player import Player


LOCKED_QUEST = "清剿黑风山"
LOCKED_TITLE = "除暴安良·清剿黑风山"
AVAILABLE_QUEST = "雾隐失药案"
INTERNAL_TOKENS = ("quest_completed:", "case:", "world:", "northfront:", "sect:", "visited_zone:")


def capture(fn, *args, **kwargs):
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        result = fn(*args, **kwargs)
    return stream.getvalue(), result


def test_locked_detail_lists_concrete_prerequisites():
    player = Player("锁定提示验收", "散人")
    output, _ = capture(handle_quest, player, "quests", [LOCKED_QUEST])
    assert f"任务详情：{LOCKED_TITLE}" in output
    assert "当前状态：条件未满足" in output
    assert "接取条件未满足：" in output
    assert "需先完成并交付【村道巡查·清理残匪】" in output
    assert "与【村长】的关系需至少 5（当前 0）" in output
    assert "等级需达到 7（当前 1）" in output
    assert "尚未满足相关剧情条件" not in output


def test_locked_hints_do_not_leak_internal_keys():
    player = Player("内部键过滤验收", "散人")
    output, _ = capture(handle_quest, player, "quests", [LOCKED_QUEST])
    for token in INTERNAL_TOKENS:
        assert token not in output


def test_detail_and_npc_dialogue_share_same_locked_reason():
    player = Player("提示一致性验收", "散人")
    state, detail = _quest_npc_status(player, LOCKED_QUEST)
    assert state == "未开放"
    detail_output, _ = capture(handle_quest, player, "quests", [LOCKED_QUEST])
    dialogue_output, _ = capture(_print_npc_quest_offers, player, "村长", [LOCKED_QUEST], True)
    assert detail in detail_output
    assert detail in dialogue_output


def test_repeated_generic_unknown_flags_are_deduplicated(monkeypatch):
    monkeypatch.setitem(engine.QUESTS, "模拟·未开放委托", {
        "desc": "测试用委托。",
        "npc": "村长",
        "requires": {"flags": ["mystery:flag_one", "mystery:flag_two"], "level": 99},
    })
    player = Player("去重验收", "散人")
    state, detail = _quest_npc_status(player, "模拟·未开放委托")
    assert state == "未开放"
    assert detail.count("尚有前置剧情尚未完成") == 1
    assert "等级需达到 99（当前 1）" in detail


def test_delivered_quest_detail_drops_stale_prerequisite_line():
    player = Player("已交付提示验收", "散人")
    player.completed_quests.append(LOCKED_QUEST)
    player.set_flag(f"quest_completed:{LOCKED_QUEST}", True)
    output, _ = capture(handle_quest, player, "quests", [LOCKED_QUEST])
    assert "当前状态：已交付" in output
    assert "接取条件" not in output
    assert "等级需" not in output


def test_available_quest_detail_shows_acceptable_status_without_hints():
    player = Player("可接取提示验收", "散人")
    player.level = 2
    output, _ = capture(handle_quest, player, "quests", [AVAILABLE_QUEST])
    assert "当前状态：可接取" in output
    assert "接取条件未满足" not in output


def test_notice_board_keeps_locked_clues_out_and_hides_internal_keys():
    player = Player("公告提示验收", "散人")
    player.location = "village_square"
    output, _ = capture(handle_notice_board, player)
    assert "黑风山道仍有山贼拦路" not in output
    for token in INTERNAL_TOKENS:
        assert token not in output
