"""Alpha196：铁衣门真实任务交付、NPC日程、地图连通与存档恢复验收。"""
from contextlib import redirect_stdout
from io import StringIO
import json

import engine
from actions import handle_quest
from player import Player

QUEST = "铁衣门历练·护路除匪"


def _joined_player(name="铁衣门实玩验收"):
    p = Player(name, "散人")
    p.level = 10
    p.location = "tieyi_guest_hall"
    p.set_flag("sect:tieyi:entry_interview", True)
    ok, message = p.join_sect("铁衣门")
    assert ok, message
    p.set_flag("sect:tieyi:joined", True)
    return p


def test_tieyi_trial_can_be_accepted_progressed_and_turned_in_for_real(monkeypatch):
    p = _joined_player()
    p.location = "tieyi_guest_hall"
    starting_gold = p.gold
    starting_level = p.level
    monkeypatch.setattr(Player, "save_to_file", lambda self, filename=None: True)

    with redirect_stdout(StringIO()):
        handle_quest(p, "jiequ", [QUEST])
    assert QUEST in p.active_quests

    p.update_quest_progress("劫镖山贼", "kill")
    p.update_quest_progress("劫镖山贼", "kill")
    assert p.active_quests[QUEST] == 2

    output = StringIO()
    with redirect_stdout(output):
        handle_quest(p, "jiaofu", [QUEST])
    assert "恭喜完成任务" in output.getvalue()
    assert QUEST not in p.active_quests
    assert QUEST in p.completed_quests
    assert p.gold == starting_gold + 45
    assert p.level > starting_level or p.exp > 0
    assert p.get_sect_reputation("铁衣门") == 25


def test_tieyi_trial_requires_returning_to_actual_turn_in_npc(monkeypatch):
    p = _joined_player("铁衣门交付地点验收")
    monkeypatch.setattr(Player, "save_to_file", lambda self, filename=None: True)
    with redirect_stdout(StringIO()):
        handle_quest(p, "jiequ", [QUEST])
    p.update_quest_progress("劫镖山贼", "kill")
    p.update_quest_progress("劫镖山贼", "kill")
    p.location = "tieyi_training_ground"
    output = StringIO()
    with redirect_stdout(output):
        handle_quest(p, "jiaofu", [QUEST])
    assert "请回到【铁衣门接引执事】处交付任务" in output.getvalue()
    assert QUEST in p.active_quests
    assert QUEST not in p.completed_quests


def test_tieyi_guard_schedule_switches_between_gate_and_foothill():
    p = Player("铁衣门巡值验收", "散人")
    # 日程按现实钟点书写：08:00 山门、14:00 山麓、20:00 山门；tick 0 = 卯时 06:00。
    p.set_var("quest_clock", 2)
    assert p.get_npc_location("铁衣门守门弟子") == "tieyi_gate"
    p.set_var("quest_clock", 8)
    assert p.get_npc_location("铁衣门守门弟子") == "tieyi_foothill"
    p.set_var("quest_clock", 14)
    assert p.get_npc_location("铁衣门守门弟子") == "tieyi_gate"


def test_tieyi_route_is_bidirectionally_connected_to_existing_world():
    rooms = engine.ROOMS
    assert rooms["road_tieyi_turnoff"]["exits"]["东"] == "tieyi_foothill"
    assert rooms["tieyi_foothill"]["exits"]["西"] == "road_tieyi_turnoff"
    assert rooms["tieyi_foothill"]["exits"]["北"] == "tieyi_gate"
    assert rooms["tieyi_gate"]["exits"]["南"] == "tieyi_foothill"
    assert rooms["tieyi_gate"]["exits"]["东"] == "tieyi_guest_hall"
    assert rooms["tieyi_guest_hall"]["exits"]["西"] == "tieyi_gate"


def test_tieyi_identity_skills_quest_and_reputation_survive_v12_save_roundtrip(tmp_path):
    p = _joined_player("铁衣门存档恢复验收")
    p.change_sect_reputation("铁衣门", 42)
    p._sect_progress_state()["铁衣门"]["official_rank_index"] = 1
    p._skill_state()["破阵刀"] = {"learned": True, "mastery": 17}
    p.active_quests[QUEST] = 1
    p.quest_states[QUEST] = {"stage": 0, "progress": 1, "accepted_at": 12}
    p.location = "tieyi_training_ground"
    save_path = tmp_path / "tieyi_save.json"
    with redirect_stdout(StringIO()):
        assert p.save_to_file(str(save_path))
        loaded = Player.load_from_file(str(save_path))
    assert loaded is not None
    assert loaded.get_sect() == "铁衣门"
    assert loaded.get_sect_reputation("铁衣门") == 42
    assert loaded.get_sect_official_rank_index("铁衣门") == 1
    assert loaded.get_skill_progress("破阵刀")["learned"] is True
    assert loaded.get_skill_progress("破阵刀")["mastery"] == 17
    assert loaded.active_quests[QUEST] == 1
    assert loaded.quest_states[QUEST]["progress"] == 1
    assert loaded.location == "tieyi_training_ground"
    raw = json.loads(save_path.read_text(encoding="utf-8"))
    assert raw["version"] == engine.SAVE_VERSION == 12
