"""Alpha179：客人通行许可不能绕过三大门派的高阶区域身份门槛。"""
import json
from pathlib import Path

from player import Player
from travel_system import room_access_denial

ROOT = Path(__file__).resolve().parents[1]
ROOMS = json.loads((ROOT / "data" / "rooms.json").read_text(encoding="utf-8"))

HIGH_RANK_ROOMS = [
    ("武当", "wudang_zhenwu_hall", 2),
    ("华山", "huashan_master_hall", 2),
]

# 少林讲经堂是受戒仪礼所在，入门弟子（身份 0）必须能进入；
# 访客许可仍然不能绕过门派归属限制。
SHAOLIN_ORDINATION_ROOM = ("少林", "shaolin_dharma_hall", 0)


def test_guest_access_does_not_bypass_high_rank_gate_for_any_major_sect():
    for sect, room_id, required_rank in HIGH_RANK_ROOMS:
        player = Player(f"访客权限测试-{sect}", "散人")
        player.set_flag(f"sect:{sect}:guest_access", True)
        denial = room_access_denial(player, ROOMS[room_id])
        assert denial, f"访客许可不应允许散人进入{ROOMS[room_id]['name']}"
        assert ROOMS[room_id]["access"]["min_rank_index"] == required_rank


def test_low_rank_member_is_still_blocked_from_high_rank_room():
    for sect, room_id, _required_rank in HIGH_RANK_ROOMS:
        player = Player(f"低阶身份测试-{sect}", "散人")
        assert player.join_sect(sect)[0]
        assert room_access_denial(player, ROOMS[room_id])


def test_sufficiently_promoted_member_can_enter_high_rank_room():
    for sect, room_id, required_rank in HIGH_RANK_ROOMS:
        player = Player(f"高阶身份测试-{sect}", "散人")
        assert player.join_sect(sect)[0]
        player._sect_progress_state().setdefault(sect, {})["official_rank_index"] = required_rank
        assert room_access_denial(player, ROOMS[room_id]) == ""


def test_shaolin_ordination_hall_is_open_to_entry_rank_but_not_guests():
    sect, room_id, required_rank = SHAOLIN_ORDINATION_ROOM
    guest = Player("少林受戒堂访客", "散人")
    guest.set_flag(f"sect:{sect}:guest_access", True)
    assert room_access_denial(guest, ROOMS[room_id]), "访客许可不应允许散人进入少林讲经堂"

    monk = Player("少林受戒堂弟子", "散人")
    assert monk.join_sect(sect)[0]
    assert monk._sect_progress_state().setdefault(sect, {}).get("official_rank_index", 0) == required_rank
    assert room_access_denial(monk, ROOMS[room_id]) == ""
