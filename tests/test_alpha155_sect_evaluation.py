"""Alpha155：门派武学与正式授阶、历练表现统一核验。"""
from player import Player


def huashan_disciple():
    p = Player("门派考核测试", "散人")
    p.level = max(p.level, 3)
    assert p.join_sect("华山")[0]
    return p


def test_advanced_huashan_skill_uses_formal_rank_not_reputation_alone():
    p = huashan_disciple()
    p.level = 3
    p.change_sect_reputation("华山", 100)
    ok, message = p.can_learn_skill("夺命连环三仙剑")
    assert not ok
    assert "身份不足" in message
    assert "外门弟子" in message
    assert p.get_sect_official_rank() == "记名弟子"


def test_formal_promotion_unlocks_rank_gated_skill_when_other_conditions_met():
    p = huashan_disciple()
    p.level = 5
    p.change_sect_reputation("华山", 70)
    for _ in range(10):
        p.record_skill_use("华山剑法")
    # 等级与声望都已达标，但没有正式授阶仍不能学习。
    assert p.get_sect_official_rank() == "记名弟子"
    ok, message = p.can_learn_skill("夺命连环三仙剑")
    assert not ok
    assert "身份不足" in message
    p.set_flag("sect:huashan:sword_principle", True)
    assert p.promote_sect_rank()[0]
    assert p.can_learn_skill("夺命连环三仙剑")[0]


def test_true_disciple_promotion_requires_completed_huashan_trial():
    p = huashan_disciple()
    p._sect_progress_state().setdefault("华山", {})["official_rank_index"] = 2
    p.level = 15
    p.change_sect_reputation("华山", 100)
    for _ in range(50):
        p.record_skill_use("华山剑法")
    p.get_sect_mentorship("华山")
    p.establish_sect_mentorship("华山授业师父")
    p.get_sect_mentorship("华山")["bond"] = 20
    ok, message = p.promote_sect_rank()
    assert not ok and "华山历练·磨剑黑风" in message
    p.completed_quests.append("华山历练·磨剑黑风")
    assert p.promote_sect_rank()[0]


def test_core_successor_requires_both_trial_and_investigation_quest():
    p = huashan_disciple()
    # 直接建立兼容测试所需的正式真传状态，验证最高阶额外考核条件。
    p._sect_progress_state().setdefault("华山", {})["official_rank_index"] = 3
    p.level = 25
    p.change_sect_reputation("华山", 180)
    for _ in range(80):
        p.record_skill_use("华山剑法")
    p.establish_sect_mentorship("华山授业师父")
    p.get_sect_mentorship("华山")["bond"] = 20
    p.completed_quests.append("华山历练·磨剑黑风")
    ok, message = p.promote_sect_rank()
    assert not ok and "青锋疑云" in message
    p.completed_quests.append("青锋疑云")
    assert p.promote_sect_rank()[0]
