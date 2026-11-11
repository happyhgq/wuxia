"""Alpha163：少林藏经阁线索可在晋升前合法取得，避免晋升条件与门禁互锁。"""
import engine
from player import Player
from travel_system import room_access_denial


def make_shaolin_player(rank_index):
    player = Player("门禁核查", "散人")
    player.level = max(player.level, 3)
    ok, message = player.join_sect("少林")
    assert ok, message
    player._sect_progress_state().setdefault("少林", {})["official_rank_index"] = rank_index
    return player


def test_shaolin_scripture_court_is_accessible_to_transmission_disciple():
    player = make_shaolin_player(3)
    assert room_access_denial(player, engine.ROOMS["shaolin_scripture_court"]) == ""


def test_shaolin_scripture_court_remains_closed_to_monk_rank():
    player = make_shaolin_player(2)
    denial = room_access_denial(player, engine.ROOMS["shaolin_scripture_court"])
    assert "传法弟子" in denial


def test_scripture_gate_no_longer_deadlocks_highest_rank_promotion():
    player = make_shaolin_player(3)
    req = player.get_sect_promotion_requirements("少林")
    assert req["target_rank"] == "少林传承弟子"
    assert req["required_flags"] == ["sect:shaolin:scripture_catalogue_reviewed"]
    assert room_access_denial(player, engine.ROOMS["shaolin_scripture_court"]) == ""
