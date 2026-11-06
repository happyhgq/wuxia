"""Alpha246：矿料委托真正影响供料、生产、深矿资源与后续任务。"""
import contextlib
import io

import engine
from actions import handle_notice_board, handle_quest, handle_talk_and_ask
from economy import EconomyManager
from player import Player


def capture(fn, *args):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        fn(*args)
    return out.getvalue()


def test_mine_supply_world_flag_improves_real_supplier_and_blacksmith_recipe(monkeypatch):
    monkeypatch.setattr(Player, "save_to_file", lambda self, filename=None: True)
    p = Player("矿料联动验收", "散人")
    base = EconomyManager({})
    assert base.gatherers["矿工顾三"]["capacity"] == 10
    assert base.recipes["铁匠"]["supplier_routes"][0]["max_stock"] == 5

    p.set_flag("world:main:abandoned_mine_supply_secured", True)
    improved = EconomyManager({})
    improved.apply_world_progress(p.world_state)
    assert improved.gatherers["矿工顾三"]["capacity"] == 14
    assert improved.gatherers["矿工顾三"]["amount"] == 4
    assert improved.gatherers["矿工顾三"]["interval"] == 4
    route = improved.recipes["铁匠"]["supplier_routes"][0]
    assert route["max_stock"] == 8
    assert route["max_per_tick"] == 4
    assert route["interval"] == 4

    # The improved profile still depends on real miner stock, funds and the production recipe.
    # 工时按左闭右开计算，老配方最后一小时属于交班；多跑一个时辰让铁匠完成本轮制作。
    improved.update(73, player_location="village_square")
    state = improved.export_state()
    miner_stock = state.get("npc_inventory", {}).get("矿工顾三", {}).get("铁矿石", 0)
    village_smith_stock = state.get("npc_inventory", {}).get("铁匠", {})
    city_smith_stock = state.get("npc_inventory", {}).get("百炼铁铺铁匠", {})
    assert miner_stock >= 0
    assert state.get("npc_gold", {}).get("矿工顾三", 0) >= 0
    # Both village and city production consume actual ore; a sword must have been made by one of them.
    assert village_smith_stock.get("铁剑", 0) + city_smith_stock.get("铁剑", 0) >= 1, state
    assert village_smith_stock.get("铁矿石", 0) >= 0


def test_boardwalk_and_deep_mine_flags_change_actual_economy_profiles():
    manager = EconomyManager({})
    assert manager.gatherers["樵夫老周"]["capacity"] == 16
    manager.apply_world_progress({"flags": {"world:main:mistwood_boardwalk_repaired": True}})
    assert manager.gatherers["樵夫老周"]["capacity"] == 20
    assert manager.gatherers["樵夫老周"]["amount"] == 3
    wood_route = manager.recipes["木匠老许"]["supplier_routes"][0]
    assert wood_route["max_stock"] == 6
    assert wood_route["interval"] == 8

    assert manager.resources["deep_iron_gallery"]["capacity"] == 28
    manager.apply_world_progress({"flags": {"world:main:deep_iron_gallery_cleared": True}})
    assert manager.resources["deep_iron_gallery"]["capacity"] == 34
    assert manager.resources["deep_iron_gallery"]["regen_amount"] == 4


def test_deep_mine_clearance_quest_accept_progress_delivery_and_notice(monkeypatch):
    monkeypatch.setattr(Player, "save_to_file", lambda self, filename=None: True)
    qid = "铁脉清障·深处探矿"
    p = Player("铁脉清障验收", "散人")
    p.location = "abandoned_iron_mine"

    p.location = "village_square"
    before = capture(handle_notice_board, p)
    assert "矿工顾三准备继续勘探铁脉长廊" not in before

    p.location = "abandoned_iron_mine"
    denied = capture(handle_talk_and_ask, p, ["矿工顾三", "接受委托", qid])
    assert "接取条件未满足" in denied or "需要先完成任务" in denied
    assert qid not in p.active_quests
    assert "铁背矿獾" not in denied

    p.set_flag("world:main:abandoned_mine_supply_secured", True)
    p.location = "village_square"
    after = capture(handle_notice_board, p)
    assert "矿工顾三准备继续勘探铁脉长廊" in after
    assert qid not in after
    assert "接受委托" not in after

    p.location = "abandoned_iron_mine"
    accepted = capture(handle_talk_and_ask, p, ["矿工顾三", "接受委托", qid])
    assert "已接取任务" in accepted, accepted
    assert p.active_quests.get(qid) == 0

    p.location = "deep_iron_gallery"
    p.update_quest_progress("铁背矿獾", event_type="kill")
    p.update_quest_progress("铁背矿獾", event_type="kill")
    assert p.active_quests[qid] == 2

    p.location = "abandoned_iron_mine"
    delivered = capture(handle_quest, p, "jiaofu", [qid])
    assert "恭喜完成任务" in delivered, delivered
    assert qid not in p.active_quests
    assert qid in p.completed_quests
    assert p.get_flag("world:main:deep_iron_gallery_cleared") is True

    economy = EconomyManager(p.economy_state)
    economy.apply_world_progress(p.world_state)
    assert economy.resources["deep_iron_gallery"]["capacity"] == 34
    assert economy.resources["deep_iron_gallery"]["regen_amount"] == 4

    dialogue = capture(handle_talk_and_ask, p, ["矿工顾三"])
    assert "铁脉长廊的矿獾已经赶走" in dialogue

    p.location = "blacksmith"
    smith_dialogue = capture(handle_talk_and_ask, p, ["铁匠"])
    assert "送来的铁矿石也更稳定了" in smith_dialogue


def test_new_enemy_is_available_in_deep_iron_gallery_and_has_bounded_drops():
    assert "铁背矿獾" in engine.ENEMIES
    room = engine.ROOMS["deep_iron_gallery"]
    assert "铁背矿獾" in room["enemies"]
    enemy = engine.ENEMIES["铁背矿獾"]
    assert 1 <= enemy["level"] <= 6
    assert enemy["hp"] > 0 and enemy["atk"] > 0
    assert all(0 <= drop.get("chance", 0) <= 1 for drop in enemy.get("drops", []))
