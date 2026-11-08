"""P4.1：天气与二十四节气氛围回归（只影响文案与状态显示）。"""

import contextlib
import io
import json

import main
import weather
import world_ambience
from player import Player


def _player(room="village_gate", tick=0, name="天气验收"):
    player = Player(name, "散人")
    player.location = room
    player.set_var("quest_clock", tick)
    return player


def _capture(player, blocked=False):
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        messages = world_ambience.announce(player, blocked=blocked)
    return messages, buffer.getvalue()


def test_first_read_stays_silent_and_clear_until_next_dawn():
    player = _player(tick=9)
    messages, output = _capture(player)
    assert messages == [] and output == ""
    state = weather._state(player, 9)
    assert state["kind"] == "clear"
    assert state["until_tick"] == 24
    assert state["term_ordinal"] == 0
    assert weather.snapshot(player)["label"] == "晴"


def test_weather_changes_only_at_dawn_and_never_repeats():
    player = _player(tick=0)
    _capture(player)
    kind, changed = weather.advance(player, 23)
    assert kind == "clear" and changed is False
    seen = []
    previous = "clear"
    for day in range(1, 61):
        kind, changed = weather.advance(player, day * 24)
        if changed:
            assert kind != previous
            seen.append(kind)
            previous = kind
    assert len(seen) >= 20
    assert all(a != b for a, b in zip(seen, seen[1:]))


def test_weather_sequence_is_identical_whether_stepped_or_jumped():
    stepped = _player(tick=0)
    jumped = _player(tick=0)
    _capture(stepped)
    _capture(jumped)
    for tick in range(1, 24 * 30 + 1):
        stepped.set_var("quest_clock", tick)
        _capture(stepped)
    jumped.set_var("quest_clock", 24 * 30)
    _capture(jumped)
    left = weather._state(stepped, 24 * 30)
    right = weather._state(jumped, 24 * 30)
    assert (left["kind"], left["until_tick"], left["term_ordinal"]) == (
        right["kind"], right["until_tick"], right["term_ordinal"]
    )


