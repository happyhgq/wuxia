# -*- coding: utf-8 -*-
"""第一批：铁匠对外称谓统一为王铁匠，内部键与自称保持不变。"""
import contextlib
import io

import actor_display
import engine
from actions import handle_talk_and_ask
from player import Player


def _talk(player, name):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        handle_talk_and_ask(player, [name])
    return buf.getvalue()


def test_room_label_uses_visible_name_without_leading_space():
    label = actor_display.format_room_label("铁匠")
    assert label == "王铁匠"
    assert not label.startswith(" ")
    assert "青石村铁匠" not in label


def test_prose_name_uses_visible_name():
    assert actor_display.prose_name("铁匠") == "王铁匠"


def test_internal_key_still_targets_blacksmith():
    assert "铁匠" in engine.NPCS
    assert engine.NPCS["铁匠"]["name"] == "王铁匠"


def test_old_long_blacksmith_name_is_gone_from_player_text():
    blob = repr(engine.NPCS["铁匠"]) + repr(engine.QUESTS)
    assert "青石村铁匠" not in blob
    assert "王打铁" not in blob.replace("我王打铁", "")


def test_blacksmith_introduces_himself_with_real_name():
    first_line = engine.NPCS["铁匠"]["dialogue"][0]
    assert first_line.startswith("我王打铁")
    assert "王铁匠" not in first_line.split("，")[0]


def test_talk_accepts_visible_and_internal_names():
    player = Player("铁匠称谓验收", "散人")
    player.location = player.get_npc_location("铁匠")

    visible = _talk(player, "王铁匠")
    internal = _talk(player, "铁匠")

    for output in (visible, internal):
        assert "王铁匠" in output
        assert "我王打铁" in output
        assert "青石村铁匠" not in output


def test_quest_copy_uses_visible_name_only():
    texts = []
    for quest in engine.QUESTS.values():
        for key in ("notice", "desc"):
            value = quest.get(key)
            if isinstance(value, str):
                texts.append(value)
    blob = "\n".join(texts)
    assert "王打铁" not in blob
    assert "王铁匠" in blob
