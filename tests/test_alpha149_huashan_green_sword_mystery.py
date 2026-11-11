"""Alpha149：华山调查任务《青锋疑云》的阶段、分支和世界影响回归。"""
import engine
from player import Player

QUEST = "青锋疑云"


def make_member():
    p = Player("青锋疑云测试", "散人")
    p.level = max(p.level, 3)
    ok, _ = p.join_sect("华山")
    assert ok
    p.active_quests[QUEST] = 0
    p.quest_states[QUEST] = {"stage": 0, "progress": 0, "accepted_at": 0}
    p.set_flag(f"quest_active:{QUEST}", True)
    return p


def test_quest_is_huashan_only_and_uses_existing_npcs():
    q = engine.QUESTS[QUEST]
    assert q["requires"] == {"sect": "华山", "level": 3}
    assert q["npc"] == "华山接引执事"
    assert q["turn_in_npc"] == "华山接引执事"
    for npc in ("华山守门弟子", "华山接引执事", "华山传功师兄"):
        assert npc in engine.NPCS


def test_investigation_progresses_to_three_meaningful_routes():
    p = make_member()
    p.update_quest_progress("华山守门弟子", event_type="talk")
    assert p.quest_states[QUEST]["stage"] == 1
    p.update_quest_progress("华山接引执事", event_type="talk")
    assert p.quest_states[QUEST]["branch_pending"] is True
    options = p.get_quest_branch_options(QUEST)
    assert [x["id"] for x in options] == ["public_report", "private_trace", "hold_report"]


def test_public_route_sets_persistent_flag_and_preserves_v12_state_shape():
    p = make_member()
    p.update_quest_progress("华山守门弟子", event_type="talk")
    p.update_quest_progress("华山接引执事", event_type="talk")
    ok, _ = p.choose_quest_branch(QUEST, "public_report")
    assert ok
    assert p.get_flag("quest:huashan_green_sword_mystery:route_public") is True
    assert p.get_var("huashan_supply_public_reports", 0) == 1
    assert p._jianghu_profile()["honor"] == 2
    assert set(p.world_state) == {"flags", "variables"}


def test_private_and_cautious_routes_lead_to_distinct_follow_up_stages():
    for branch, expected_stage, flag in [
        ("private_trace", 3, "quest:huashan_green_sword_mystery:route_private"),
        ("hold_report", 4, "quest:huashan_green_sword_mystery:route_cautious"),
    ]:
        p = make_member()
        p.update_quest_progress("华山守门弟子", event_type="talk")
        p.update_quest_progress("华山接引执事", event_type="talk")
        ok, _ = p.choose_quest_branch(QUEST, branch)
        assert ok
        assert p.quest_states[QUEST]["stage"] == expected_stage
        assert p.get_flag(flag) is True


def test_unrelated_talk_does_not_advance_investigation():
    p = make_member()
    p.update_quest_progress("村长", event_type="talk")
    assert p.quest_states[QUEST]["stage"] == 0
    assert p.quest_states[QUEST]["progress"] == 0


def test_full_public_route_can_be_turned_in_and_rewards_huashan_reputation():
    from actions import handle_quest
    import contextlib
    import io

    p = Player("青锋疑云交付测试", "散人")
    p.level = max(p.level, 3)
    assert p.join_sect("华山")[0]
    p.level = 3
    p.location = "huashan_guest_hall"
    with contextlib.redirect_stdout(io.StringIO()):
        handle_quest(p, "jiequ", [QUEST])
    assert QUEST in p.active_quests
    p.update_quest_progress("华山守门弟子", event_type="talk")
    p.update_quest_progress("华山接引执事", event_type="talk")
    assert p.choose_quest_branch(QUEST, "public_report")[0]
    p.update_quest_progress("华山守门弟子", event_type="talk")
    assert p.quest_states[QUEST]["stage"] == 5
    p.update_quest_progress("华山接引执事", event_type="talk")
    p.location = "huashan_guest_hall"
    old_rep = p.get_sect_reputation("华山")
    with contextlib.redirect_stdout(io.StringIO()):
        handle_quest(p, "jiaofu", [QUEST])
    assert QUEST in p.completed_quests
    assert p.get_flag("quest:huashan_green_sword_mystery:resolved") is True
    assert p.get_sect_reputation("华山") == old_rep + 20
    assert p.gold >= 50


def test_investigation_route_affects_established_mentor_trust_once():
    p = make_member()
    p.establish_sect_mentorship()
    p.update_quest_progress("华山守门弟子", event_type="talk")
    p.update_quest_progress("华山接引执事", event_type="talk")
    before = p.get_sect_mentorship("华山")["bond"]
    ok, _ = p.choose_quest_branch(QUEST, "private_trace")
    assert ok
    assert p.get_sect_mentorship("华山")["bond"] == before + 5
    assert p.get_sect_mentorship("华山")["investigation_route"] == "private_trace"
    # 分支已切换阶段，重复选择不能重复获得认可。
    ok, _ = p.choose_quest_branch(QUEST, "private_trace")
    assert not ok
    assert p.get_sect_mentorship("华山")["bond"] == before + 5
