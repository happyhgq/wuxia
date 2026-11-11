"""Alpha317：势力冲突忙碌状态下的场景行与交谈提示必须一致。"""
import contextlib
import io

import actions
import actor_display
import engine
from actions import handle_talk_and_ask
from player import Player
from ui_output import _ANSI_RE


CONFLICT_SOURCE = "faction_conflict:青石村:黑风寨"
CONFLICT_REASON = "青石村与黑风寨局势升级至conflict"


def capture(fn, *args):
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        result = fn(*args)
    return _ANSI_RE.sub("", stream.getvalue()), result


def make_player(npc_name, state, quest=None):
    player = Player("冲突忙碌回归", "散人")
    player.set_var("quest_clock", 12)
    player.location = engine.NPCS[npc_name].get("home_room", "village_chief_room")
    player.set_npc_location(npc_name, player.location, source="alpha317")
    player.set_npc_state(npc_name, state, duration=99, reason=CONFLICT_REASON, source=CONFLICT_SOURCE)
    if quest:
        info = engine.QUESTS[quest]
        player.active_quests[quest] = 1
        player.quest_states[quest] = {"stage": 0, "progress": 0, "accepted_at": 12}
    return player


def npc_scene_line(output, npc_name):
    label = actor_display.format_room_label(npc_name)
    for line in output.splitlines():
        if line.strip().startswith(label + "："):
            return line.strip()
    return ""


def test_conflict_busy_scene_line_matches_unavailable_reply():
    player = make_player("村长", "busy")
    output, _ = capture(actions.look, player)
    line = npc_scene_line(output, "村长")
    assert "急事缠住" in line
    # 不能同时把日程里的“准备歇下”当作可交谈状态展示。
    assert "收拾桌上的茶碗" not in line
    assert "局势升级" not in line


def test_conflict_non_busy_scene_line_still_uses_schedule_reason():
    player = make_player("村长", "fear")
    output, _ = capture(actions.look, player)
    line = npc_scene_line(output, "村长")
    assert line
    assert "局势升级" not in line


def test_busy_talk_warns_progress_unchanged_for_pending_talk_objective():
    player = make_player("村长", "busy", quest="新手跑腿·送信")
    output, result = capture(handle_talk_and_ask, player, ["村长"])
    assert result is False
    assert "委托进度也就没有变化" in output
    assert player.quest_states["新手跑腿·送信"]["progress"] == 0


def test_busy_talk_without_talk_objective_has_no_progress_hint():
    player = make_player("村长", "busy", quest="新手狩猎·野外除害")
    output, _ = capture(handle_talk_and_ask, player, ["村长"])
    assert "委托进度也就没有变化" not in output


def test_normal_talk_never_shows_progress_hint():
    player = make_player("村长", "normal", quest="新手跑腿·送信")
    output, _ = capture(handle_talk_and_ask, player, ["村长"])
    assert "委托进度也就没有变化" not in output
