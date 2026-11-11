"""Alpha218：修复资源提示、尸体说明、守山岗位状态和接引拜师流程。"""
import contextlib
import io
import json
from pathlib import Path
from unittest.mock import patch

import engine
import world_lifecycle
from actions import handle_talk_and_ask, look
from player import Player
from ui_output import _ANSI_RE

ROOT = Path(__file__).resolve().parents[1]


def capture(fn, *args, **kwargs):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        fn(*args, **kwargs)
    return _ANSI_RE.sub("", out.getvalue())


def test_corpse_inspection_has_only_player_facing_state():
    p = Player("尸体查看测试", "散人")
    p.location = "village_gate"
    with patch.object(world_lifecycle, "visible_enemies", return_value=([], [{"name": "野猪"}])):
        output = capture(__import__("actions").look, p, ["野猪的尸体"])
    assert "【野猪的尸体】" in output
    assert "尸体已经失去生命迹象" in output
    assert "此版本保留尸体身份" not in output
    assert "不会重复发放战利品" not in output


def test_gate_guards_use_distinct_post_status_in_scene_people_list():
    expected = {
        "huashan_gate": ("华山守门弟子", "华山山门前巡视"),
        "shaolin_gate": ("少林守山僧", "少林山门前值守"),
        "wudang_gate": ("武当守山弟子", "武当山门前值守"),
    }
    for room_id, (npc_name, phrase) in expected.items():
        p = Player("守山状态测试", "散人")
        p.location = room_id
        with patch.object(p, "get_npcs_in_room", return_value=[npc_name]):
            output = capture(look, p)
        assert phrase in output
        assert f"{npc_name}：在住处休息" not in output


def test_zero_delta_dialogue_does_not_print_relation_change():
    p = Player("关系显示测试", "散人")
    p.location = "huashan_guest_hall"
    output = capture(handle_talk_and_ask, p, ["华山接引执事", "访客规矩"])
    assert "访客可以在山门与迎客厅停留" in output
    assert "关系变化：+0" not in output


def test_receptionist_baishi_topic_completes_admission_without_extra_command():
    cases = [
        ("huashan_guest_hall", "华山接引执事", "华山"),
        ("shaolin_guest_hall", "少林接引僧", "少林"),
        ("wudang_guest_hall", "武当接引道人", "武当"),
        ("tieyi_guest_hall", "铁衣门接引执事", "铁衣门"),
    ]
    for room_id, npc_name, sect_name in cases:
        p = Player("拜师流程测试", "散人")
        p.location = room_id
        p.level = 10
        output = capture(handle_talk_and_ask, p, [npc_name, "拜师"])
        assert p.get_sect() == sect_name, (npc_name, output)
        assert f"正式拜入【{sect_name}】" in output


def test_baishi_failure_names_required_and_current_level():
    p = Player("拜师条件测试", "散人")
    p.location = "tieyi_guest_hall"
    output = capture(handle_talk_and_ask, p, ["铁衣门接引执事", "拜师"])
    assert "拜师失败" in output
    assert "需达到 3 级" in output
    assert "当前 1 级" in output
    assert p.get_sect() == "散人"


def test_resource_room_prompts_do_not_repeat_search_as_gather_instructions():
    rooms = json.loads((ROOT / "data" / "rooms.json").read_text(encoding="utf-8"))
    old_phrases = ("输入“搜索”尝试采集", "输入“采集”或“搜索”尝试搜寻", "输入“搜索”尝试采集")
    for room_id, room in rooms.items():
        desc = str(room.get("desc", ""))
        for phrase in old_phrases:
            assert phrase not in desc, (room_id, phrase)
        assert desc.count("输入“搜索”可尝试获取") <= 1, room_id
