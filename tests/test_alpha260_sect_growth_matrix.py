"""Alpha260：收尾前核查门派入门、授课、晋升与高阶武学门槛的闭环。"""
import contextlib
import io
import json
from pathlib import Path

import engine
from actions import handle_sect, handle_skills
from player import Player

ROOT = Path(__file__).resolve().parents[1]
SECT_ENTRY = {
    "少林": ("shaolin_guest_hall", "sect:shaolin:entry_interview"),
    "武当": ("wudang_guest_hall", "sect:wudang:entry_interview"),
    "华山": ("huashan_guest_hall", "sect:huashan:entry_interview"),
    "铁衣门": ("tieyi_guest_hall", "sect:tieyi:entry_interview"),
}


def run_capture(fn, *args):
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        fn(*args)
    return stream.getvalue()


def test_formal_sect_admission_requires_level_three_for_all_four_sects():
    for sect, (room, interview_flag) in SECT_ENTRY.items():
        player = Player(f"入门门槛-{sect}", "散人")
        player.location = room
        player.set_flag(interview_flag, True)
        player.level = 2
        output = run_capture(handle_sect, player, ["拜师", sect])
        assert "需达到 3 级" in output, (sect, output)
        assert player.get_sect() == "散人"

        player.level = 3
        output = run_capture(handle_sect, player, ["拜师", sect])
        assert player.get_sect() == sect, (sect, output)
        assert "正式拜入" in output


def test_every_sect_skill_has_consistent_rank_and_teaching_gates():
    sects = json.loads((ROOT / "data" / "sects.json").read_text(encoding="utf-8"))
    for sect in ("少林", "武当", "华山", "铁衣门"):
        config = sects[sect]
        teacher_map = config["skill_teachers"]
        training = config["training"]
        ranks = config["ranks"]
        for skill in engine.SKILLS[sect]:
            name = skill["name"]
            player = Player(f"武学门槛-{sect}-{name}", sect)
            player.level = 60
            player.change_sect_reputation(sect, 1000)
            player._sect_progress_state().setdefault(sect, {})["official_rank_index"] = len(ranks) - 1
            if player.get_skill_progress(name)["learned"]:
                player.forget_skill(name)
            rank_need = int(skill.get("learn_min_rank", 0) or 0)
            if rank_need > 0:
                player._sect_progress_state().setdefault(sect, {})["official_rank_index"] = rank_need - 1
                allowed, reason = player.can_learn_skill(name)
                assert not allowed and "身份不足" in reason, (sect, name, reason)
                player._sect_progress_state().setdefault(sect, {})["official_rank_index"] = len(ranks) - 1
            assert player.can_learn_skill(name)[0], (sect, name, player.can_learn_skill(name))

            # 即使角色满足等级、声望与职位，离开指定演武场也不能直接学习。
            player.location = "village_square"
            blocked = run_capture(handle_skills, player, ["学习", name])
            assert "须前往" in blocked, (sect, name, blocked)
            assert not player.get_skill_progress(name)["learned"]

            # 回到演武场后，必须有配置的授课师长在场才可学习。
            player.location = training["room_id"]
            room_npcs = engine.ROOMS[training["room_id"]].get("npcs", [])
            teacher = teacher_map[name]
            assert teacher in room_npcs, (sect, name, teacher, room_npcs)
            learned = run_capture(handle_skills, player, ["学习", name])
            assert "已学会" in learned, (sect, name, learned)
            assert player.get_skill_progress(name)["learned"]


def test_all_promotion_rules_reference_existing_quests_and_valid_rank_steps():
    quests = json.loads((ROOT / "data" / "quests.json").read_text(encoding="utf-8"))
    quest_names = set()
    if isinstance(quests, list):
        quest_names = {q.get("name") for q in quests if isinstance(q, dict)}
    elif isinstance(quests, dict):
        quest_names = {q.get("name", key) for key, q in quests.items() if isinstance(q, dict)}
    for sect in ("少林", "武当", "华山", "铁衣门"):
        info = engine.SECTS[sect]
        ranks = info["ranks"]
        requirements = info["promotion_requirements"]
        assert len(ranks) == 5
        assert set(requirements) >= {"1", "2", "3", "4"}
        for step in range(1, len(ranks)):
            rule = requirements[str(step)]
            assert int(rule["level"]) >= 1
            assert int(rule["mastery"]) >= 0
        # 晋升中引用的历练任务必须存在，避免角色满足其他条件后永久卡死。
        player = Player(f"晋升规则-{sect}", sect)
        for target in range(3, len(ranks) + 1):
            req = player.get_sect_promotion_requirements(sect)
            for quest_name in req.get("required_quests", []):
                assert quest_name in quest_names, (sect, quest_name)
            # 只推进审计副本的职位索引，不触碰真实存档。
            player._sect_progress_state().setdefault(sect, {})["official_rank_index"] = target - 1
