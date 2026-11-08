"""四门派收束：少林/武当/华山/铁衣门终章的三结局、区域后果与条件台词。"""
import contextlib
import io
import json
from pathlib import Path

import pytest

import engine
import region_activity
from actions import handle_quest, handle_talk_and_ask
from player import Player

ROOT = Path(__file__).resolve().parents[1]
SECTS = json.loads((ROOT / "data" / "quests.json").read_text(encoding="utf-8"))

CASES = {
    "少林": {
        "quest": "少林收束·戒律与慈悲",
        "giver": "少林戒律僧",
        "second": "少林守山僧",
        "zone": "shaolin_mountain",
        "prereqs": ["少林戒律·问心持戒", "少林护寺·山门驱谍"],
        "flag_a": "sect:shaolin:discipline:precepts",
        "flag_b": "sect:shaolin:discipline:guard",
        "choices": ["precepts_line", "guard_line", "middle_line"],
        "titles": ["守住戒律", "护人即持戒", "戒护并重"],
        "started": "quest:shaolin_closure:started",
        "gold": {"precepts_line": 100, "guard_line": 80, "middle_line": 90},
        "honor": {"precepts_line": 4, "guard_line": 6, "middle_line": 5},
        "infamy": {"precepts_line": 0, "guard_line": 0, "middle_line": 0},
        "rep": {"precepts_line": 28, "guard_line": 22, "middle_line": 20},
        "region": {
            "precepts_line": {"security": 6, "commerce": -2, "travel": -3},
            "guard_line": {"security": -2, "commerce": 5, "travel": 6},
            "middle_line": {"security": 3, "commerce": 2, "travel": 2},
        },
        "item": {"precepts_line": "菩提念珠", "guard_line": "金创药", "middle_line": "清心散"},
        "faction": {
            "precepts_line": ("少林", "官府", 3),
            "guard_line": ("少林", "江湖", 4),
            "middle_line": ("少林", "江湖", 2),
        },
        "relation": {
            "precepts_line": ("少林戒律僧", 4),
            "guard_line": ("少林守山僧", 3),
            "middle_line": ("少林戒律僧", 4),
        },
        "world": {
            "precepts_line": "world:shaolin:closure_precepts",
            "guard_line": "world:shaolin:closure_guard",
            "middle_line": "world:shaolin:closure_middle",
        },
        "giver_line": {
            "precepts_line": "寺门重归清规",
            "guard_line": "你护住了山门",
            "middle_line": "戒律与慈悲并非两条路",
        },
        "second_line": "今日起入寺先验度牒",
        "active_line": "流民还在山门外",
        "base_line": "戒律并非束缚",
    },
    "武当": {
        "quest": "武当收束·剑理与内功",
        "giver": "武当传功师父",
        "second": "武当守山弟子",
        "zone": "wudang_mountain",
        "prereqs": ["武当剑理·松间问道", "武当内功·紫霄听息"],
        "flag_a": "sect:wudang:sword_principle:observe",
        "flag_b": "sect:wudang:sword_principle:direct",
        "choices": ["observe_line", "direct_line", "middle_line"],
        "titles": ["以静观变", "以意驭剑", "剑理合一"],
        "started": "quest:wudang_closure:started",
        "gold": {"observe_line": 95, "direct_line": 70, "middle_line": 85},
        "honor": {"observe_line": 3, "direct_line": 5, "middle_line": 4},
        "infamy": {"observe_line": 0, "direct_line": 0, "middle_line": 0},
        "rep": {"observe_line": 28, "direct_line": 22, "middle_line": 20},
        "region": {
            "observe_line": {"security": 4, "commerce": 1, "travel": 3},
            "direct_line": {"security": 7, "commerce": 3, "travel": -2},
            "middle_line": {"security": 5, "commerce": 2, "travel": 1},
        },
        "item": {"observe_line": "太极剑穗", "direct_line": "清心散", "middle_line": "清心散"},
        "faction": {
            "observe_line": ("武当", "江湖", 3),
            "direct_line": ("武当", "官府", 3),
            "middle_line": ("武当", "江湖", 2),
        },
        "relation": {
            "observe_line": ("武当传功师父", 4),
            "direct_line": ("武当守山弟子", 4),
            "middle_line": ("武当传功师父", 3),
        },
        "world": {
            "observe_line": "world:wudang:closure_observe",
            "direct_line": "world:wudang:closure_direct",
            "middle_line": "world:wudang:closure_middle",
        },
        "giver_line": {
            "observe_line": "你先看清了局势",
            "direct_line": "以意驭剑，先发也能制人",
            "middle_line": "剑理与内功本是一体",
        },
        "second_line": "师父让我们先盯住山道",
        "active_line": "商队还在山下等着说法",
        "base_line": "太极剑不争一时锋芒",
    },
    "华山": {
        "quest": "华山收束·剑锋与古道",
        "giver": "华山传功师兄",
        "second": "华山守门弟子",
        "zone": "huashan_mountain",
        "prereqs": ["华山剑理·松风听剑", "华山巡剑·古道清障"],
        "flag_a": "sect:huashan:sword_principle:speed",
        "flag_b": "sect:huashan:sword_principle:steady",
        "choices": ["speed_line", "steady_line", "middle_line"],
        "titles": ["快剑立威", "守剑护道", "快守相济"],
        "started": "quest:huashan_closure:started",
        "gold": {"speed_line": 110, "steady_line": 85, "middle_line": 95},
        "honor": {"speed_line": 2, "steady_line": 6, "middle_line": 4},
        "infamy": {"speed_line": 1, "steady_line": 0, "middle_line": 0},
        "rep": {"speed_line": 28, "steady_line": 23, "middle_line": 20},
        "region": {
            "speed_line": {"security": 4, "commerce": 3, "travel": -2},
            "steady_line": {"security": 6, "commerce": 1, "travel": 4},
            "middle_line": {"security": 5, "commerce": 2, "travel": 1},
        },
        "item": {"speed_line": "华山剑穗", "steady_line": "行军干粮", "middle_line": "行军干粮"},
        "faction": {
            "speed_line": ("华山", "商会", 4),
            "steady_line": ("华山", "官府", 3),
            "middle_line": ("华山", "商会", 2),
        },
        "relation": {
            "speed_line": ("华山传功师兄", 3),
            "steady_line": ("华山守门弟子", 4),
            "middle_line": ("华山传功师兄", 3),
        },
        "world": {
            "speed_line": "world:huashan:closure_speed",
            "steady_line": "world:huashan:closure_steady",
            "middle_line": "world:huashan:closure_middle",
        },
        "giver_line": {
            "speed_line": "快剑立威，古道上的匪人",
            "steady_line": "你守住了古道",
            "middle_line": "快慢本无定法",
        },
        "second_line": "师兄让咱们把剑亮出来",
        "active_line": "古道上的商旅还在等",
        "base_line": "练剑切忌贪快",
    },
    "铁衣门": {
        "quest": "铁衣门收束·行规与义护",
        "giver": "铁衣门护运执事",
        "second": "铁衣门接引执事",
        "zone": "tieyi_mountain",
        "prereqs": ["铁衣门护运·商路问价", "铁衣门守约·短途护送"],
        "flag_a": "sect:tieyi:trade_route:fair",
        "flag_b": "sect:tieyi:trade_route:secure",
        "choices": ["fair_line", "secure_line", "middle_line"],
        "titles": ["行规为先", "义护为先", "行义两全"],
        "started": "quest:tieyi_closure:started",
        "gold": {"fair_line": 150, "secure_line": 60, "middle_line": 100},
        "honor": {"fair_line": 1, "secure_line": 6, "middle_line": 3},
        "infamy": {"fair_line": 1, "secure_line": 0, "middle_line": 0},
        "rep": {"fair_line": 28, "secure_line": 22, "middle_line": 20},
        "region": {
            "fair_line": {"security": 2, "commerce": 6, "travel": 1},
            "secure_line": {"security": 5, "commerce": -2, "travel": 4},
            "middle_line": {"security": 4, "commerce": 2, "travel": 3},
        },
        "item": {"fair_line": "铁衣护腕", "secure_line": "金创药", "middle_line": "行军干粮"},
        "faction": {
            "fair_line": ("铁衣门", "商会", 5),
            "secure_line": ("铁衣门", "江湖", 4),
            "middle_line": ("铁衣门", "商会", 2),
        },
        "relation": {
            "fair_line": ("铁衣门护运执事", 3),
            "secure_line": ("铁衣门接引执事", 1),
            "middle_line": ("铁衣门护运执事", 4),
        },
        "world": {
            "fair_line": "world:tieyi:closure_fair",
            "secure_line": "world:tieyi:closure_secure",
            "middle_line": "world:tieyi:closure_middle",
        },
        "giver_line": {
            "fair_line": "按行规收价",
            "secure_line": "这趟少收的银子",
            "middle_line": "该收的收，该让的让",
        },
        "second_line": "货单照公价誊清了",
        "active_line": "那桩赔本镖还压在案上",
        "base_line": "门派要在江湖立足",
    },
}


