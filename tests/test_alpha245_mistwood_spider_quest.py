"""Alpha245：新增野外除蛛委托与真实资源点反馈。"""
import contextlib
import io

import engine
import main
from actions import handle_quest, handle_talk_and_ask, look
from economy import EconomyManager
from player import Player


def capture(fn, *args):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        fn(*args)
    return out.getvalue()


def test_spider_quest_is_gated_then_fully_deliverable(monkeypatch):
    monkeypatch.setattr(Player, "save_to_file", lambda self, filename=None: True)
    p = Player("蛛患委托验收", "散人")
    p.location = "mistwood_trail"

    denied = capture(handle_talk_and_ask, p, ["采药人阿芷", "接受委托", "雾溪除蛛·护药浅滩"])
    assert "接取条件未满足" in denied or "需要先完成任务" in denied
    assert "雾溪除蛛·护药浅滩" not in p.active_quests

    p.completed_quests.extend(["新手采药·认识资源", "雾林伐木·修补栈道"])
    p.set_flag("quest_completed:新手采药·认识资源", True)
    p.set_flag("quest_completed:雾林伐木·修补栈道", True)
    p.set_flag("world:main:mistwood_boardwalk_repaired", True)
    accepted = capture(handle_talk_and_ask, p, ["采药人阿芷", "接受委托", "雾溪除蛛·护药浅滩"])
    assert "已接取任务" in accepted, accepted
    assert p.active_quests.get("雾溪除蛛·护药浅滩") == 0

    p.location = "herb_springbank"
    p.update_quest_progress("迷雾毒蛛", event_type="kill")
    assert p.active_quests["雾溪除蛛·护药浅滩"] == 1
    p.update_quest_progress("迷雾毒蛛", event_type="kill")
    assert p.active_quests["雾溪除蛛·护药浅滩"] == 2

    p.location = "mistwood_trail"
    out = capture(handle_quest, p, "jiaofu", ["雾溪除蛛·护药浅滩"])
    assert "恭喜完成任务" in out, out
    assert "雾溪除蛛·护药浅滩" not in p.active_quests
    assert "雾溪除蛛·护药浅滩" in p.completed_quests
    assert p.get_flag("world:main:mistwood_herb_route_safe") is True

    dialogue = capture(handle_talk_and_ask, p, ["采药人阿芷"])
    assert "药香浅滩的毒蛛已经清掉了" in dialogue


def test_spider_clearance_changes_real_resource_capacity_and_scene_feedback():
    p = Player("浅滩资源反馈", "散人")
    p.location = "herb_springbank"
    manager = EconomyManager(getattr(p, "economy_state", {}))
    main._apply_player_world_resource_effects(manager, p)
    assert manager.resources["herb_springbank"]["capacity"] == 8

    p.set_flag("world:main:mistwood_herb_route_safe", True)
    manager = EconomyManager(getattr(p, "economy_state", {}))
    main._apply_player_world_resource_effects(manager, p)
    assert manager.resources["herb_springbank"]["capacity"] == 12
    assert manager.resources["herb_springbank"]["regen_amount"] == 3

    scene = capture(look, p)
    assert "毒蛛已被清除" in scene
    assert "资源储量：" in scene and "/12" in scene


def test_spider_quest_notice_is_hidden_until_both_prerequisites():
    from actions import handle_notice_board
    p = Player("蛛患线索", "散人")
    p.location = "village_square"
    before = capture(handle_notice_board, p)
    assert "药香浅滩近来毒蛛增多" not in before

    p.set_flag("quest_completed:新手采药·认识资源", True)
    p.set_flag("world:main:mistwood_boardwalk_repaired", True)
    after = capture(handle_notice_board, p)
    assert "药香浅滩近来毒蛛增多" in after
    assert "雾溪除蛛·护药浅滩" not in after
    assert "接受委托" not in after
