"""Alpha180：少林、武当、华山的地图、身份、武学和晋升条件联合验收。"""
import json
from pathlib import Path

import engine
from player import Player
from travel_system import room_access_denial

ROOT = Path(__file__).resolve().parents[1]

SECTS = {
    "少林": {
        "prefix": "shaolin_", "entry": "shaolin_gate",
        "high_room": "shaolin_dharma_hall", "required_rank": 2,
        "skills": ["罗汉拳", "般若掌", "金刚伏魔拳"],
        "trial": "少林历练·黑风除恶",
    },
    "武当": {
        "prefix": "wudang_", "entry": "wudang_foothill",
        "high_room": "wudang_zhenwu_hall", "required_rank": 2,
        "skills": ["太极剑", "绵掌", "两仪剑诀"],
        "trial": "武当历练·以静制动",
    },
    "华山": {
        "prefix": "huashan_", "entry": "huashan_approach",
        "high_room": "huashan_master_hall", "required_rank": 2,
        "skills": ["华山剑法", "夺命连环三仙剑", "破玉剑式"],
        "trial": "华山历练·磨剑黑风",
    },
}


def _reachable_sect_rooms(prefix, start):
    seen, pending = {start}, [start]
    while pending:
        room_id = pending.pop()
        for target in (engine.ROOMS[room_id].get("exits") or {}).values():
            if target.startswith(prefix) and target not in seen:
                seen.add(target)
                pending.append(target)
    return seen


def test_all_three_sect_maps_are_connected_from_their_outer_entry():
    for sect, cfg in SECTS.items():
        expected = {rid for rid in engine.ROOMS if rid.startswith(cfg["prefix"])}
        reached = _reachable_sect_rooms(cfg["prefix"], cfg["entry"])
        assert reached == expected, f"{sect}地图存在无法从入口抵达的地点：{sorted(expected - reached)}"
        for rid in expected:
            for direction, target in (engine.ROOMS[rid].get("exits") or {}).items():
                assert target in engine.ROOMS, f"{sect}地点 {rid} 的{direction}出口指向不存在的地点 {target}"


def test_each_sect_has_matching_skill_data_and_its_own_promotion_trial():
    quests = json.loads((ROOT / "data" / "quests.json").read_text(encoding="utf-8"))
    for sect, cfg in SECTS.items():
        info = engine.SECTS[sect]
        assert len(info["ranks"]) == 5
        assert set(cfg["skills"]) <= set(info["exclusive_skills"])
        actual = {row["name"] for row in engine.SKILLS[sect]}
        assert set(cfg["skills"]) <= actual
        assert set(info["exclusive_skills"]) <= actual
        assert cfg["trial"] in quests
        assert quests[cfg["trial"]].get("requires", {}).get("sect") == sect


def test_guest_permission_and_wrong_sect_never_open_high_rank_rooms():
    for sect, cfg in SECTS.items():
        room = engine.ROOMS[cfg["high_room"]]
        guest = Player(f"访客-{sect}", "散人")
        guest.set_flag(f"sect:{sect}:guest_access", True)
        assert room_access_denial(guest, room)

        other = next(name for name in SECTS if name != sect)
        member = Player(f"异门-{sect}", "散人")
        member.level = max(member.level, 3)
        assert member.join_sect(other)[0]
        member._sect_progress_state().setdefault(sect, {})["official_rank_index"] = 4
        assert room_access_denial(member, room)


def test_rank_gated_skills_use_official_promotion_not_reputation_shortcut():
    for sect, cfg in SECTS.items():
        player = Player(f"武学门槛-{sect}", "散人")
        player.level = max(player.level, 3)
        assert player.join_sect(sect)[0]
        player.level = 30
        player.change_sect_reputation(sect, 1000)
        advanced_skill = cfg["skills"][1]
        ok, message = player.can_learn_skill(advanced_skill)
        assert not ok and "正式晋升" in message, f"{sect}高声望不应绕过正式授阶：{message}"

        player._sect_progress_state()[sect]["official_rank_index"] = 2
        ok, _ = player.can_learn_skill(advanced_skill)
        assert ok, f"{sect}达到对应正式身份后应满足身份条件"


def test_foreign_sect_skills_cannot_be_learned_after_joining_another_sect():
    for current, cfg in SECTS.items():
        player = Player(f"跨门派武学-{current}", "散人")
        player.level = max(player.level, 3)
        assert player.join_sect(current)[0]
        foreign = next(other for other in SECTS if other != current)
        foreign_skill = SECTS[foreign]["skills"][0]
        ok, message = player.can_learn_skill(foreign_skill)
        assert not ok and "并非你当前门派可学武学" in message


def test_character_panel_reports_formal_sect_identity_and_legacy_save_keeps_compatibility():
    for sect in SECTS:
        fresh = Player(f"新入门-{sect}", "散人")
        fresh.level = max(fresh.level, 3)
        assert fresh.join_sect(sect)[0]
        assert fresh.get_sect_summary()["rank"] == engine.SECTS[sect]["ranks"][0]["name"]

        legacy = Player(f"旧存档-{sect}", sect)
        legacy.change_sect_reputation(sect, 50)
        legacy._sect_progress_state().pop(sect, None)
        assert legacy.get_sect_official_rank(sect) == legacy.get_sect_rank(sect)
