"""Alpha275：V12 读档恢复、长周期续跑与跨系统状态一致性验收。"""
import copy
import json
import random
from unittest.mock import patch

import engine
from player import Player

_MISSING = object()
_NPC = next(iter(engine.NPCS))
_CRISIS = "alpha275_test_crisis"
_FACTION = "青石村"
_CONFLICT = "官府:黑市"


def _rich_world_state():
    return {
        "flags": {"alpha275_flag": True},
        "variables": {
            "quest_clock": 40,
            "world_crisis_last_roll": 36,
            "region_ecology": {
                "main": {"security": 61, "commerce": 55, "travel": 72, "tension": 2, "last_change": 35}
            },
            "region_activity": {
                "main": {
                    "security": 5,
                    "commerce": 2,
                    "travel": 1,
                    "events": {"caravan_ambush": {"last_reward_clock": 10}},
                    "security_incident": {
                        "started_clock": 30,
                        "expires_clock": 50,
                        "progress": 1,
                        "required_patrols": 2,
                        "status": "active",
                        "contributors": ["捕头"],
                        "result_text": "",
                    },
                }
            },
            "world_crises": {
                _CRISIS: {
                    "started_clock": 30,
                    "expires_clock": 60,
                    "status": "active",
                    "npc_relief": 0.1,
                    "player_relief": 0.2,
                    "effects": {"security": -5},
                    "npc_response": {},
                    "player_action": {},
                    "escalation": {},
                }
            },
            "npc_locations": {
                _NPC: {
                    "location": "village_gate",
                    "source": "schedule",
                    "until_clock": 50,
                    "last_schedule_move_clock": 40,
                }
            },
            "npc_autonomy": {
                _NPC: {
                    "last_action_clock": 40,
                    "last_action": "patrol",
                    "target": "",
                    "location": "village_gate",
                    "proactive_events": {"alpha275_event": 35},
                }
            },
            "faction_actions": {_FACTION: {"history": {"alpha275_action": 30}}},
            "faction_conflicts": {
                _CONFLICT: {
                    "relation": -20,
                    "pressure": 10,
                    "last_change": 30,
                    "history": [{"clock": 20, "level": "tension"}],
                }
            },
            "dynamic_world_stability": {"faction_recovery": {_FACTION: 30}},
            "player_information": {
                "topic_a": {
                    "topic": "topic_a",
                    "text": "黑风寨最近有人在村外踩点。",
                    "source": "说书先生",
                    "confidence": 80,
                    "learned_at": 30,
                    "sentiment": "neutral",
                }
            },
            "npc_information": {
                _NPC: {
                    "topic_b": {
                        "topic": "topic_b",
                        "text": "官府正在追查失窃的铁器。",
                        "source": _NPC,
                        "confidence": 70,
                        "learned_at": 28,
                        "sentiment": "neutral",
                    }
                }
            },
            "npc_proactive_events": [{"clock": 35, "event_id": "alpha275_event", "npc": _NPC}],
            "region_security_log": [{"clock": 30, "zone": "main", "text": "村口出现了可疑人影。"}],
            "faction_conflict_log": [{"clock": 20, "level": "tension"}],
            "quest_interventions": {"alpha275_quest:alpha": 25},
            "quest_competitions": {"alpha275_quest:beta": 27},
            "sect_state": {"current_sect": "散人", "reputation": {}},
        },
    }


def _rich_player():
    player = Player("Alpha275存档恢复", "散人")
    player.economy_state = {"tick": 40, "npc_gold": {"测试商人": 320}}
    player.world_state = _rich_world_state()
    player._ensure_sect_state()
    player._ensure_skill_state()
    return player


def _base_payload(tmp_path):
    player = _rich_player()
    path = tmp_path / "alpha275_base.json"
    assert player.save_to_file(str(path))
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["version"] == engine.SAVE_VERSION
    return payload, player


def _write_payload(payload, tmp_path, name="alpha275_case.json"):
    path = tmp_path / name
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def _load(payload, tmp_path, capsys, name="alpha275_case.json"):
    path = _write_payload(payload, tmp_path, name)
    loaded = Player.load_from_file(str(path))
    capsys.readouterr()
    return loaded


def _set(payload, keys, value):
    target = payload
    for key in keys[:-1]:
        target = target[key]
    target[keys[-1]] = value


def _at(*keys):
    def read(container):
        for key in keys:
            if not isinstance(container, dict) or key not in container:
                return _MISSING
            container = container[key]
        return container

    return read


