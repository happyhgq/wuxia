"""Alpha170：核验门派武学学习门槛、实战熟练度成长与旧存档兼容。"""

from player import Player


def join(sect):
    player = Player(f"{sect}武学闭环测试", "散人")
    assert player.join_sect(sect)[0]
    return player


def test_successful_skill_use_increases_mastery_and_failed_use_does_not():
    player = join("武当")
    before = player.get_skill_progress("太极剑")
    assert before["learned"]  # 拜入门派时会登记基础武学

    failed = player.record_skill_use("太极剑", success=False)
    assert failed["mastery"] == before["mastery"]

    after = player.record_skill_use("太极剑", success=True)
    assert after["mastery"] > before["mastery"]
    assert after["level"] >= before["level"]


def test_mastery_changes_combat_power_and_internal_energy_cost():
    player = join("武当")
    assert player.get_skill_progress("太极剑")["learned"]
    low = next(skill for skill in player.get_available_skills() if skill["name"] == "太极剑")

    for _ in range(8):
        player.record_skill_use("太极剑", success=True)
    high_progress = player.get_skill_progress("太极剑")
    high = next(skill for skill in player.get_available_skills() if skill["name"] == "太极剑")

    assert high_progress["mastery"] == 81
    assert high_progress["level"] == 5
    assert high["power"] > low["power"]
    assert high["mp_cost"] < low["mp_cost"]


def test_high_level_skill_still_requires_character_level_reputation_and_official_rank():
    player = join("少林")
    player.level = 1
    ok, reason = player.can_learn_skill("金刚伏魔拳")
    assert not ok and "等级不足" in reason

    player.level = 10
    player.change_sect_reputation("少林", 100)
    # 新存档已有正式身份记录时，声望本身不能替代正式晋升。
    ok, reason = player.can_learn_skill("金刚伏魔拳")
    assert not ok and "正式晋升" in reason


def test_learned_skill_remains_available_after_leaving_teaching_location():
    player = join("华山")
    assert player.get_skill_progress("华山剑法")["learned"]
    player.location = "main_square"

    available = player.get_available_skills()
    assert any(skill["name"] == "华山剑法" for skill in available)
    assert player.get_skill_progress("华山剑法")["learned"]


def test_old_style_saved_skill_state_keeps_mastery_and_learned_flag():
    player = join("武当")
    assert player.get_skill_progress("太极剑")["learned"]
    for _ in range(3):
        player.record_skill_use("太极剑", success=True)

    # 模拟 V12 存档中的武学状态原样读回：熟练度和已学标记均应保留。
    saved_state = dict(player._skill_state()["太极剑"])
    player._skill_state()["太极剑"] = saved_state
    progress = player.get_skill_progress("太极剑")
    assert progress["learned"] is True
    assert progress["mastery"] == saved_state["mastery"]
