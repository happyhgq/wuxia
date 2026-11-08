"""北境暗线·了断：北境失货与沉星黑市的收束、三结局与区域后果。"""
import contextlib
import io
import json
from pathlib import Path

import engine
import region_activity
from actions import handle_quest, handle_talk_and_ask
from player import Player

QUEST = "北境暗线·了断"
OFFICIAL_FLAG = "northfront:smuggling_route_exposed"
BLACK_FLAG = "northfront:smuggler_deal_made"


def _capture(callback, *args):
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        callback(*args)
    return stream.getvalue()


def _start_quest(player):
    player.active_quests[QUEST] = 1
    player.quest_states[QUEST] = {"stage": 3, "progress": 1}
    player.set_flag(f"quest_active:{QUEST}", True)
    player.set_flag("quest:northfront_blackmarket_settlement:started", True)


def _deliver(player, monkeypatch, choice=None):
    monkeypatch.setattr(Player, "save_to_file", lambda self, filename=None, verbose=True: True)
    monkeypatch.setattr(Player, "get_npcs_in_room", lambda self, location=None: ["巡河老兵"])
    args = [QUEST if choice is None else f"{QUEST}|{choice}"]
    return _capture(handle_quest, player, "jiaofu", args)


def _eligible(player):
    return [
        choice["id"]
        for choice in engine.QUESTS[QUEST]["choices"]
        if engine.check_conditions(choice.get("requires"), player.world_state, player.completed_quests, player)
    ]


def _faction(player, first, second):
    key = f"{first}:{second}"
    relations = player.world_state.get("variables", {}).get("faction_relations", {})
    if key in relations:
        return relations[key]
    return engine.FACTIONS.get(first, {}).get("relations", {}).get(second, 0)


def _npc_relation(player, name):
    return player.world_state.get("variables", {}).get("npc_relations", {}).get(name, 0)


def _talk(npc, flags, monkeypatch):
    monkeypatch.setattr(Player, "save_to_file", lambda self, filename=None, verbose=True: True)
    player = Player("北境暗线台词", "散人")
    player.get_npcs_in_room = lambda location=None: [npc]
    for flag in flags:
        player.set_flag(flag, True)
    return _capture(handle_talk_and_ask, player, [npc])


def test_quest_links_northfront_and_black_market():
    quests = json.loads(Path("data/quests.json").read_text(encoding="utf-8"))
    quest = quests[QUEST]

    assert quest["npc"] == "巡河老兵"
    assert quest["turn_in_npc"] == "巡河老兵"
    assert quest["requires"]["level"] == 8
    assert set(quest["requires"]["flags"]) == {"quest_completed:北境失货追查", "quest_completed:沉星黑市"}
    assert [choice["id"] for choice in quest["choices"]] == ["seal_the_line", "keep_the_line", "joint_checkpoint"]
    assert [stage["target_name"] for stage in quest["stages"]] == ["北境货栈掌柜", "河埠私枭", "黑市接头人", "巡河老兵"]


def test_official_profile_can_seal_or_check_but_not_tolerate():
    player = Player("北境官方线", "散人")
    player.set_flag(OFFICIAL_FLAG, True)

    assert _eligible(player) == ["seal_the_line", "joint_checkpoint"]


def test_blackmarket_profile_can_tolerate_or_check_but_not_seal():
    player = Player("北境黑市线", "散人")
    player.set_flag(BLACK_FLAG, True)

    assert _eligible(player) == ["keep_the_line", "joint_checkpoint"]


def test_mixed_profile_sees_all_three_endings():
    player = Player("北境两头跑", "散人")
    player.set_flag(OFFICIAL_FLAG, True)
    player.set_flag(BLACK_FLAG, True)

    assert _eligible(player) == ["seal_the_line", "keep_the_line", "joint_checkpoint"]


def test_accept_requires_both_prior_quest_lines(monkeypatch):
    monkeypatch.setattr(Player, "save_to_file", lambda self, filename=None, verbose=True: True)
    player = Player("北境接取前置", "散人")
    player.level = 8
    player.location = "northfront_gate"
    player.get_npcs_in_room = lambda location=None: ["巡河老兵"]
    player.completed_quests.append("北境失货追查")

    output = _capture(handle_quest, player, "jiequ", [QUEST])

    assert "接取失败" in output
    assert QUEST not in player.active_quests


def test_accept_sets_started_flags(monkeypatch):
    monkeypatch.setattr(Player, "save_to_file", lambda self, filename=None, verbose=True: True)
    player = Player("北境接取成功", "散人")
    player.level = 8
    player.location = "northfront_gate"
    player.get_npcs_in_room = lambda location=None: ["巡河老兵"]
    player.completed_quests.extend(["北境失货追查", "沉星黑市"])

    _capture(handle_quest, player, "jiequ", [QUEST])

    assert QUEST in player.active_quests
    assert player.get_flag("quest:northfront_blackmarket_settlement:started") is True
    assert player.get_flag(f"quest_active:{QUEST}") is True


