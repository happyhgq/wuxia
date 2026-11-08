"""归云三方中盘主线：探风、暗流交锋与定局三择的三方后果。"""
import contextlib
import io
import json
from pathlib import Path

import engine
import region_activity
from actions import _quest_npc_status, handle_quest, handle_talk_and_ask
from player import Player

PROBE = "归云三方·探风"
CLASH = "归云三方·暗流交锋"
ACCORD = "归云三方·定局三择"

PROBE_DONE = "quest:guiyun_threeway:probe_done"
CLASH_DONE = "quest:guiyun_threeway:clash_done"

ENDINGS = {
    "merchant_accord": {
        "title": "扶商宽市",
        "flag": "world:guiyun:threeway_merchant",
        "gold": 180,
        "item": "大还丹",
        "honor": 2,
        "infamy": 0,
        "region": {"security": -3, "commerce": 10, "travel": 5},
        "faction": ("江湖", "商会", 4),
        "relations": {"万商会会长": 5, "捕头": -2, "黑市管事": -1, "书生陆文清": 2},
        "report": "区域变化：归云城 安全度 -3、商路 +10、通行 +5",
    },
    "official_accord": {
        "title": "严法安城",
        "flag": "world:guiyun:threeway_official",
        "gold": 130,
        "item": "金创药",
        "honor": 6,
        "infamy": 0,
        "region": {"security": 10, "commerce": -4, "travel": 2},
        "faction": ("江湖", "官府", 4),
        "relations": {"捕头": 5, "府衙文书": 3, "万商会会长": -2, "黑市管事": -2, "书生陆文清": 2},
        "report": "区域变化：归云城 安全度 +10、商路 -4、通行 +2",
    },
    "underworld_accord": {
        "title": "夜市通融",
        "flag": "world:guiyun:threeway_underworld",
        "gold": 200,
        "item": "清心散",
        "honor": 0,
        "infamy": 2,
        "region": {"security": -7, "commerce": 3, "travel": 6},
        "faction": ("江湖", "黑市", 5),
        "relations": {"黑市管事": 5, "万商会会长": 1, "捕头": -3, "书生陆文清": 1},
        "report": "区域变化：归云城 安全度 -7、商路 +3、通行 +6",
    },
}

ENDING_FLAGS = [cfg["flag"] for cfg in ENDINGS.values()]


def _capture(callback, *args):
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        callback(*args)
    return stream.getvalue()


def _patch(monkeypatch, npc):
    monkeypatch.setattr(Player, "save_to_file", lambda self, filename=None, verbose=True: True)
    monkeypatch.setattr(Player, "get_npcs_in_room", lambda self, location=None: [npc])


def _accept(quest, player, npc, monkeypatch, location):
    _patch(monkeypatch, npc)
    player.location = location
    return _capture(handle_quest, player, "jiequ", [quest])


def _start(quest, player, stage, progress=1):
    player.active_quests[quest] = progress
    player.quest_states[quest] = {"stage": stage, "progress": progress}
    player.set_flag(f"quest_active:{quest}", True)


def _deliver(quest, player, npc, monkeypatch, choice=None):
    _patch(monkeypatch, npc)
    args = [quest if choice is None else f"{quest}|{choice}"]
    return _capture(handle_quest, player, "jiaofu", args)


def _eligible(quest, player):
    return [
        choice["id"]
        for choice in engine.QUESTS[quest]["choices"]
        if engine.check_conditions(choice.get("requires"), player.world_state, player.completed_quests, player)
    ]


def _talk(npc, flags, monkeypatch):
    _patch(monkeypatch, npc)
    player = Player("三方台词验收", "散人")
    for flag in flags:
        player.set_flag(flag, True)
    return _capture(handle_talk_and_ask, player, [npc])


