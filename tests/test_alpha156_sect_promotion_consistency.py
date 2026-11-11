"""Alpha156：少林、武当、华山晋升规则一致性与可达性。"""
from player import Player


def joined(sect):
    player = Player("门派规则测试", "散人")
    player.level = max(player.level, 3)
    assert player.join_sect(sect)[0]
    return player


def test_shaolin_true_disciple_uses_shaolin_trial_and_not_huashan_mentorship():
    player = joined("少林")
    player._sect_progress_state().setdefault("少林", {})["official_rank_index"] = 2
    player.level = 15
    player.change_sect_reputation("少林", 100)
    for _ in range(50):
        player.record_skill_use("罗汉拳")
    requirements = player.get_sect_promotion_requirements("少林")
    assert requirements["required_mentor_bond"] == 0
    assert requirements["required_quests"] == ["少林历练·黑风除恶"]
    ok, message = player.promote_sect_rank("少林")
    assert not ok and "少林历练·黑风除恶" in message
    player.completed_quests.append("少林历练·黑风除恶")
    assert player.promote_sect_rank("少林")[0]


def test_wudang_true_disciple_uses_wudang_trial_and_not_huashan_mentorship():
    player = joined("武当")
    player._sect_progress_state().setdefault("武当", {})["official_rank_index"] = 2
    player.level = 15
    player.change_sect_reputation("武当", 100)
    for _ in range(50):
        player.record_skill_use("太极剑")
    requirements = player.get_sect_promotion_requirements("武当")
    assert requirements["required_mentor_bond"] == 0
    assert requirements["required_quests"] == ["武当历练·以静制动"]
    ok, message = player.promote_sect_rank("武当")
    assert not ok and "武当历练·以静制动" in message
    player.completed_quests.append("武当历练·以静制动")
    assert player.promote_sect_rank("武当")[0]


def test_huashan_keeps_mentorship_and_investigation_requirements():
    player = joined("华山")
    player._sect_progress_state().setdefault("华山", {})["official_rank_index"] = 2
    player.level = 15
    player.change_sect_reputation("华山", 100)
    for _ in range(50):
        player.record_skill_use("华山剑法")
    player.establish_sect_mentorship("华山授业师父")
    player.get_sect_mentorship("华山")["bond"] = 20
    requirements = player.get_sect_promotion_requirements("华山")
    assert requirements["required_mentor_bond"] == 15
    assert requirements["required_quests"] == ["华山历练·磨剑黑风"]
    player.completed_quests.append("华山历练·磨剑黑风")
    assert player.promote_sect_rank("华山")[0]
    player.level = 25
    player.change_sect_reputation("华山", 180)
    for _ in range(30):
        player.record_skill_use("华山剑法")
    requirements = player.get_sect_promotion_requirements("华山")
    assert requirements["required_quests"] == ["华山历练·磨剑黑风", "青锋疑云"]
    ok, message = player.promote_sect_rank("华山")
    assert not ok and "青锋疑云" in message
