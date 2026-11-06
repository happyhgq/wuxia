"""Alpha150：门派身份正式授阶与晋升考核。"""
import contextlib
import io

from actions import handle_sect
from player import Player


def capture(fn, *args):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        fn(*args)
    return out.getvalue()


def enrolled_player():
    p = Player("晋升测试", "散人")
    p.level = 3
    assert p.join_sect("华山")[0]
    p.location = "huashan_training_ground"
    return p


def test_new_member_starts_at_formal_named_disciple_even_with_reputation_rank_separate():
    p = enrolled_player()
    p.change_sect_reputation("华山", 50)
    assert p.get_sect_rank() == "内门弟子"  # legacy reputation-derived view remains compatible
    assert p.get_sect_official_rank() == "记名弟子"
    assert p._skill_rank_index("华山") == 0


def test_promotion_requires_training_ground_and_instructor():
    p = enrolled_player()
    p.change_sect_reputation("华山", 20)
    p.record_skill_use("华山剑法")
    p.location = "huashan_guest_hall"
    out = capture(handle_sect, p, ["晋升"])
    assert "演武场" in out
    assert p.get_sect_official_rank() == "记名弟子"


def test_promotion_requires_reputation_level_and_basic_skill_practice():
    p = enrolled_player()
    out = capture(handle_sect, p, ["晋升"])
    assert "声望" in out and "熟练度" in out
    assert p.get_sect_official_rank() == "记名弟子"


def test_first_promotion_records_official_rank_and_unlocks_rank_gated_skill_condition():
    p = enrolled_player()
    p.change_sect_reputation("华山", 20)
    p.record_skill_use("华山剑法")
    p.set_flag("sect:huashan:sword_principle", True)
    out = capture(handle_sect, p, ["晋升"])
    assert "外门弟子" in out
    assert p.get_sect_official_rank() == "外门弟子"
    assert p._skill_rank_index("华山") == 1
    assert p._sect_state()["progress"]["华山"]["promotion_history"][-1]["rank"] == "外门弟子"


def test_legacy_character_without_formal_promotion_record_keeps_v12_rank_behavior():
    p = Player("旧档角色", "华山")
    p.change_sect_reputation("华山", 50)
    assert p.get_sect_official_rank() == "内门弟子"
    assert p._skill_rank_index("华山") == 2


def test_huashan_council_hall_requires_official_inner_disciple_rank():
    from travel_system import room_access_denial
    p = enrolled_player()
    room = __import__("engine").ROOMS["huashan_master_hall"]
    assert "内门弟子" in room_access_denial(p, room)
    p.change_sect_reputation("华山", 20)
    p.record_skill_use("华山剑法")
    p.set_flag("sect:huashan:sword_principle", True)
    assert p.promote_sect_rank()[0]
    p.change_sect_reputation("华山", 30)
    p.level = 8
    p.record_skill_use("华山剑法")
    p.record_skill_use("华山剑法")
    assert "内门弟子" in room_access_denial(p, room)
    # 晋升到内门后才开放议事堂
    p.set_flag("sect:huashan:questline:patrol_done", True)
    assert p.promote_sect_rank()[0]
    assert room_access_denial(p, room) == ""


def test_higher_rank_requires_mentor_trust_without_affecting_earlier_promotions():
    p = enrolled_player()
    # 达到外门、内门所需的既有条件，确保前两次晋升规则保持兼容。
    p.change_sect_reputation("华山", 50)
    for _ in range(10):
        p.record_skill_use("华山剑法")
    p.set_flag("sect:huashan:sword_principle", True)
    assert p.promote_sect_rank()[0]
    p.level = 8
    for _ in range(30):
        p.record_skill_use("华山剑法")
    p.set_flag("sect:huashan:questline:patrol_done", True)
    assert p.promote_sect_rank()[0]
    p.level = 15
    p.change_sect_reputation("华山", 50)
    for _ in range(30):
        p.record_skill_use("华山剑法")
    req = p.get_sect_promotion_requirements()
    assert req["required_mentor_bond"] == 15
    ok, message = p.promote_sect_rank()
    assert not ok and "师承认可" in message
    p.establish_sect_mentorship()
    p.get_sect_mentorship("华山")["bond"] = 15
    # 真传考核除师承认可外，还需完成本门历练，不能只靠声望累积晋升。
    ok, message = p.promote_sect_rank()
    assert not ok and "华山历练·磨剑黑风" in message
    p.completed_quests.append("华山历练·磨剑黑风")
    assert p.promote_sect_rank()[0]