def test_chain_ties_probe_clash_and_accord_to_existing_city_quests():
    quests = json.loads(Path("data/quests.json").read_text(encoding="utf-8"))
    npcs = json.loads(Path("data/npcs.json").read_text(encoding="utf-8"))

    assert quests[PROBE]["npc"] == "万商会会长"
    assert quests[PROBE]["requires"] == {"completed_quests": ["沉星黑市"], "level": 9}
    assert [stage["target_name"] for stage in quests[PROBE]["stages"]] == ["府衙文书", "黑市管事", "万商会会长"]

    assert quests[CLASH]["npc"] == "捕头"
    assert quests[CLASH]["requires"]["completed_quests"] == [PROBE]
    assert quests[CLASH]["requires"]["level"] == 10
    assert [stage["target_name"] for stage in quests[CLASH]["stages"]] == [
        "震远镖局总镖头", "劫镖山贼", "黑市管事", "捕头",
    ]
    assert quests[CLASH]["stages"][1]["required_cnt"] == 2

    assert quests[ACCORD]["npc"] == "书生陆文清"
    assert quests[ACCORD]["requires"]["completed_quests"] == [CLASH]
    assert quests[ACCORD]["requires"]["level"] == 11
    assert [stage["target_name"] for stage in quests[ACCORD]["stages"]] == [
        "万商会会长", "捕头", "黑市管事", "书生陆文清",
    ]
    assert [choice["id"] for choice in quests[ACCORD]["choices"]] == list(ENDINGS)
    assert [choice["title"] for choice in quests[ACCORD]["choices"]] == [ENDINGS[cid]["title"] for cid in ENDINGS]

    assert PROBE in npcs["万商会会长"]["quests"]
    assert CLASH in npcs["捕头"]["quests"]
    assert ACCORD in npcs["书生陆文清"]["quests"]


def test_probe_requires_black_market_completion_and_level_nine(monkeypatch):
    low = Player("三方探风等级不足", "散人")
    low.level = 8
    low.completed_quests.append("沉星黑市")
    output = _accept(PROBE, low, "万商会会长", monkeypatch, "guiyun_merchant_guild")
    assert "接取失败" in output
    assert PROBE not in low.active_quests

    missing = Player("三方未清黑市", "散人")
    missing.level = 9
    output = _accept(PROBE, missing, "万商会会长", monkeypatch, "guiyun_merchant_guild")
    assert "接取失败" in output
    assert PROBE not in missing.active_quests

    player = Player("三方探风接取", "散人")
    player.level = 9
    player.completed_quests.append("沉星黑市")
    _accept(PROBE, player, "万商会会长", monkeypatch, "guiyun_merchant_guild")
    assert PROBE in player.active_quests
    assert player.get_flag("quest:guiyun_threeway:probe_started") is True
    assert player.get_flag(f"quest_active:{PROBE}") is True


def test_probe_completion_sets_done_flag_rewards_and_relations(monkeypatch):
    player = Player("三方探风交付", "散人")
    _start(PROBE, player, 2)
    gold_before = player.gold
    honor_before = player._jianghu_profile()["honor"]
    guild_before = player.get_relation("万商会会长")
    clerk_before = player.get_relation("府衙文书")
    steward_before = player.get_relation("黑市管事")
    qingxin_before = player.inventory.count("清心散")

    output = _deliver(PROBE, player, "万商会会长", monkeypatch)

    assert PROBE in player.completed_quests
    assert player.get_flag(PROBE_DONE) is True
    assert player.gold - gold_before == 75
    assert player.inventory.count("清心散") - qingxin_before == 1
    assert player._jianghu_profile()["honor"] - honor_before == 1
    assert player.get_relation("万商会会长") - guild_before == 2
    assert player.get_relation("府衙文书") - clerk_before == 1
    assert player.get_relation("黑市管事") - steward_before == 1
    assert "区域变化" not in output


def test_clash_locked_until_probe_delivered(monkeypatch):
    player = Player("三方交锋未探风", "散人")
    player.level = 10
    output = _accept(CLASH, player, "捕头", monkeypatch, "guiyun_guard_camp")
    assert "接取失败" in output
    assert CLASH not in player.active_quests

    player.completed_quests.append(PROBE)
    output = _accept(CLASH, player, "捕头", monkeypatch, "guiyun_guard_camp")
    assert "接取失败" in output

    player.set_flag(PROBE_DONE, True)
    _accept(CLASH, player, "捕头", monkeypatch, "guiyun_guard_camp")
    assert CLASH in player.active_quests
    assert player.get_flag("quest:guiyun_threeway:clash_started") is True


def test_clash_offers_three_way_investigation_lean(monkeypatch):
    options = engine.QUESTS[CLASH]["stages"][0]["branch_choices"]
    assert [option["id"] for option in options] == ["official_lean", "merchant_lean", "underworld_lean"]

    expected = {
        "official_lean": ("world:guiyun:threeway_lean_official", "government_reputation"),
        "merchant_lean": ("world:guiyun:threeway_lean_merchant", "merchant_reputation"),
        "underworld_lean": ("world:guiyun:threeway_lean_underworld", "black_market_reputation"),
    }
    for choice_id, (flag, variable) in expected.items():
        player = Player(f"三方交锋{choice_id}", "散人")
        _start(CLASH, player, 0)
        player.quest_states[CLASH]["branch_pending"] = True
        variable_before = player.get_var(variable, 0)
        honor_before = player._jianghu_profile()["honor"]
        infamy_before = player._jianghu_profile()["infamy"]

        ok, message = player.choose_quest_branch(CLASH, choice_id)

        assert ok, message
        assert player.get_flag(flag) is True
        assert player.get_var(variable) - variable_before == 1
        assert player.quest_states[CLASH]["stage"] == 1
        if choice_id == "official_lean":
            assert player._jianghu_profile()["honor"] - honor_before == 1
        if choice_id == "underworld_lean":
            assert player._jianghu_profile()["infamy"] - infamy_before == 1


