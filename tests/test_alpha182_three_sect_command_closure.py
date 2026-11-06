"""Alpha182：少林、武当、华山门派武学实际指令闭环验收。"""
import contextlib
import io

import engine
from actions import handle_sect, handle_skills
from player import Player

SECTS = {
    "少林": ("shaolin_training_ground", "少林传功师兄", "般若掌"),
    "武当": ("wudang_training_ground", "武当传功师兄", "绵掌"),
    "华山": ("huashan_training_ground", "华山传功师兄", "夺命连环三仙剑"),
}


def capture(fn, *args):
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        fn(*args)
    return output.getvalue()


def prepared_disciple(sect):
    player = Player(f"{sect}指令闭环测试", "散人")
    assert player.join_sect(sect)[0]
    player.level = 30
    player.change_sect_reputation(sect, 1000)
    player._sect_progress_state().setdefault(sect, {})["official_rank_index"] = 2
    return player


def test_advanced_skill_command_requires_correct_training_ground_and_teacher_for_each_sect():
    for sect, (room_id, teacher, skill) in SECTS.items():
        player = prepared_disciple(sect)
        player._ensure_skill_state()[skill] = {"learned": False, "mastery": 0}

        player.location = next(room_id_other for room_id_other in engine.ROOMS if room_id_other != room_id and not room_id_other.startswith(("shaolin_", "wudang_", "huashan_")))
        output = capture(handle_skills, player, ["学习", skill])
        assert "前往" in output, f"{sect}应提示正确传功地点：{output}"
        assert not player.get_skill_progress(skill)["learned"]

        player.location = room_id
        original_get_npcs = player.get_npcs_in_room
        try:
            player.get_npcs_in_room = lambda target=None: [name for name in original_get_npcs(target) if name != teacher]
            output = capture(handle_skills, player, ["学习", skill])
            assert ("暂时无法" in output or "暂时没有" in output), f"{sect}缺少传功师兄时应拒绝学习：{output}"
            assert not player.get_skill_progress(skill)["learned"]
        finally:
            player.get_npcs_in_room = original_get_npcs

        output = capture(handle_skills, player, ["学习", skill])
        assert "已学会" in output, f"{sect}满足身份、声望、地点和师长条件后应能学习：{output}"
        assert player.get_skill_progress(skill)["learned"]


def test_sect_study_command_requires_the_real_teaching_npc_and_obeys_cooldown():
    teaching = {
        "少林": ("shaolin_training_ground", "少林传功师父"),
        "武当": ("wudang_training_ground", "武当传功师父"),
        "华山": ("huashan_training_ground", "华山授业师父"),
    }
    for sect, (room_id, teacher) in teaching.items():
        player = prepared_disciple(sect)
        player.change_sect_reputation(sect, -900)
        player.location = room_id
        original_get_npcs = player.get_npcs_in_room
        try:
            player.get_npcs_in_room = lambda target=None: [name for name in original_get_npcs(target) if name != teacher]
            output = capture(handle_sect, player, ["修习"])
            assert "不在场" in output or "暂时无法" in output, f"{sect}缺少授业师长时应拒绝修习：{output}"
        finally:
            player.get_npcs_in_room = original_get_npcs

        before = player.get_sect_reputation(sect)
        output = capture(handle_sect, player, ["修习"])
        assert "声望提升 5" in output
        assert player.get_sect_reputation(sect) == before + 5
        output = capture(handle_sect, player, ["修习"])
        assert "再历练" in output, f"{sect}修习冷却未生效：{output}"