def capture(fn, *args):
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        fn(*args)
    return stream.getvalue()


def _patch(player, monkeypatch, npcs):
    monkeypatch.setattr(Player, "save_to_file", lambda self, filename=None, verbose=True: True)
    monkeypatch.setattr(Player, "get_npcs_in_room", lambda self, location=None: list(npcs))


def _prepare(sect, cfg, monkeypatch, flags=(), level=6, reputation=40):
    player = Player(f"{sect}收束验收", sect)
    player.level = level
    player.change_sect_reputation(sect, reputation)
    player.completed_quests.extend(cfg["prereqs"])
    for flag in flags:
        player.set_flag(flag, True)
    _patch(player, monkeypatch, [cfg["giver"]])
    return player


def _start(sect, cfg, monkeypatch, flags=(), level=6, reputation=40):
    player = _prepare(sect, cfg, monkeypatch, flags=flags, level=level, reputation=reputation)
    player.active_quests[cfg["quest"]] = 1
    player.quest_states[cfg["quest"]] = {"stage": 2, "progress": 1}
    player.set_flag(f"quest_active:{cfg['quest']}", True)
    return player


def _eligible(player, cfg):
    return [
        choice["id"]
        for choice in SECTS[cfg["quest"]]["choices"]
        if engine.check_conditions(choice.get("requires"), player.world_state, player.completed_quests, player)
    ]


