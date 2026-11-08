"""Alpha307：阶段目标达标后重复触发不得再次结算阶段效果。"""
import contextlib
import io

import engine
from player import Player

QUEST = "审计阶段效果"


def _make_player(monkeypatch, stages):
    monkeypatch.setitem(engine.QUESTS, QUEST, {
        "title": QUEST,
        "desc": "",
        "npc": "村长",
        "turn_in_npc": "村长",
        "target_type": "kill",
        "target_name": "测试目标",
        "required_cnt": 1,
        "stages": stages,
    })
    player = Player("阶段效果审计", "散人")
    player.active_quests[QUEST] = 0
    player.quest_states[QUEST] = {"stage": 0, "progress": 0}
    player.set_flag(f"quest_active:{QUEST}", True)
    return player


def _run(player, target, event_type="kill"):
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        player.update_quest_progress(target, event_type=event_type)
    return output.getvalue()


def test_final_stage_effect_is_applied_once(monkeypatch):
    player = _make_player(monkeypatch, [{
        "desc": "击败测试目标",
        "target_type": "kill",
        "target_name": "测试目标",
        "required_cnt": 1,
        "effects": {"increment_variables": {"audit_stage_effect": 1}},
    }])

    first = _run(player, "测试目标")
    second = _run(player, "测试目标")
    third = _run(player, "测试目标")

    assert "[任务更新]" in first
    assert "[任务更新]" not in second and "[任务更新]" not in third
    assert player.get_var("audit_stage_effect", 0) == 1
    assert player.quest_states[QUEST]["progress"] == 1

    player.update_quest_progress("测试目标")
    assert player.get_var("audit_stage_effect", 0) == 1


def test_branch_pending_stage_effect_is_not_reapplied(monkeypatch):
    player = _make_player(monkeypatch, [
        {
            "desc": "向证人问话",
            "target_type": "talk",
            "target_name": "证人",
            "required_cnt": 1,
            "effects": {"increment_variables": {"audit_branch_effect": 1}},
            "branch_choices": [
                {"id": "route_a", "title": "甲路", "next_stage": 1},
                {"id": "route_b", "title": "乙路", "next_stage": 1},
            ],
        },
        {
            "desc": "回禀村长",
            "target_type": "talk",
            "target_name": "村长",
            "required_cnt": 1,
        },
    ])

    _run(player, "证人", "talk")
    assert player.get_var("audit_branch_effect", 0) == 1
    assert player.quest_states[QUEST]["branch_pending"] is True
    assert player.active_quests[QUEST] == 0

    _run(player, "证人", "talk")
    with contextlib.redirect_stdout(io.StringIO()):
        assert player.choose_quest_branch(QUEST, "route_a")[0]

    assert player.get_var("audit_branch_effect", 0) == 1
    assert player.quest_states[QUEST]["stage"] == 1
    assert "branch_pending" not in player.quest_states[QUEST]
    assert player.active_quests[QUEST] == 0