def test_weather_duration_is_always_one_to_three_days():
    player = _player(tick=0)
    _capture(player)
    durations = []
    previous_until = weather._state(player, 0)["until_tick"]
    for day in range(1, 121):
        _kind, changed = weather.advance(player, day * 24)
        state = weather._state(player, day * 24)
        if changed:
            durations.append((state["until_tick"] - previous_until) // 24)
        previous_until = state["until_tick"]
    assert durations
    assert set(durations) <= {1, 2, 3}


def test_all_24_terms_cycle_in_order():
    player = _player(tick=0)
    _capture(player)
    seen = []
    for index in range(1, 25):
        tick = index * weather.TICKS_PER_TERM
        player.set_var("quest_clock", tick)
        world_ambience._state(player)["last_scene_tick"] = tick
        messages, _output = _capture(player)
        terms = [text for text in messages if text.startswith("节气已至")]
        assert len(terms) == 1, (index, messages)
        seen.append(terms[0])
    expected = [
        f"节气已至{weather.TERMS[index]}，{weather.TERM_TEXTS[index]}"
        for index in range(1, 24)
    ] + [f"节气已至{weather.TERMS[0]}，{weather.TERM_TEXTS[0]}"]
    assert seen == expected


def test_season_and_term_follow_the_360_day_calendar():
    assert weather.term_for_tick(0) == "立春"
    assert weather.season_for_tick(0) == "春"
    assert weather.term_for_tick(6 * 15 * 24) == "立夏"
    assert weather.season_for_tick(6 * 15 * 24) == "夏"
    assert weather.term_for_tick(12 * 15 * 24) == "立秋"
    assert weather.season_for_tick(12 * 15 * 24) == "秋"
    assert weather.term_for_tick(18 * 15 * 24) == "立冬"
    assert weather.season_for_tick(18 * 15 * 24) == "冬"
    assert weather.term_for_tick(24 * 15 * 24) == "立春"


def test_seasonal_tables_avoid_impossible_weather():
    for season, table in weather._WEATHER_TABLES.items():
        kinds = {kind for kind, _weight in table}
        assert kinds <= set(weather.KIND_LABELS)
        if season == "冬":
            assert "snow" in kinds
            assert "rain" not in kinds and "storm" not in kinds
        else:
            assert "snow" not in kinds


def test_term_message_appears_once_every_fifteen_days():
    player = _player(tick=0)
    _capture(player)
    world_ambience._state(player)["last_scene_tick"] = 360
    player.set_var("quest_clock", 360)
    messages, _output = _capture(player)
    assert any(text.startswith("节气已至雨水") for text in messages)
    assert _capture(player)[0] == []
    world_ambience._state(player)["last_scene_tick"] = 720
    player.set_var("quest_clock", 720)
    messages, _output = _capture(player)
    assert any(text.startswith("节气已至惊蛰") for text in messages)


def test_skipped_weather_and_terms_only_report_the_latest():
    player = _player(tick=0)
    _capture(player)
    world_ambience._state(player)["last_scene_tick"] = 3 * weather.TICKS_PER_TERM
    player.set_var("quest_clock", 3 * weather.TICKS_PER_TERM)
    messages, _output = _capture(player)
    terms = [text for text in messages if text.startswith("节气已至")]
    assert terms == [f"节气已至{weather.TERMS[3]}，{weather.TERM_TEXTS[3]}"]
    assert weather._state(player, 3 * weather.TICKS_PER_TERM)["term_ordinal"] == 3
    transitions = [
        text
        for text in messages
        if any(text in variants for variants in world_ambience._WEATHER_TRANSITIONS.values())
    ]
    assert len(transitions) <= 1


def test_phase_and_weather_changes_merge_into_one_message():
    player = _player(tick=9)
    _capture(player)
    world_ambience._state(player)["last_scene_tick"] = 24
    player.set_var("quest_clock", 24)
    messages, _output = _capture(player)
    kind = weather._state(player, 24)["kind"]
    assert kind != "clear"
    assert messages == [world_ambience._WEATHER_PHASE_MESSAGES[kind]["dawn"]]


def test_weather_message_precedes_term_message_on_the_same_dawn():
    player = _player(tick=0)
    _capture(player)
    state = weather._state(player, 0)
    state["kind"] = "clear"
    state["until_tick"] = weather.TICKS_PER_TERM
    world_ambience._state(player)["last_scene_tick"] = weather.TICKS_PER_TERM
    player.set_var("quest_clock", weather.TICKS_PER_TERM)
    messages, _output = _capture(player)
    assert messages[0] in world_ambience._WEATHER_TRANSITIONS[weather._state(player, weather.TICKS_PER_TERM)["kind"]]
    assert messages[1].startswith("节气已至雨水")


def test_indoor_dawn_reports_time_phase_then_indoor_weather():
    player = _player(room="general_shop", tick=9)
    _capture(player)
    world_ambience._state(player)["last_scene_tick"] = 24
    player.set_var("quest_clock", 24)
    messages, _output = _capture(player)
    kind = weather._state(player, 24)["kind"]
    assert kind != "clear"
    assert messages == [
        world_ambience._INDOOR_PHASE_MESSAGES["dawn"],
        world_ambience._WEATHER_TRANSITIONS[kind][1],
    ]


def test_weather_deferred_at_five_messages_reports_latest_once_next_turn():
    player = _player(room="general_shop", tick=9)
    _capture(player)
    world_ambience._state(player)["last_scene_tick"] = 24
    _fill_with_special(player)
    player.set_var("quest_clock", 24)
    messages, _output = _capture(player)
    kind = weather._state(player, 24)["kind"]
    weather_text = world_ambience._WEATHER_TRANSITIONS[kind][1]
    assert len(messages) == 5
    assert weather_text not in messages
    follow_up, _output = _capture(player)
    assert follow_up == [world_ambience._INDOOR_PHASE_MESSAGES["dawn"], weather_text]
    assert _capture(player)[0] == []


def test_wait_order_is_traffic_then_weather_then_term():
    player = _player(tick=0)
    _capture(player)
    state = weather._state(player, 0)
    state["kind"] = "clear"
    state["until_tick"] = weather.TICKS_PER_TERM
    world_ambience._state(player)["last_scene_tick"] = weather.TICKS_PER_TERM
    player.set_var("quest_clock", weather.TICKS_PER_TERM)
    collected = world_ambience.collect_messages(player, include_traffic=True)
    messages = collected["messages"]
    assert len(messages) == 3
    assert messages[0] == collected["traffic"]
    assert messages[1] in world_ambience._WEATHER_TRANSITIONS[weather._state(player, weather.TICKS_PER_TERM)["kind"]]
    assert messages[2].startswith("节气已至雨水")


def test_term_message_is_deferred_behind_five_movements_then_flushed():
    player = _player(tick=0)
    _capture(player)
    world_ambience._state(player)["last_scene_tick"] = weather.TICKS_PER_TERM
    _fill_with_special(player)
    player.set_var("quest_clock", weather.TICKS_PER_TERM)
    messages, _output = _capture(player)
    assert len(messages) == 5
    assert weather._state(player, weather.TICKS_PER_TERM)["term_ordinal"] == 0
    follow_up, _output = _capture(player)
    assert any(text.startswith("节气已至雨水") for text in follow_up)
    assert weather._state(player, weather.TICKS_PER_TERM)["term_ordinal"] == 1


def test_indoor_transitions_never_use_outdoor_viewpoint():
    banned = ("外面", "屋外", "街上", "街上飘")
    for kind, (_outdoor, indoor) in world_ambience._WEATHER_TRANSITIONS.items():
        assert not any(phrase in indoor for phrase in banned), kind
        assert "檐外" in indoor or "远处" in indoor, kind


def test_outdoor_and_indoor_use_different_weather_wording():
    outdoor = _player(room="village_gate")
    indoor = _player(room="general_shop")
    for player in (outdoor, indoor):
        _capture(player)
        world_ambience._state(player)["last_scene_tick"] = 24
        player.set_var("quest_clock", 24)
    outdoor_messages, _output = _capture(outdoor)
    indoor_messages, _output = _capture(indoor)
    kind = weather._state(outdoor, 24)["kind"]
    assert kind != "clear"
    assert outdoor_messages[0] == world_ambience._WEATHER_TRANSITIONS[kind][0]
    assert indoor_messages[0] == world_ambience._WEATHER_TRANSITIONS[kind][1]
    assert outdoor_messages[0] != indoor_messages[0]


def test_rain_overrides_outdoor_phase_text_but_not_indoor():
    outdoor = _player(tick=9)
    _capture(outdoor)
    weather._state(outdoor, 9)["kind"] = "rain"
    weather._state(outdoor, 9)["until_tick"] = 100
    world_ambience._state(outdoor)["last_scene_tick"] = 10
    outdoor.set_var("quest_clock", 10)
    messages, _output = _capture(outdoor)
    assert messages == [world_ambience._WEATHER_PHASE_MESSAGES["rain"]["dusk"]]

    indoor = _player(room="general_shop", tick=9)
    _capture(indoor)
    weather._state(indoor, 9)["kind"] = "rain"
    weather._state(indoor, 9)["until_tick"] = 100
    # 直接改写天气状态后同步确认标记，只验证天色措辞。
    world_ambience._state(indoor)["weather_seen"] = ["rain", 100]
    world_ambience._state(indoor)["last_scene_tick"] = 10
    indoor.set_var("quest_clock", 10)
    messages, _output = _capture(indoor)
    assert messages == [world_ambience.PHASE_MESSAGES["dusk"]]


def _fill_with_special(player):
    """制造五条不可合并的特殊移动，占满推送上限。"""
    names = ("守卫", "村长", "铁匠", "药铺老板", "柳三娘")
    for name in names:
        player.set_npc_location(name, player.location, "test", announce=False)
    player.drain_npc_movement_messages()
    for name in names:
        player.set_npc_offstage(name)


def test_weather_change_is_deferred_behind_five_movements_then_flushed():
    player = _player(tick=0)
    _capture(player)
    world_ambience._state(player)["last_scene_tick"] = 24
    _fill_with_special(player)
    player.set_var("quest_clock", 24)
    messages, _output = _capture(player)
    assert len(messages) == 5
    # 五条满时只延后文案；天气状态仍推进，面板不会显示旧天色。
    assert weather._state(player, 24)["kind"] != "clear"
    follow_up, _output = _capture(player)
    assert len(follow_up) == 1
    assert follow_up[0] in world_ambience._WEATHER_TRANSITIONS[weather._state(player, 24)["kind"]]


def test_blocked_flush_keeps_weather_until_panel_closes():
    player = _player(tick=0)
    _capture(player)
    world_ambience._state(player)["last_scene_tick"] = 24
    player.set_var("quest_clock", 24)
    messages, output = _capture(player, blocked=True)
    assert messages == [] and output == ""
    assert weather._state(player, 24)["kind"] == "clear"
    messages, _output = _capture(player)
    assert len(messages) == 1
    assert weather._state(player, 24)["kind"] != "clear"


def test_weather_state_roundtrips_inside_v12_variables(tmp_path):
    player = _player(tick=0)
    _capture(player)
    world_ambience._state(player)["last_scene_tick"] = 24
    player.set_var("quest_clock", 24)
    _capture(player)
    kind = weather._state(player, 24)["kind"]
    path = tmp_path / "weather_save.json"
    assert player.save_to_file(str(path))
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["version"] == 12
    assert "weather_world" in raw["world_state"]["variables"]
    loaded = Player.load_from_file(str(path))
    assert weather.current_kind(loaded, 24) == kind
    assert weather.snapshot(loaded)["label"] == weather.KIND_LABELS[kind]
    assert _capture(loaded)[0] == []


def test_status_panel_shows_season_term_and_weather():
    player = _player(tick=0)
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        main.show_status(player)
    rendered = output.getvalue()
    assert "天时：" in rendered
    assert "立春 · 晴" in rendered
    assert "春·立春" not in rendered
    player.set_var("quest_clock", 24)
    _capture(player)
    info = weather.snapshot(player)
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        main.show_status(player)
    assert f"{info['term']} · {info['label']}" in output.getvalue()


def test_status_panel_shows_current_weather_when_message_is_crowded_out():
    player = _player(room="general_shop", tick=23)
    _capture(player)
    world_ambience._state(player)["last_scene_tick"] = 24
    _fill_with_special(player)
    player.set_var("quest_clock", 24)
    messages, _output = _capture(player)
    assert len(messages) == 5
    kind = weather._state(player, 24)["kind"]
    assert kind != "clear"
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        main.show_status(player)
    assert f"立春 · {weather.KIND_LABELS[kind]}" in output.getvalue()


def test_help_explains_weather_is_ambience_only():
    for topic in ("天气", "节气", "天时"):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            main.show_help(topic)
        rendered = output.getvalue()
        assert "【天气】" in rendered
        assert "不改变战斗" in rendered
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        main.show_help()
    menu = output.getvalue()
    assert "状态与成长" in menu
    assert "【天气】" not in menu
