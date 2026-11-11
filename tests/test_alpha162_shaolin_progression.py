"""Alpha162：少林高阶身份晋升与藏经规矩形成实际关联。"""
import contextlib
import io

from actions import handle_talk_and_ask
from player import Player


def capture(fn, *args):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        fn(*args)
    return out.getvalue()


def test_scripture_catalogue_dialogue_records_progress_flag():
    player = Player("藏经规矩测试", "少林")
    player.location = "shaolin_scripture_court"
    assert not player.get_flag("sect:shaolin:scripture_catalogue_reviewed", False)
    output = capture(handle_talk_and_ask, player, ["少林守阁僧", "藏经目录"])
    assert "经、律、论各有分门" in output
    assert player.get_flag("sect:shaolin:scripture_catalogue_reviewed", False)


def test_shaolin_highest_rank_requires_scripture_guidance_and_trial():
    player = Player("少林晋升测试", "散人")
    player.level = max(player.level, 3)
    assert player.join_sect("少林")[0]
    player._sect_progress_state().setdefault("少林", {})["official_rank_index"] = 3
    player.level = 30
    player.change_sect_reputation("少林", 200)
    for _ in range(100):
        player.record_skill_use("罗汉拳")
    player.completed_quests.append("少林历练·黑风除恶")
    req = player.get_sect_promotion_requirements("少林")
    assert req["target_rank"] == "少林传承弟子"
    assert "sect:shaolin:scripture_catalogue_reviewed" in req["required_flags"]
    ok, message = player.promote_sect_rank("少林")
    assert not ok and "藏经阁外院" in message
    player.set_flag("sect:shaolin:scripture_catalogue_reviewed", True)
    ok, message = player.promote_sect_rank("少林")
    assert ok, message
    assert player.get_sect_official_rank("少林") == "少林传承弟子"


def test_non_shaolin_promotion_does_not_inherit_shaolin_requirement():
    player = Player("门派隔离测试", "散人")
    player.level = max(player.level, 3)
    assert player.join_sect("武当")[0]
    player._sect_progress_state().setdefault("武当", {})["official_rank_index"] = 2
    player.level = 30
    player.change_sect_reputation("武当", 200)
    for _ in range(100):
        player.record_skill_use("太极剑")
    player.completed_quests.append("武当历练·以静制动")
    req = player.get_sect_promotion_requirements("武当")
    assert req["required_flags"] == []
