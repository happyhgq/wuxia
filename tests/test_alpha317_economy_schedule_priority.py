"""Alpha317：日程明确在岗时，营生模拟文案不得把人物改写成停工。"""
import contextlib
import io
from unittest.mock import patch

import actions
from player import Player
from ui_output import _ANSI_RE


def capture(fn, *args):
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        result = fn(*args)
    return _ANSI_RE.sub("", stream.getvalue()), result


def player_at(room_id, clock):
    player = Player("营生日程优先级", "散人")
    player.location = room_id
    player.set_var("quest_clock", clock)
    return player


def people_line(output, npc_name):
    for line in output.splitlines():
        stripped = line.strip()
        if stripped.startswith("【") or "：" not in stripped:
            continue
        if npc_name in stripped.split("：", 1)[0]:
            return stripped
    return ""


def test_waiting_materials_text_yields_to_busy_schedule():
    # tick 2 = 08:00，木匠老许日程为“在广场边支起木架做活”。
    player = player_at("village_square", 2)
    with patch.object(actions, "_npc_economy_scene_status", return_value="正等着原料到货"):
        output, _ = capture(actions.look, player)
    line = people_line(output, "木匠老许")
    assert "支起木架做活" in line
    assert "原料" not in line


def test_economy_text_still_used_when_schedule_is_normal():
    # tick 0 = 06:00，铁匠日程为普通状态（生炉火、查铁料）。
    player = player_at("blacksmith", 0)
    with patch.object(actions, "_npc_economy_scene_status", return_value="正等着原料到货"):
        output, _ = capture(actions.look, player)
    line = people_line(output, "铁匠")
    assert "正等着原料到货" in line
    assert "生起炉火" not in line


def test_working_economy_text_also_yields_to_busy_schedule():
    player = player_at("village_square", 2)
    with patch.object(actions, "_npc_economy_scene_status", return_value="正在制作木剑"):
        output, _ = capture(actions.look, player)
    line = people_line(output, "木匠老许")
    assert "支起木架做活" in line
    assert "正在制作木剑" not in line
