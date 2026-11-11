"""Alpha159：少林专属身份阶位、受戒仪礼与人物面板。"""
import contextlib
import io

import engine
from actions import handle_sect
from main import show_status
from player import Player


def joined_shaolin():
    p = Player("少林身份测试", "散人")
    p.level = max(p.level, 3)
    assert p.join_sect("少林")[0]
    return p


def capture(fn, *args):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        fn(*args)
    return out.getvalue()


def test_shaolin_uses_distinct_identity_names_without_changing_other_sects():
    p = joined_shaolin()
    assert p.get_sect_official_rank() == "俗家弟子"
    w = Player("武当测试", "散人")
    w.level = max(w.level, 3)
    assert w.join_sect("武当")[0]
    assert w.get_sect_official_rank() == "记名弟子"


def test_shaolin_status_panel_uses_identity_label_and_no_training_direction():
    p = joined_shaolin()
    output = capture(show_status, p, "sect")
    assert "门派身份" in output
    assert "俗家弟子" in output
    assert "师承" in output and "暂无师承" in output
    assert "修习方向" not in output
    assert "师徒关系" not in output


def test_shaolin_cannot_promote_to_novice_without_ordination():
    p = joined_shaolin()
    p.level = 5
    p.change_sect_reputation("少林", 20)
    for _ in range(10):
        p.record_skill_use("罗汉拳")
    ok, message = p.promote_sect_rank()
    assert not ok
    assert "受戒仪礼" in message
    assert p.get_sect_official_rank() == "俗家弟子"


def test_shaolin_ordination_is_location_npc_and_practice_gated_then_allows_promotion():
    p = joined_shaolin()
    p.level = 5
    p.change_sect_reputation("少林", 20)
    for _ in range(10):
        p.record_skill_use("罗汉拳")
    p.location = "shaolin_dharma_hall"
    assert "少林戒律僧" in p.get_npcs_in_room(p.location)
    output = capture(handle_sect, p, ["受戒"])
    assert "仪礼已记录" in output
    assert p.get_flag("sect:shaolin:ordination:novice", False)
    p.location = "shaolin_training_ground"
    output = capture(handle_sect, p, ["晋升"])
    assert "沙弥" in output
    assert p.get_sect_official_rank() == "沙弥"


def test_shaolin_full_ordination_required_before_becoming_monk():
    p = joined_shaolin()
    p._sect_progress_state().setdefault("少林", {})["official_rank_index"] = 1
    p.level = 10
    p.change_sect_reputation("少林", 50)
    for _ in range(30):
        p.record_skill_use("罗汉拳")
    ok, message = p.promote_sect_rank()
    assert not ok and "受戒仪礼" in message
    p.location = "shaolin_dharma_hall"
    assert "少林戒律僧" in p.get_npcs_in_room(p.location)
    output = capture(handle_sect, p, ["受戒"])
    assert "正式受戒" in output
    p.location = "shaolin_training_ground"
    output = capture(handle_sect, p, ["晋升"])
    assert "僧人" in output
    assert p.get_sect_official_rank() == "僧人"