def _variables(payload):
    return payload["world_state"]["variables"]


def _snapshot(player):
    variables = player.world_state.get("variables", {})
    durable_variables = {
        key: copy.deepcopy(value)
        for key, value in variables.items()
        if not key.startswith(("visited:", "visited_zone:"))
    }
    return json.loads(json.dumps({
        "clock": player.get_quest_clock(),
        "flags": {
            key: value for key, value in player.world_state.get("flags", {}).items()
            if not key.startswith(("visited:", "visited_zone:"))
        },
        "variables": durable_variables,
        "economy_state": player.economy_state,
        "active_quests": player.active_quests,
        "quest_states": player.quest_states,
        "completed_quests": player.completed_quests,
        "inventory": player.inventory,
        "gold": player.gold,
    }, ensure_ascii=False, sort_keys=True))


def _corruption_cases():
    v = "world_state", "variables"
    return [
        (v + ("quest_clock",), "坏档", _at("quest_clock"), 0),
        (v + ("world_crisis_last_roll",), "坏档", _at("world_crisis_last_roll"), -999999),
        (v + ("region_ecology", "main", "security"), "坏档", _at("region_ecology", "main", "security"), _MISSING),
        (v + ("region_ecology", "main", "tension"), "坏档", _at("region_ecology", "main", "tension"), _MISSING),
        (v + ("region_activity", "main", "events"), None, _at("region_activity", "main", "events"), {}),
        (v + ("region_activity", "main", "security_incident", "expires_clock"), "坏档",
         _at("region_activity", "main", "security_incident", "expires_clock"), 0),
        (v + ("region_activity", "main", "security_incident", "status"), 5,
         _at("region_activity", "main", "security_incident", "status"), "expired"),
        (v + ("region_activity", "main", "security_incident", "contributors"), "坏档",
         _at("region_activity", "main", "security_incident", "contributors"), []),
        (v + ("world_crises", _CRISIS, "expires_clock"), "坏档",
         _at("world_crises", _CRISIS, "expires_clock"), 0),
        (v + ("world_crises", _CRISIS, "npc_relief"), "坏档", _at("world_crises", _CRISIS, "npc_relief"), 0.0),
        (v + ("world_crises", _CRISIS, "effects"), [], _at("world_crises", _CRISIS, "effects"), {}),
        (v + ("world_crises", _CRISIS), [], _at("world_crises", _CRISIS), _MISSING),
        (v + ("npc_locations", _NPC, "source"), 5, _at("npc_locations", _NPC, "source"), ""),
        (v + ("npc_locations", _NPC, "location"), [], _at("npc_locations", _NPC, "location"), _MISSING),
        (v + ("npc_locations", _NPC), [], _at("npc_locations", _NPC), _MISSING),
        (v + ("npc_autonomy", _NPC, "proactive_events"), "坏档",
         _at("npc_autonomy", _NPC, "proactive_events"), {}),
        (v + ("npc_autonomy", _NPC), [], _at("npc_autonomy", _NPC), _MISSING),
        (v + ("faction_actions", _FACTION, "history"), None,
         _at("faction_actions", _FACTION, "history"), {}),
        (v + ("faction_conflicts", _CONFLICT, "relation"), "坏档",
         _at("faction_conflicts", _CONFLICT, "relation"), -100),
        (v + ("faction_conflicts", _CONFLICT, "history"), {},
         _at("faction_conflicts", _CONFLICT, "history"), []),
        (v + ("dynamic_world_stability",), [], _at("dynamic_world_stability"), {}),
        (v + ("dynamic_world_stability", "faction_recovery"), None,
         _at("dynamic_world_stability", "faction_recovery"), {}),
        (v + ("player_information", "topic_a", "confidence"), "坏档",
         _at("player_information", "topic_a", "confidence"), 50),
        (v + ("npc_information", _NPC, "topic_b", "confidence"), "坏档",
         _at("npc_information", _NPC, "topic_b", "confidence"), 50),
        (v + ("npc_information", _NPC), "坏档", _at("npc_information", _NPC), _MISSING),
        (v + ("sect_state", "current_sect"), {}, _at("sect_state", "current_sect"), "散人"),
        (v + ("npc_proactive_events",), {}, _at("npc_proactive_events"), []),
        (v + ("region_security_log",), {}, _at("region_security_log"), []),
        (v + ("quest_interventions",), "坏档", _at("quest_interventions"), {}),
        (v + ("quest_competitions",), "坏档", _at("quest_competitions"), {}),
    ]


