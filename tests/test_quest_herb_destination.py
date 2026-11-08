import contextlib
import io
import json
from pathlib import Path

import engine
import region_activity
from actions import handle_quest, handle_region_ecology
from player import Player

QUEST = "百草堂·药材去向"


def _capture(callback, *args):
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        callback(*args)
    return stream.getvalue()


def _start_quest(player):
    player.active_quests[QUEST] = 1
    player.quest_states[QUEST] = {"stage": 0, "progress": 1}
    player.set_flag(f"quest_active:{QUEST}", True)
    player.set_flag("quest:village_herb_destination:started", True)


def _deliver(player, monkeypatch, choice=None):
    monkeypatch.setattr(Player, "save_to_file", lambda self, filename=None, verbose=True: True)
    monkeypatch.setattr(Player, "get_npcs_in_room", lambda self, location=None: ["村长"])
    args = [QUEST if choice is None else f"{QUEST}|{choice}"]
    return _capture(handle_quest, player, "jiaofu", args)


def test_quest_is_gated_behind_herb_restock():
    quests = json.loads(Path("data/quests.json").read_text(encoding="utf-8"))
    quest = quests[QUEST]

    assert quest["npc"] == "村长"
    assert quest["turn_in_npc"] == "村长"
    assert quest["target_type"] == "talk"
    assert quest["target_name"] == "药铺老板"
    assert "world:main:herb_stock_replenished" in quest["requires"]["flags"]
    assert "quest_completed:百草备货·补齐药材" in quest["requires"]["flags"]
    assert [choice["id"] for choice in quest["choices"]] == ["sell_to_merchant", "keep_for_village"]


def test_sell_ending_pays_merchant_and_lifts_commerce(monkeypatch):
    player = Player("药材去向行商", "散人")
    _start_quest(player)
    gold_before = player.gold

    _deliver(player, monkeypatch, "sell_to_merchant")

    assert QUEST in player.completed_quests
    assert QUEST not in player.active_quests
    assert player.gold - gold_before == 180
    assert player.get_flag("world:main:herb_sold_to_merchant") is True
    assert region_activity.get_permanent_region_delta(player, "main") == {
        "security": -3,
        "commerce": 12,
        "travel": 4,
    }
    variables = player.world_state["variables"]
    assert variables["faction_relations"]["青石村:商会"] == 12
    assert variables["npc_relations"]["村长"] == 5
    assert variables["npc_relations"]["药铺老板"] == -4


def test_keep_ending_adds_medicine_and_security(monkeypatch):
    player = Player("药材去向留村", "散人")
    _start_quest(player)
    honor_before = player._jianghu_profile()["honor"]
    medicine_before = player.inventory.count("疗伤药")

    _deliver(player, monkeypatch, "keep_for_village")

    assert QUEST in player.completed_quests
    assert player._jianghu_profile()["honor"] - honor_before == 4
    assert player.inventory.count("疗伤药") == medicine_before + 1
    assert player.get_flag("world:main:herb_kept_for_village") is True
    assert region_activity.get_permanent_region_delta(player, "main") == {
        "security": 8,
        "commerce": -4,
        "travel": 0,
    }
    variables = player.world_state["variables"]
    assert variables["faction_relations"]["青石村:商会"] == 6
    assert variables["faction_relations"]["青石村:官府"] == 20
    assert variables["npc_relations"]["药铺老板"] == 5
    assert variables["npc_relations"]["村长"] == -2


def test_region_panel_shows_prosperity_after_merchant_ending(monkeypatch):
    player = Player("药材去向商路", "散人")
    _start_quest(player)
    _deliver(player, monkeypatch, "sell_to_merchant")

    player.process_region_ecology()
    output = _capture(handle_region_ecology, player, ["主世界"])

    assert "安全度：69/100" in output
    assert "商路：80/100" in output
    assert "商路繁荣" in output


def test_region_panel_shows_safety_after_village_ending(monkeypatch):
    player = Player("药材去向治安", "散人")
    _start_quest(player)
    _deliver(player, monkeypatch, "keep_for_village")

    player.process_region_ecology()
    output = _capture(handle_region_ecology, player, ["主世界"])

    assert "安全度：80/100" in output
    assert "商路：64/100" in output
    assert "治安较好" in output


def test_ambiguous_delivery_lists_both_endings_without_settling(monkeypatch):
    player = Player("药材去向待选", "散人")
    _start_quest(player)
    gold_before = player.gold

    output = _deliver(player, monkeypatch)

    assert "请选择任务结局" in output
    assert "卖给归云城行商" in output
    assert "留作村中备药" in output
    assert QUEST in player.active_quests
    assert player.gold == gold_before
    assert region_activity.get_permanent_region_delta(player, "main")["commerce"] == 0


def test_merchant_ending_reports_region_changes(monkeypatch):
    player = Player("药材去向商路反馈", "散人")
    _start_quest(player)

    output = _deliver(player, monkeypatch, "sell_to_merchant")

    assert "区域变化：主世界 安全度 -3、商路 +12、通行 +4" in output


def test_village_ending_reports_region_changes(monkeypatch):
    player = Player("药材去向治安反馈", "散人")
    _start_quest(player)

    output = _deliver(player, monkeypatch, "keep_for_village")

    assert "区域变化：主世界 安全度 +8、商路 -4" in output
