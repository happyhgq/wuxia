# -*- coding: utf-8 -*-
"""Alpha294：只读指令不耗时、普通交互只走一个世界时刻，tick 0 = 卯时 06:00。"""
import builtins
import contextlib
import io
from unittest.mock import patch

import pytest

import main
from actions import handle_talk_and_ask
from command_policy import command_advances_world
from economy.manager import _within_work_hours
from player import Player
from world_time import WORLD_CLOCK_OFFSET, format_world_clock, shichen_name, world_hour


def test_tick_zero_is_maoshi_six():
    assert WORLD_CLOCK_OFFSET == 6
    assert world_hour(0) == 6
    assert shichen_name(0) == "卯"
    assert format_world_clock(0) == "卯时 06:00"
    assert world_hour(18) == 0
    assert shichen_name(18) == "子"


def test_economy_work_hours_share_the_same_clock_baseline():
    # 铁匠铺 07:00–18:00 为左闭右开：tick 1 = 07:00，tick 11 = 17:00，
    # tick 12 = 18:00 已属于收工时刻，tick 13 = 19:00 同样歇工。
    assert not _within_work_hours([7, 18], 0)
    assert _within_work_hours([7, 18], 1)
    assert _within_work_hours([7, 18], 11)
    assert not _within_work_hours([7, 18], 12)
    assert not _within_work_hours([7, 18], 13)
    # 与 NPC 日常日程共用边界语义：结束钟点让给下一班次。
    assert _within_work_hours([22, 6], 16)   # 22:00
    assert not _within_work_hours([22, 6], 0)  # 06:00 已交班
    assert not _within_work_hours([9, 9], 3)


def test_npc_daily_schedule_uses_the_same_clock_baseline():
    player = Player("时钟对齐", "散人")
    player.set_var("quest_clock", 0)  # 卯时 06:00
    player.refresh_npc_schedules()
    assert player.get_npc_state("守卫") == "busy"  # 守卫 06:00–12:00 巡村
    player.set_var("quest_clock", 6)  # 午时 12:00
    player.refresh_npc_schedules()
    assert player.get_npc_state("守卫") == "normal"


@pytest.mark.parametrize("cmd,args", [
    ("shop", []),
    ("list", ["金创药"]),
    ("quests", []),
    ("quests", ["民团训练"]),
    ("attributes", []),
    ("attributes", ["查看"]),
    ("sect", []),
    ("sect", ["查看", "少林"]),
    ("sect", ["声望"]),
    ("sect", ["关系"]),
    ("sect", ["师徒"]),
    ("information", []),
    ("information", ["memory"]),
    ("memory", []),
    ("equipment", []),
    ("装备", []),
    ("compare", ["精铁剑"]),
    ("forge", ["预览"]),
    ("influence", []),
])
def test_read_only_views_do_not_advance_world(cmd, args):
    assert command_advances_world(cmd, args) is False


@pytest.mark.parametrize("cmd,args", [
    ("buy", ["金创药", "1"]),
    ("sell", ["草药", "1"]),
    ("mine", []),
    ("chop", []),
    ("search", []),
    ("forge", []),
    ("forge", ["强化"]),
    ("quests", ["接取", "民团训练"]),
    ("quests", ["交付", "民团训练"]),
    ("attributes", ["力量", "1"]),
    ("attributes", ["加点", "力量", "1"]),
    ("sect", ["拜师", "少林"]),
    ("sect", ["晋升"]),
    ("sect", ["师徒", "请教"]),
    ("information", ["山贼"]),
    ("travel", ["华山山门"]),
])
def test_ordinary_interactions_advance_world(cmd, args):
    assert command_advances_world(cmd, args) is True


def test_talk_is_ticked_by_the_dialogue_path_not_the_generic_policy():
    # 交谈要在读取当前在场人物后推进时钟，主循环单独处理，避免 NPC 先被日程移走。
    assert command_advances_world("talk", ["村长"]) is False


class _FakePlayer:
    def __init__(self):
        self.location = "village_square"
        self.world_state = {"variables": {}}
        self.ticks = 0
        self.saved = 0

    def get_quest_clock(self):
        return self.ticks

    def tick_quest_clock(self, steps=1):
        self.ticks += steps

    def mark_visited(self, _room):
        return None

    def save_to_file(self, filename=None, verbose=True):
        self.saved += 1

    def begin_deferred_save(self):
        self._save_deferred = True

    def flush_deferred_save(self):
        self._save_deferred = False
        return False