def test_corrupted_save_state_is_recovered_before_world_tick(tmp_path, capsys):
    payload, _ = _base_payload(tmp_path)
    for keys, bad_value, read, expected in _corruption_cases():
        corrupted = copy.deepcopy(payload)
        _set(corrupted, keys, bad_value)
        loaded = _load(corrupted, tmp_path, capsys)
        assert loaded is not None, "存档读档失败：" + ".".join(keys)
        actual = read(loaded.world_state["variables"])
        assert actual == expected or (actual is _MISSING and expected is _MISSING), (
            "恢复结果不符：" + ".".join(keys) + f" 实际={actual!r} 期望={expected!r}"
        )
        loaded.tick_quest_clock(2)


def test_valid_dynamic_state_roundtrip_keeps_player_progress(tmp_path, capsys):
    payload, player = _base_payload(tmp_path)
    loaded = _load(payload, tmp_path, capsys)
    assert loaded is not None
    for key in (
        "region_activity", "region_ecology", "world_crises", "npc_locations", "npc_autonomy",
        "faction_actions", "faction_conflicts", "dynamic_world_stability",
        "player_information", "npc_information", "npc_proactive_events",
        "region_security_log", "faction_conflict_log", "quest_interventions", "quest_competitions",
    ):
        assert loaded.world_state["variables"][key] == player.world_state["variables"][key], key
    assert loaded.get_quest_clock() == 40
    assert loaded.economy_state == player.economy_state
    assert loaded.world_state["flags"]["alpha275_flag"] is True


def test_recovered_state_survives_second_save_and_long_cycle_continuation(tmp_path, capsys):
    payload, _ = _base_payload(tmp_path)
    corrupted = copy.deepcopy(payload)
    variables = _variables(corrupted)
    variables["quest_clock"] = "坏档"
    variables["region_activity"]["main"]["events"] = None
    variables["npc_autonomy"][_NPC]["proactive_events"] = "坏档"
    variables["faction_actions"][_FACTION]["history"] = None
    variables["dynamic_world_stability"]["faction_recovery"] = None
    variables["player_information"]["topic_a"]["confidence"] = "坏档"
    variables["npc_proactive_events"] = {}

    with patch("economy.manager.time.time", return_value=1_800_000_000.0):
        recovered = _load(corrupted, tmp_path, capsys, "alpha275_recovered.json")
        assert recovered is not None
        random.seed(2751)
        recovered.tick_quest_clock(30)
        snapshot = _snapshot(recovered)

        second_path = tmp_path / "alpha275_second_save.json"
        assert recovered.save_to_file(str(second_path))
        capsys.readouterr()
        resumed = Player.load_from_file(str(second_path))
        capsys.readouterr()
        assert resumed is not None
        assert _snapshot(resumed) == snapshot

        random.seed(2752)
        resumed.tick_quest_clock(30)
        after_resume = _snapshot(resumed)

        reference = _load(corrupted, tmp_path, capsys, "alpha275_reference.json")
        assert reference is not None
        random.seed(2751)
        reference.tick_quest_clock(30)
        random.seed(2752)
        reference.tick_quest_clock(30)

    assert after_resume == _snapshot(reference)


def test_long_cycle_with_mid_cycle_save_matches_uninterrupted_run(tmp_path, capsys):
    uninterrupted, resumed = _rich_player(), _rich_player()
    with patch("economy.manager.time.time", return_value=1_800_000_000.0):
        random.seed(2753)
        uninterrupted.tick_quest_clock(45)
        random.seed(2753)
        resumed.tick_quest_clock(45)

        path = tmp_path / "alpha275_mid_cycle.json"
        assert resumed.save_to_file(str(path))
        capsys.readouterr()
        loaded = Player.load_from_file(str(path))
        capsys.readouterr()
        assert loaded is not None

        random.seed(2754)
        uninterrupted.tick_quest_clock(90)
        random.seed(2754)
        loaded.tick_quest_clock(90)

    assert _snapshot(loaded) == _snapshot(uninterrupted)


def test_information_confidence_condition_tolerates_corrupt_value(tmp_path, capsys):
    payload, _ = _base_payload(tmp_path)
    corrupted = copy.deepcopy(payload)
    _variables(corrupted)["player_information"]["topic_a"]["confidence"] = "坏档"
    loaded = _load(corrupted, tmp_path, capsys)
    assert loaded is not None
    condition = {"npc_information": {"topic_a": {"min_confidence": 60}}}
    assert engine.check_conditions(condition, loaded.world_state, loaded.completed_quests, loaded) is False