def test_seal_ending_raises_security_and_reports_both_regions(monkeypatch):
    player = Player("北境封线", "散人")
    player.set_flag(OFFICIAL_FLAG, True)
    _start_quest(player)
    gold_before = player.gold
    honor_before = player._jianghu_profile()["honor"]
    black_market_before = _faction(player, "江湖", "黑市")
    veteran_before = _npc_relation(player, "巡河老兵")

    output = _deliver(player, monkeypatch, "seal_the_line")

    assert QUEST in player.completed_quests
    assert QUEST not in player.active_quests
    assert player.gold - gold_before == 140
    assert player._jianghu_profile()["honor"] - honor_before == 7
    assert player.get_flag("world:northfront:blackmarket_line_closed") is True
    assert player.get_flag("world:northfront:blackmarket_line_settled") is True
    assert region_activity.get_permanent_region_delta(player, "northfront_town") == {
        "security": 10,
        "commerce": -6,
        "travel": -2,
    }
    assert region_activity.get_permanent_region_delta(player, "guiyun_city") == {
        "security": 4,
        "commerce": -3,
        "travel": 0,
    }
    assert _faction(player, "江湖", "黑市") - black_market_before == -5
    assert _npc_relation(player, "巡河老兵") - veteran_before == 4
    assert "区域变化：北境商镇 安全度 +10、商路 -6、通行 -2" in output
    assert "区域变化：归云城 安全度 +4、商路 -3" in output


def test_tolerate_ending_lifts_commerce_and_adds_infamy(monkeypatch):
    player = Player("北境留线", "散人")
    player.set_flag(BLACK_FLAG, True)
    _start_quest(player)
    gold_before = player.gold
    infamy_before = player._jianghu_profile()["infamy"]
    black_market_before = _faction(player, "江湖", "黑市")

    _deliver(player, monkeypatch, "keep_the_line")

    assert player.gold - gold_before == 240
    assert player._jianghu_profile()["infamy"] - infamy_before == 2
    assert player.get_flag("world:northfront:blackmarket_line_tolerated") is True
    assert player.get_flag("world:northfront:blackmarket_line_closed") is False
    assert region_activity.get_permanent_region_delta(player, "northfront_town") == {
        "security": -7,
        "commerce": 9,
        "travel": 4,
    }
    assert region_activity.get_permanent_region_delta(player, "guiyun_city") == {
        "security": -3,
        "commerce": 5,
        "travel": 0,
    }
    assert _faction(player, "江湖", "黑市") - black_market_before == 5


def test_checkpoint_ending_balances_security_and_checkpoint_cost(monkeypatch):
    player = Player("北境设卡", "散人")
    _start_quest(player)
    gold_before = player.gold
    honor_before = player._jianghu_profile()["honor"]

    _deliver(player, monkeypatch, "joint_checkpoint")

    assert player.gold - gold_before == 180
    assert player._jianghu_profile()["honor"] - honor_before == 5
    assert player.get_flag("world:northfront:blackmarket_line_supervised") is True
    assert region_activity.get_permanent_region_delta(player, "northfront_town") == {
        "security": 4,
        "commerce": 2,
        "travel": -3,
    }
    assert region_activity.get_permanent_region_delta(player, "guiyun_city") == {
        "security": 2,
        "commerce": 1,
        "travel": -1,
    }


def test_ambiguous_delivery_lists_endings_without_settling(monkeypatch):
    player = Player("北境待选", "散人")
    player.set_flag(OFFICIAL_FLAG, True)
    player.set_flag(BLACK_FLAG, True)
    _start_quest(player)
    gold_before = player.gold

    output = _deliver(player, monkeypatch)

    assert "请选择任务结局" in output
    assert "封死暗线" in output
    assert QUEST in player.active_quests
    assert player.gold == gold_before
    assert region_activity.get_permanent_region_delta(player, "northfront_town")["security"] == 0


def test_veteran_line_changes_with_settlement(monkeypatch):
    closed = _talk("巡河老兵", ["world:northfront:blackmarket_line_closed"], monkeypatch)
    tolerated = _talk("巡河老兵", ["world:northfront:blackmarket_line_tolerated"], monkeypatch)
    supervised = _talk("巡河老兵", ["world:northfront:blackmarket_line_supervised"], monkeypatch)

    assert "暗线封了" in closed
    assert "那几条船，我不会再看第二眼" in tolerated
    assert "关卡立起来后" in supervised
    assert len({closed, tolerated, supervised}) == 3


def test_shopkeeper_line_changes_with_settlement(monkeypatch):
    closed = _talk("北境货栈掌柜", ["world:northfront:blackmarket_line_closed"], monkeypatch)
    tolerated = _talk("北境货栈掌柜", ["world:northfront:blackmarket_line_tolerated"], monkeypatch)
    supervised = _talk("北境货栈掌柜", ["world:northfront:blackmarket_line_supervised"], monkeypatch)

    assert "账倒是干净了" in closed
    assert "我连账都不敢往明面上写" in tolerated
    assert "封蜡总算不会再被人偷偷换掉" in supervised
    assert len({closed, tolerated, supervised}) == 3


def test_both_npcs_use_started_line_while_quest_active(monkeypatch):
    veteran = _talk("巡河老兵", [f"quest_active:{QUEST}"], monkeypatch)
    shopkeeper = _talk("北境货栈掌柜", [f"quest_active:{QUEST}"], monkeypatch)

    assert "接头人也在等你的话" in veteran
    assert "等你了断这条线" in shopkeeper


def test_npcs_keep_base_dialogue_without_settlement_flags(monkeypatch):
    veteran = _talk("巡河老兵", [], monkeypatch)
    shopkeeper = _talk("北境货栈掌柜", [], monkeypatch)

    assert "水面看着平静" in veteran or "若要去河埠" in veteran
    assert "封了暗线" not in veteran
    assert "近来河埠不太平" in shopkeeper
    assert "封了暗线" not in shopkeeper
