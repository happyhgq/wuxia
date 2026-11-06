"""Alpha195：铁衣门拜师、武学门槛、历练与晋升闭环回归。"""
from contextlib import redirect_stdout
from io import StringIO

import engine
from actions import handle_sect
from player import Player


def _ready_tieyi_player(name="铁衣门流程验收"):
    player = Player(name, "散人")
    player.level = 25
    player.location = "tieyi_guest_hall"
    player.set_flag("sect:tieyi:entry_interview", True)
    ok, message = player.join_sect("铁衣门")
    assert ok, message
    return player


def test_tieyi_entry_is_gated_by_real_guest_hall_and_interview_flag():
    player = Player("铁衣门入门门槛验收", "散人")
    player.level = 10
    player.location = "tieyi_foothill"
    output = StringIO()
    with redirect_stdout(output):
        handle_sect(player, ["拜师", "铁衣门"])
    assert player.get_sect() == "散人"
    assert "接待堂" in output.getvalue()

    player.location = "tieyi_guest_hall"
    output = StringIO()
    with redirect_stdout(output):
        handle_sect(player, ["拜师", "铁衣门"])
    assert player.get_sect() == "散人"
    assert "登记" in output.getvalue()

    player.set_flag("sect:tieyi:entry_interview", True)
    with redirect_stdout(StringIO()):
        handle_sect(player, ["拜师", "铁衣门"])
    assert player.get_sect() == "铁衣门"
    assert player.get_sect_official_rank_index("铁衣门") == 0
    assert player.get_flag("sect:tieyi:joined", False)


def test_tieyi_exclusive_skill_respects_rank_and_reputation_gates():
    player = _ready_tieyi_player()
    assert player.get_skill_progress("铁衣功")["learned"]
    ok, reason = player.can_learn_skill("破阵刀")
    assert not ok and "声望不足" in reason

    player.change_sect_reputation("铁衣门", 35)
    ok, reason = player.can_learn_skill("破阵刀")
    assert not ok and "身份不足" in reason

    player._sect_progress_state()["铁衣门"]["official_rank_index"] = 1
    ok, reason = player.can_learn_skill("破阵刀")
    assert ok, reason
    ok, reason = player.learn_skill("破阵刀")
    assert ok, reason
    assert player.get_skill_progress("破阵刀")["learned"]


def test_tieyi_trial_quest_is_required_for_real_promotion_and_success_updates_rank():
    player = _ready_tieyi_player("铁衣门晋升闭环验收")
    player.location = "tieyi_training_ground"
    player.change_sect_reputation("铁衣门", 200)
    progress = player._sect_progress_state()["铁衣门"]
    progress["official_rank_index"] = 2
    player._skill_state()["铁衣功"] = {"learned": True, "mastery": 80}
    assert "铁衣门历练·护路除匪" in engine.QUESTS
    assert "铁衣门传功师父" in player.get_npcs_in_room(player.location)

    output = StringIO()
    with redirect_stdout(output):
        handle_sect(player, ["晋升"])
    assert player.get_sect_official_rank_index("铁衣门") == 2
    assert "护路除匪" in output.getvalue()

    player.completed_quests.append("铁衣门历练·护路除匪")
    output = StringIO()
    with redirect_stdout(output):
        handle_sect(player, ["晋升"])
    assert player.get_sect_official_rank_index("铁衣门") == 3
    assert "执事弟子" in output.getvalue()

    output = StringIO()
    with redirect_stdout(output):
        handle_sect(player, ["晋升"])
    assert player.get_sect_official_rank_index("铁衣门") == 4
    assert "铁衣传人" in output.getvalue()


def test_tieyi_trial_quest_acceptance_and_progress_are_connected_to_actual_target():
    player = _ready_tieyi_player("铁衣门历练联动验收")
    player.location = engine.NPCS["铁衣门接引执事"].get("room", "tieyi_guest_hall")
    # NPC placement is defined by room data; locate the actual registered giver.
    player.location = next(room_id for room_id, room in engine.ROOMS.items()
                           if "铁衣门接引执事" in room.get("npcs", []))
    quest = engine.QUESTS["铁衣门历练·护路除匪"]
    assert quest["npc"] in engine.ROOMS[player.location]["npcs"]
    assert quest["turn_in_npc"] == quest["npc"]
    assert quest["target_type"] == "kill" and quest["required_cnt"] == 2

    player.active_quests["铁衣门历练·护路除匪"] = 0
    player.quest_states["铁衣门历练·护路除匪"] = {"stage": 0, "progress": 0}
    player.update_quest_progress("劫镖山贼", "kill")
    assert player.active_quests["铁衣门历练·护路除匪"] == 1
    player.update_quest_progress("劫镖山贼", "kill")
    assert player.active_quests["铁衣门历练·护路除匪"] == 2


def test_leaving_tieyi_resets_active_rank_and_rejoining_does_not_restore_old_rank():
    player = _ready_tieyi_player("铁衣门退门兼容验收")
    player._sect_progress_state()["铁衣门"]["official_rank_index"] = 3
    ok, message = player.leave_sect()
    assert ok, message
    assert player.get_sect() == "散人"
    assert player.get_sect_official_rank_index("铁衣门") == 0
    player.level = 3
    ok, message = player.join_sect("铁衣门")
    assert ok, message
    assert player.get_sect_official_rank_index("铁衣门") == 0
    assert player.get_skill_progress("破阵刀")["learned"] is False