def test_clash_completion_sets_flags_rewards_and_relations(monkeypatch):
    player = Player("三方交锋交付", "散人")
    _start(CLASH, player, 3)
    gold_before = player.gold
    honor_before = player._jianghu_profile()["honor"]
    constable_before = player.get_relation("捕头")
    escort_before = player.get_relation("震远镖局总镖头")
    potion_before = player.inventory.count("金创药")

    _deliver(CLASH, player, "捕头", monkeypatch)

    assert player.get_flag(CLASH_DONE) is True
    assert player.get_flag("world:guiyun:threeway_incident_cleared") is True
    assert player.gold - gold_before == 110
    assert player.inventory.count("金创药") - potion_before == 2
    assert player._jianghu_profile()["honor"] - honor_before == 4
    assert player.get_relation("捕头") - constable_before == 2
    assert player.get_relation("震远镖局总镖头") - escort_before == 2
    assert player.get_var("government_reputation") == 1


def test_accord_locked_until_clash_delivered(monkeypatch):
    player = Player("三方定局未交锋", "散人")
    player.level = 11
    player.completed_quests.append(CLASH)
    output = _accept(ACCORD, player, "书生陆文清", monkeypatch, "guiyun_central_square")
    assert "接取失败" in output
    assert ACCORD not in player.active_quests

    player.set_flag(CLASH_DONE, True)
    _accept(ACCORD, player, "书生陆文清", monkeypatch, "guiyun_central_square")
    assert ACCORD in player.active_quests
    assert player.get_flag("quest:guiyun_threeway:accord_started") is True


def test_accord_offers_all_three_endings():
    player = Player("三方定局选路", "散人")
    assert _eligible(ACCORD, player) == list(ENDINGS)


def test_ambiguous_delivery_lists_all_three_without_settling(monkeypatch):
    player = Player("三方定局待选", "散人")
    _start(ACCORD, player, 3)
    gold_before = player.gold

    output = _deliver(ACCORD, player, "书生陆文清", monkeypatch)

    assert "请选择任务结局" in output
    for cfg in ENDINGS.values():
        assert cfg["title"] in output
    assert ACCORD in player.active_quests
    assert player.gold == gold_before
    assert region_activity.get_permanent_region_delta(player, "guiyun_city")["commerce"] == 0


def _settle(choice_id):
    player = Player(f"三方定局{choice_id}", "散人")
    _start(ACCORD, player, 3)
    return player


def test_endings_apply_rewards_world_consequences_and_report(monkeypatch):
    for choice_id, cfg in ENDINGS.items():
        player = _settle(choice_id)
        gold_before = player.gold
        honor_before = player._jianghu_profile()["honor"]
        infamy_before = player._jianghu_profile()["infamy"]
        item_before = player.inventory.count(cfg["item"])
        first, second, delta = cfg["faction"]
        faction_before = player.get_faction_relation(first, second)
        relation_before = {name: player.get_relation(name) for name in cfg["relations"]}

        output = _deliver(ACCORD, player, "书生陆文清", monkeypatch, choice_id)

        assert ACCORD in player.completed_quests, choice_id
        assert player.get_flag(cfg["flag"]) is True, choice_id
        assert player.gold - gold_before == cfg["gold"], choice_id
        assert player.inventory.count(cfg["item"]) - item_before == 1, choice_id
        assert player._jianghu_profile()["honor"] - honor_before == cfg["honor"], choice_id
        assert player._jianghu_profile()["infamy"] - infamy_before == cfg["infamy"], choice_id
        assert player.get_faction_relation(first, second) - faction_before == delta, choice_id
        for name, expected in cfg["relations"].items():
            assert player.get_relation(name) - relation_before[name] == expected, (choice_id, name)
        assert region_activity.get_permanent_region_delta(player, "guiyun_city") == cfg["region"], choice_id
        assert cfg["report"] in output, choice_id