def _faction(player, first, second):
    key = f"{first}:{second}"
    relations = player.world_state.get("variables", {}).get("faction_relations", {})
    if key in relations:
        return relations[key]
    return engine.FACTIONS.get(first, {}).get("relations", {}).get(second, 0)


def _relation(player, npc):
    return player.world_state.get("variables", {}).get("npc_relations", {}).get(npc, 0)


@pytest.mark.parametrize("sect", list(CASES))
def test_closure_quest_requires_prior_choice_and_offers_third_path(sect):
    cfg = CASES[sect]
    quest = SECTS[cfg["quest"]]

    assert quest["npc"] == cfg["giver"]
    assert quest["turn_in_npc"] == cfg["giver"]
    assert quest["requires"]["sect"] == sect
    assert quest["requires"]["level"] == 6
    assert quest["requires"]["sect_reputation"][sect]["gte"] == 30
    assert set(quest["requires"]["completed_quests"]) == set(cfg["prereqs"])
    assert [stage["target_name"] for stage in quest["stages"]] == [cfg["second"], "劫镖山贼" if sect != "少林" else "黑风寨精锐", cfg["giver"]]
    assert [choice["id"] for choice in quest["choices"]] == cfg["choices"]
    assert [choice["title"] for choice in quest["choices"]] == cfg["titles"]
    assert quest["choices"][0]["requires"]["flags"] == [cfg["flag_a"]]
    assert quest["choices"][1]["requires"]["flags"] == [cfg["flag_b"]]
    assert quest["choices"][2]["requires"] == {}


@pytest.mark.parametrize("sect", list(CASES))
def test_closure_eligibility_follows_earlier_branch(sect, monkeypatch):
    cfg = CASES[sect]
    a_player = _start(sect, cfg, monkeypatch, flags=[cfg["flag_a"]])
    b_player = _start(sect, cfg, monkeypatch, flags=[cfg["flag_b"]])
    none_player = _start(sect, cfg, monkeypatch)

    assert _eligible(a_player, cfg) == [cfg["choices"][0], cfg["choices"][2]]
    assert _eligible(b_player, cfg) == [cfg["choices"][1], cfg["choices"][2]]
    assert _eligible(none_player, cfg) == [cfg["choices"][2]]


@pytest.mark.parametrize("sect", list(CASES))
def test_closure_acceptance_checks_sect_level_and_reputation(sect, monkeypatch):
    cfg = CASES[sect]
    valid = _prepare(sect, cfg, monkeypatch)
    assert "已接取任务" in capture(handle_quest, valid, "jiequ", [cfg["quest"]])
    assert valid.get_flag(cfg["started"]) is True

    wrong_sect = Player(f"{sect}非本门", "散人")
    wrong_sect.level = 6
    wrong_sect.completed_quests.extend(cfg["prereqs"])
    _patch(wrong_sect, monkeypatch, [cfg["giver"]])
    assert "接取失败" in capture(handle_quest, wrong_sect, "jiequ", [cfg["quest"]])
    assert cfg["quest"] not in wrong_sect.active_quests

    low_level = _prepare(sect, cfg, monkeypatch, level=5)
    assert "接取失败" in capture(handle_quest, low_level, "jiequ", [cfg["quest"]])

    low_rep = _prepare(sect, cfg, monkeypatch, reputation=10)
    assert "接取失败" in capture(handle_quest, low_rep, "jiequ", [cfg["quest"]])


