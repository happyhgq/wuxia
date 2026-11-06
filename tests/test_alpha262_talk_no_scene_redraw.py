"""Alpha262：同场景交谈与 NPC 动态消息不得触发场景整段重绘。"""
import builtins
import contextlib
import io
from unittest.mock import Mock, patch

import engine
import main


class _LoopPlayer:
    def __init__(self):
        self.location = "village_square"
        self.world_state = {"variables": {}}
        self.tick_count = 0
        self.saved = 0

    def mark_visited(self, _room):
        return None

    def tick_quest_clock(self, steps=1):
        self.tick_count += steps
        # 模拟 NPC 自主行动产生的动态消息；消息本身不应触发 look。
        print("【附近动态】守卫刚刚沿街巡查。")

    def get_quest_clock(self):
        return self.tick_count

    def drain_npc_movement_messages(self):
        return []

    def save_to_file(self, filename=None, verbose=True):
        self.saved += 1

    def begin_deferred_save(self):
        self._save_deferred = True

    def flush_deferred_save(self):
        self._save_deferred = False
        return False


def _run_loop(commands):
    player = _LoopPlayer()
    look_spy = Mock()
    talk_spy = Mock()
    output = io.StringIO()
    with patch.object(main.os.path, "exists", return_value=True), \
         patch.object(main.Player, "load_from_file", return_value=player), \
         patch.object(builtins, "input", return_value="y"), \
         patch.object(main, "read_command", side_effect=list(commands)), \
         patch.object(main, "clear_screen"), \
         patch.object(main, "look", look_spy), \
         patch.object(main, "handle_talk_and_ask", talk_spy), \
         patch.object(main, "announce_pending_caravan_arrivals"), \
         contextlib.redirect_stdout(output):
        main.main()
    return player, look_spy, talk_spy, output.getvalue()


def test_talk_in_same_room_does_not_redraw_scene_and_dynamic_message_stays_inline():
    player, look_spy, talk_spy, output = _run_loop(["交谈 村长", "退出"])

    # 唯一一次 look 是启动时的首次场景展示；交谈处理后没有第二次场景渲染。
    assert look_spy.call_count == 1
    talk_spy.assert_called_once_with(player, ["村长"])
    assert player.tick_count == 1
    assert "【附近动态】守卫刚刚沿街巡查。" in output
    assert player.saved == 1


def test_explicit_look_redraws_scene_but_talk_does_not():
    player, look_spy, talk_spy, _output = _run_loop(["交谈 村长", "查看", "退出"])

    # 启动时一次 + 玩家主动查看一次；交谈本身不增加场景渲染次数。
    assert look_spy.call_count == 2
    assert look_spy.call_args_list[0].args == (player,)
    assert talk_spy.call_count == 1
    assert player.tick_count == 1


def test_talk_is_excluded_from_generic_world_tick_policy():
    assert main.command_advances_world("talk", ["村长"]) is False



def test_busy_talk_does_not_advance_world_tick():
    player = _LoopPlayer()
    output = io.StringIO()
    with patch.object(main.os.path, "exists", return_value=True), \
         patch.object(main.Player, "load_from_file", return_value=player), \
         patch.object(builtins, "input", return_value="y"), \
         patch.object(main, "read_command", side_effect=["交谈 村长", "退出"]), \
         patch.object(main, "clear_screen"), \
         patch.object(main, "look"), \
         patch.object(main, "handle_talk_and_ask", return_value=False), \
         patch.object(main, "announce_pending_caravan_arrivals"), \
         contextlib.redirect_stdout(output):
        main.main()
    assert player.tick_count == 0
