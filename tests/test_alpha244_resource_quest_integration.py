"""Alpha244：四类新手资源/狩猎任务及后续野外委托的真实进度与交付闭环。"""
import contextlib
import io
import json
from pathlib import Path

import engine
from actions import handle_quest, handle_talk_and_ask
from economy import EconomyManager
from player import Player


def capture(fn, *args):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        fn(*args)
    return out.getvalue()


def accept(player, npc, public_title):
    out = capture(handle_talk_and_ask, player, [npc, "接受委托", public_title])
    assert "已接取任务" in out, out
    assert any(public_title == engine.QUESTS[q].get("title") for q in player.active_quests)


def deliver(player, qid, npc, location):
    player.location = location
    out = capture(handle_quest, player, "jiaofu", [qid])
    assert "恭喜完成任务" in out, out
    assert qid not in player.active_quests
    assert qid in player.completed_quests
    return out


def test_four_starter_tasks_progress_from_real_resource_and_kill_events(monkeypatch):
    monkeypatch.setattr(Player, "save_to_file", lambda self, filename=None: True)
    cases = [
        ("新手采药·认识资源", "药铺老板", "初入江湖·采药识草", "草药", "gather", "mistwood_stream", "medicine_shop", 2),
        ("新手伐木·备料", "铁匠", "初入江湖·备些木料", "木材", "chop", "mistwood_trail", "blacksmith", 2),
        ("新手采矿·寻铁", "铁匠", "初入江湖·寻找铁矿", "铁矿石", "mine", "abandoned_iron_mine", "blacksmith", 2),
        ("新手狩猎·野外除害", "村长", "初入江湖·野外除害", "野猪", "kill", "wild_fields", "village_head_house", 1),
    ]
    for qid, npc, title, target, event, resource_room, turn_in_room, needed in cases:
        p = Player("闭环-" + qid, "散人")
        # Put player at the issuer before acceptance; no guide flag is required.
        issuer_room = next(rid for rid, room in engine.ROOMS.items() if npc in room.get("npcs", []))
        p.location = issuer_room
        accept(p, npc, title)
        assert qid in p.active_quests

        if event == "kill":
            p.location = resource_room
            p.update_quest_progress(target, event_type="kill")
        else:
            manager = EconomyManager(getattr(p, "economy_state", {}))
            manager.real_time_regen = True
            method = {"gather": manager.gather, "chop": manager.chop, "mine": manager.mine}[event]
            baseline_target_count = p.inventory.count(target)
            item_name, amount = target, 0
            # 草药节点每次只产出一份；循环真实采集调用直到满足任务数量。
            for _ in range(needed + 2):
                ok, result = method(resource_room, min(needed - amount, 3), max_quantity=needed - amount)
                if not ok:
                    break
                item_name, gained = result
                assert item_name == target, (qid, result)
                amount += gained
                p.inventory.extend([item_name] * gained)
                for _ in range(gained):
                    p.update_quest_progress(item_name, event_type="collect")
                if amount >= needed:
                    break
            assert amount >= needed, (qid, amount)
            p.economy_state = manager.export_state()

        assert p.active_quests[qid] >= needed, (qid, p.active_quests[qid])
        # Collection quests consume required items at delivery; hunting doesn't require a drop.
        deliver(p, qid, npc, turn_in_room)
        if event != "kill":
            assert p.inventory.count(target) == baseline_target_count + amount - needed


def test_two_new_wilderness_followups_are_gated_and_fully_deliverable(monkeypatch):
    monkeypatch.setattr(Player, "save_to_file", lambda self, filename=None: True)
    quests = json.loads(Path("data/quests.json").read_text(encoding="utf-8"))
    followups = [
        ("雾林伐木·修补栈道", "樵夫老周", "雾林伐木·修补栈道", "木材", "mistwood_trail", "新手伐木·备料", 4),
        ("废矿寻铁·补足矿料", "矿工顾三", "废矿寻铁·补足矿料", "铁矿石", "abandoned_iron_mine", "新手采矿·寻铁", 4),
    ]
    for qid, npc, title, target, resource_room, prerequisite, needed in followups:
        p = Player("后续-" + qid, "散人")
        issuer_room = next(rid for rid, room in engine.ROOMS.items() if npc in room.get("npcs", []))
        p.location = issuer_room
        denied = capture(handle_talk_and_ask, p, [npc, "接受委托", title])
        assert "接取条件未满足" in denied or "需要先完成任务" in denied, denied
        assert qid not in p.active_quests

        p.completed_quests.append(prerequisite)
        p.set_flag("quest_completed:" + prerequisite, True)
        p.location = issuer_room
        accept(p, npc, title)
        manager = EconomyManager(getattr(p, "economy_state", {}))
        manager.real_time_regen = True
        method = manager.chop if target == "木材" else manager.mine
        baseline_target_count = p.inventory.count(target)
        item_name, amount = target, 0
        for _ in range(needed + 2):
            ok, result = method(resource_room, min(needed - amount, 3), max_quantity=needed - amount)
            if not ok:
                break
            item_name, gained = result
            assert item_name == target, (qid, result)
            amount += gained
            p.inventory.extend([item_name] * gained)
            for _ in range(gained):
                p.update_quest_progress(item_name, event_type="collect")
            if amount >= needed:
                break
        assert amount >= needed, (qid, amount)
        p.economy_state = manager.export_state()
        deliver(p, qid, npc, issuer_room)
        world_flag = next(flag for flag in quests[qid]["on_complete"]["set_flags"] if flag.startswith("world:"))
        assert p.get_flag(world_flag) is True
        assert p.inventory.count(target) == baseline_target_count + amount - needed


def test_new_followup_clues_are_natural_and_hidden_until_prerequisite():
    p = Player("新后续线索", "散人")
    p.location = "village_square"
    from actions import handle_notice_board
    before = capture(handle_notice_board, p)
    assert "雾隐林道的木栈道" not in before
    assert "废弃铁矿的矿工" not in before

    p.set_flag("quest_completed:新手伐木·备料", True)
    p.set_flag("quest_completed:新手采矿·寻铁", True)
    after = capture(handle_notice_board, p)
    assert "雾隐林道的木栈道" in after
    assert "废弃铁矿的矿工" in after
    assert "雾林伐木·修补栈道" not in after
    assert "废矿寻铁·补足矿料" not in after
    assert "接受委托" not in after


def test_world_progress_dialogue_reflects_completed_wood_and_mining_followups():
    p = Player("野外世界反馈", "散人")
    p.location = "mistwood_trail"
    p.set_flag("world:main:mistwood_boardwalk_repaired", True)
    wood = capture(handle_talk_and_ask, p, ["樵夫老周"])
    assert "栈道修好了" in wood

    p.location = "abandoned_iron_mine"
    p.set_flag("world:main:abandoned_mine_supply_secured", True)
    miner = capture(handle_talk_and_ask, p, ["矿工顾三"])
    assert "修整矿道的材料总算够了" in miner
