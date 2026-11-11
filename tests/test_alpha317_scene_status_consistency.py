"""Alpha317：静态岗位描述与作息忙碌措辞必须一致。"""
import contextlib
import io

import actions
import actor_display
from actions import handle_talk_and_ask
from player import Player
from ui_output import _ANSI_RE


def capture(fn, *args):
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        result = fn(*args)
    return _ANSI_RE.sub("", stream.getvalue()), result


def make_player(room, tick):
    player = Player("岗位措辞一致", "散人")
    player.location = room
    player.set_var("quest_clock", tick)
    return player


def npc_line(output, npc_name):
    label = actor_display.format_room_label(npc_name)
    for line in output.splitlines():
        if line.strip().startswith(label + "："):
            return line.strip()
    return ""


def test_guard_busy_schedule_overrides_static_scene_status():
    # tick 13 = 19:00，华山守门弟子按作息在 18-22 轮值巡查。
    player = make_player("huashan_guest_path", 13)
    output, _ = capture(actions.look, player)
    line = npc_line(output, "华山守门弟子")
    assert "轮值巡查山门" in line
    assert "巡视" not in line


def test_guard_busy_reply_uses_same_reason():
    player = make_player("huashan_guest_path", 13)
    output, _ = capture(handle_talk_and_ask, player, ["华山守门弟子"])
    assert "轮值巡查山门" in output
    assert "匆匆应了一声" in output


def test_guard_normal_hours_keep_scene_status():
    # tick 6 = 12:00，值守时段仍保留山门巡视的岗位描述。
    player = make_player("huashan_gate", 6)
    output, _ = capture(actions.look, player)
    line = npc_line(output, "华山守门弟子")
    assert "正在华山山门前巡视" in line


def test_apothecary_look_and_busy_reply_share_wording():
    # tick 9 = 15:00，药铺老板作息忙碌，场景行与短应答应为同一措辞。
    player = make_player("medicine_shop", 9)
    look_output, _ = capture(actions.look, player)
    talk_output, _ = capture(handle_talk_and_ask, player, ["药铺老板"])
    line = npc_line(look_output, "药铺老板")
    assert "正在柜台后照方抓药" in line
    assert "正在柜台后照方抓药" in talk_output
