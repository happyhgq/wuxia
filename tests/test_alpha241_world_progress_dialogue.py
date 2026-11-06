"""Alpha241：村道与药材任务完成后，固定 NPC 的日常对白反映世界变化。"""
import contextlib
import io

from actions import handle_talk_and_ask
from player import Player


def _talk(player, npc):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        handle_talk_and_ask(player, [npc])
    return out.getvalue()


def test_medicine_shop_dialogue_reflects_highest_completed_world_state():
    p = Player("世界反馈药铺", "散人")
    p.location = "medicine_shop"
    assert "前阵子耽搁太久" not in _talk(p, "药铺老板")
    p.set_flag("world:main:village_road_safe", True)
    assert "采药人也敢走动了" in _talk(p, "药铺老板")
    p.set_flag("world:main:herb_trade_resumed", True)
    assert "常用药材还缺着几味" in _talk(p, "药铺老板")
    p.set_flag("world:main:herb_stock_replenished", True)
    assert "常用药材总算补齐了" in _talk(p, "药铺老板")


def test_village_chief_dialogue_reflects_restock_completion():
    p = Player("世界反馈村长", "散人")
    p.location = "village_head_house"
    p.set_flag("world:main:herb_stock_replenished", True)
    out = _talk(p, "村长")
    assert "百草堂的药材已经补齐" in out
    assert "靠你肯替乡亲跑这一趟" in out


def test_conditional_dialogue_does_not_change_quest_or_save_schema():
    p = Player("世界反馈兼容", "散人")
    p.location = "medicine_shop"
    before = set(p.active_quests)
    _talk(p, "药铺老板")
    assert set(p.active_quests) == before
    assert getattr(p, "SAVE_VERSION", 12) == 12