def test_main_loop_ticks_once_per_ordinary_interaction():
    fake = _FakePlayer()
    commands = ["查看", "帮助", "背包", "属性", "锻造", "交谈 村长", "退出"]
    with patch.object(main.os.path, "exists", return_value=True), \
         patch.object(main.Player, "load_from_file", return_value=fake), \
         patch.object(builtins, "input", return_value="y"), \
         patch.object(main, "read_command", side_effect=commands), \
         patch.object(main, "clear_screen"), \
         patch.object(main, "look"), \
         patch.object(main, "show_help"), \
         patch.object(main, "show_inventory"), \
         patch.object(main, "handle_attributes"), \
         patch.object(main, "handle_forge"), \
         patch.object(main, "handle_talk_and_ask", return_value=None), \
         patch.object(main, "announce_pending_npc_movement"), \
         patch.object(main, "announce_pending_caravan_arrivals"), \
         contextlib.redirect_stdout(io.StringIO()):
        main.main()
    # 四条查看指令不耗时；锻造与交谈各推进一个时刻。
    assert fake.ticks == 2
    assert fake.saved == 1


def test_status_panel_shows_world_clock():
    player = Player("时钟显示", "散人")
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        main.show_status(player, "main")
    rendered = output.getvalue()
    assert "世界时间：" in rendered
    assert "卯时 06:00" in rendered


def _run_main_loop(player, commands):
    with patch.object(main.os.path, "exists", return_value=True), \
         patch.object(main.Player, "load_from_file", return_value=player), \
         patch.object(main.Player, "save_to_file", lambda self, filename=None: True), \
         patch.object(builtins, "input", return_value="y"), \
         patch.object(main, "read_command", side_effect=list(commands)), \
         patch.object(main, "clear_screen"), \
         patch.object(main, "look"), \
         patch.object(main, "announce_pending_npc_movement"), \
         patch.object(main, "announce_pending_caravan_arrivals"), \
         contextlib.redirect_stdout(io.StringIO()):
        main.main()


def _capture_talk(player, args):
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        result = handle_talk_and_ask(player, args)
    return output.getvalue(), result


def test_talk_without_any_npc_does_not_advance_world():
    player = Player("空房交谈", "散人")
    player.set_var("quest_clock", 7)
    player.location = "temple"
    # 随机路人按概率刷新，会让“空房间”偶发出现可交谈对象；固定为空以验证无对象时不耗时。
    with patch("random_npcs.refresh_current_room", return_value=[]):
        _run_main_loop(player, ["交谈", "退出"])
    assert player.get_quest_clock() == 7


def test_talk_to_missing_npc_does_not_advance_world():
    player = Player("不在场交谈", "散人")
    player.set_var("quest_clock", 7)
    player.location = "village_gate"
    _run_main_loop(player, ["交谈 村长", "退出"])
    assert player.get_quest_clock() == 7


def test_busy_idle_talk_does_not_advance_world():
    player = Player("忙碌空谈", "散人")
    player.set_var("quest_clock", 7)
    player.location = "village_chief_room"
    player.set_npc_state("村长", "busy", duration=4, reason="处理村务")
    _run_main_loop(player, ["交谈 村长", "退出"])
    assert player.get_quest_clock() == 7
    assert player.get_npc_state("村长") == "busy"


def test_busy_talk_with_topic_still_advances_world():
    player = Player("忙碌问事", "散人")
    player.set_var("quest_clock", 7)
    player.location = "village_chief_room"
    player.set_npc_state("村长", "busy", duration=4, reason="处理村务")
    _run_main_loop(player, ["交谈 村长 委托", "退出"])
    assert player.get_quest_clock() == 8


def test_normal_talk_still_advances_world():
    player = Player("正常交谈", "散人")
    player.set_var("quest_clock", 7)
    player.location = "village_chief_room"
    _run_main_loop(player, ["交谈 村长", "退出"])
    assert player.get_quest_clock() == 8


def test_away_and_hostile_talk_return_false():
    away = Player("暂离返回", "散人")
    away.location = "medicine_shop"
    away.set_npc_state("药铺老板", "away", duration=5, reason="出门采买")
    _, result = _capture_talk(away, ["药铺老板"])
    assert result is False

    hostile = Player("敌对返回", "散人")
    hostile.set_var("quest_clock", 7)
    hostile.location = "village_gate"
    hostile.change_relation("守卫", -80)
    _, result = _capture_talk(hostile, ["守卫"])
    assert result is False


def test_business_rumor_talk_is_read_only():
    player = Player("营生查询", "散人")
    _, result = _capture_talk(player, ["营生"])
    assert result is False