@pytest.mark.parametrize("sect", list(CASES))
@pytest.mark.parametrize("choice_id", ["a", "b", "middle"])
def test_closure_endings_apply_rewards_and_world_consequences(sect, choice_id, monkeypatch):
    cfg = CASES[sect]
    key = cfg["choices"][{"a": 0, "b": 1, "middle": 2}[choice_id]]
    flag = {"a": cfg["flag_a"], "b": cfg["flag_b"], "middle": None}[choice_id]
    player = _start(sect, cfg, monkeypatch, flags=[flag] if flag else [])

    gold_before = player.gold
    honor_before = player._jianghu_profile()["honor"]
    infamy_before = player._jianghu_profile()["infamy"]
    rep_before = player.get_sect_reputation(sect)
    faction_first, faction_second, faction_delta = cfg["faction"][key]
    faction_before = _faction(player, faction_first, faction_second)
    relation_npc, relation_delta = cfg["relation"][key]
    relation_before = _relation(player, relation_npc)

    output = capture(handle_quest, player, "jiaofu", [f"{cfg['quest']}|{key}"])

    assert "恭喜完成任务" in output
    assert cfg["quest"] in player.completed_quests
    assert player.gold == gold_before + cfg["gold"][key]
    assert player._jianghu_profile()["honor"] == honor_before + cfg["honor"][key]
    assert player._jianghu_profile()["infamy"] == infamy_before + cfg["infamy"][key]
    assert player.get_sect_reputation(sect) == rep_before + cfg["rep"][key]
    assert cfg["item"][key] in player.inventory
    assert player.get_flag(cfg["world"][key]) is True
    assert region_activity.get_permanent_region_delta(player, cfg["zone"]) == cfg["region"][key]
    assert _faction(player, faction_first, faction_second) == faction_before + faction_delta
    assert _relation(player, relation_npc) == relation_before + relation_delta

    zone_name = engine.WORLD_REGIONS[cfg["zone"]]["name"]
    parts = []
    for field, label in (("security", "安全度"), ("commerce", "商路"), ("travel", "通行")):
        delta = cfg["region"][key][field]
        if delta:
            parts.append(f"{label} {delta:+d}")
    assert f"区域变化：{zone_name} {'、'.join(parts)}" in output


@pytest.mark.parametrize("sect", list(CASES))
def test_closure_prompts_when_both_branches_are_available(sect, monkeypatch):
    cfg = CASES[sect]
    player = _start(sect, cfg, monkeypatch, flags=[cfg["flag_a"], cfg["flag_b"]])
    gold_before = player.gold

    output = capture(handle_quest, player, "jiaofu", [cfg["quest"]])

    assert "请选择任务结局" in output
    for title in cfg["titles"]:
        assert title in output
    assert cfg["quest"] in player.active_quests
    assert player.gold == gold_before


@pytest.mark.parametrize("sect", list(CASES))
def test_closure_npc_lines_follow_final_choice(sect, monkeypatch):
    cfg = CASES[sect]
    for key, expected in cfg["giver_line"].items():
        player = Player(f"{sect}结局台词", sect)
        player.set_flag(cfg["world"][key], True)
        _patch(player, monkeypatch, [cfg["giver"]])
        output = capture(handle_talk_and_ask, player, [cfg["giver"]])
        assert expected in output

    second_player = Player(f"{sect}山门台词", sect)
    second_player.set_flag(cfg["world"][cfg["choices"][0]], True)
    _patch(second_player, monkeypatch, [cfg["second"]])
    assert cfg["second_line"] in capture(handle_talk_and_ask, second_player, [cfg["second"]])


@pytest.mark.parametrize("sect", list(CASES))
def test_closure_active_and_base_dialogue(sect, monkeypatch):
    cfg = CASES[sect]
    active = Player(f"{sect}进行中台词", sect)
    active.set_flag(f"quest_active:{cfg['quest']}", True)
    _patch(active, monkeypatch, [cfg["giver"]])
    assert cfg["active_line"] in capture(handle_talk_and_ask, active, [cfg["giver"]])

    base = Player(f"{sect}基础台词", sect)
    _patch(base, monkeypatch, [cfg["giver"]])
    output = capture(handle_talk_and_ask, base, [cfg["giver"]])
    assert cfg["base_line"] in output
    for line in cfg["giver_line"].values():
        assert line not in output