def test_three_endings_are_mutually_exclusive_in_flags_and_region_axes(monkeypatch):
    regions = []
    for choice_id, cfg in ENDINGS.items():
        player = _settle(choice_id)
        _deliver(ACCORD, player, "书生陆文清", monkeypatch, choice_id)
        other_flags = [flag for flag in ENDING_FLAGS if flag != cfg["flag"]]
        assert all(player.get_flag(flag) is False for flag in other_flags), choice_id
        regions.append(region_activity.get_permanent_region_delta(player, "guiyun_city"))

    assert len({tuple(sorted(region.items())) for region in regions}) == 3
    assert regions[0]["commerce"] == 10
    assert regions[1]["security"] == 10
    assert regions[2]["travel"] == 6


def test_guild_constable_steward_and_scholar_lines_follow_each_ending(monkeypatch):
    expected = {
        "万商会会长": {
            "world:guiyun:threeway_merchant": "行规按商路重订",
            "world:guiyun:threeway_official": "巡夜加了两班",
            "world:guiyun:threeway_underworld": "夜市开了口子",
        },
        "捕头": {
            "world:guiyun:threeway_merchant": "巡夜的担子压在我们这边",
            "world:guiyun:threeway_official": "街面总算有章法",
            "world:guiyun:threeway_underworld": "夜市一开",
        },
        "黑市管事": {
            "world:guiyun:threeway_merchant": "黑市的生意就得往暗处再收一收",
            "world:guiyun:threeway_official": "衙门的手伸到巷子里来了",
            "world:guiyun:threeway_underworld": "你这份人情，管事记下了",
        },
        "书生陆文清": {
            "world:guiyun:threeway_merchant": "先通商，再议事",
            "world:guiyun:threeway_official": "以安民为先",
            "world:guiyun:threeway_underworld": "夜市一条写进去了",
        },
    }
    for npc, cases in expected.items():
        outputs = [_talk(npc, [flag], monkeypatch) for flag in cases]
        for output, phrase in zip(outputs, cases.values()):
            assert phrase in output, (npc, phrase)
        assert len(set(outputs)) == 3, npc


def test_givers_use_active_lines_while_chain_runs(monkeypatch):
    assert "你先去探探两边口风" in _talk("万商会会长", [f"quest_active:{PROBE}"], monkeypatch)
    assert "你落笔之前" in _talk("万商会会长", [f"quest_active:{ACCORD}"], monkeypatch)
    assert "先去镖局问清经过" in _talk("捕头", [f"quest_active:{CLASH}"], monkeypatch)
    assert "再去听听捕头和黑市管事" in _talk("万商会会长", [f"quest_active:{ACCORD}"], monkeypatch)
    assert "最后落笔的人得自己担这份干系" in _talk("书生陆文清", [f"quest_active:{ACCORD}"], monkeypatch)
    assert "巡夜不能减，抽税可以谈" in _talk("府衙文书", [f"quest_active:{PROBE}"], monkeypatch)
    assert "黑市的兄弟往后靠什么吃饭" in _talk("黑市管事", [f"quest_active:{ACCORD}"], monkeypatch)


def test_npcs_keep_base_dialogue_before_new_chain(monkeypatch):
    guild = _talk("万商会会长", [], monkeypatch)
    constable = _talk("捕头", [], monkeypatch)
    steward = _talk("黑市管事", [], monkeypatch)
    scholar = _talk("书生陆文清", [], monkeypatch)
    clerk = _talk("府衙文书", [], monkeypatch)

    assert "商路一通，百业皆活" in guild
    assert "最近有几名脚夫" in constable
    assert "这里的规矩只有一条" in steward
    assert "读书不只为科举" in scholar or "我正在整理各地风物" in scholar
    assert "若能把沉星黑市的头目揪出来" in clerk
    for output in (guild, constable, steward, scholar, clerk):
        assert "行规" not in output
        assert "夜市" not in output


def test_old_save_with_black_market_sees_only_probe_open():
    player = Player("三方旧档", "散人")
    player.level = 11
    player.completed_quests.append("沉星黑市")

    assert _quest_npc_status(player, PROBE)[0] == "未领取"
    clash_state, clash_detail = _quest_npc_status(player, CLASH)
    accord_state, accord_detail = _quest_npc_status(player, ACCORD)

    assert clash_state == "未开放"
    assert PROBE in clash_detail
    assert accord_state == "未开放"
    assert CLASH in accord_detail
    assert not any(flag.startswith("quest:guiyun_threeway:") and player.get_flag(flag) for flag in (
        "quest:guiyun_threeway:probe_started",
        PROBE_DONE,
        "quest:guiyun_threeway:clash_started",
        CLASH_DONE,
        "quest:guiyun_threeway:accord_started",
        "quest:guiyun_threeway:resolved",
    ))
