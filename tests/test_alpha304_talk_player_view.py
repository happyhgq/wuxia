"""Alpha304：交谈去面板、关系详情与玩家自身五段式观察。"""
import contextlib
import io
import os

import pytest

import actor_display
import engine
from actions import handle_relations, handle_talk_and_ask, look
from player import Player
from ui_output import _ANSI_RE

BASE = os.path.dirname(os.path.dirname(__file__))


def capture(fn, *args, **kwargs):
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        result = fn(*args, **kwargs)
    return _ANSI_RE.sub("", stream.getvalue()), result


def player_at(room="medicine_shop", tick=7):
    player = Player("形貌验收侠客")
    player.location = room
    player.set_var("quest_clock", tick)
    return player


def render_self(player, alias="自己"):
    return capture(look, player, [alias])[0]


def test_player_profile_defaults_and_overrides():
    player = Player("默认形貌")
    profile = player.get_player_profile()
    assert profile == {"gender": "male", "age_desc": "二十来岁", "face_attire": ""}

    assert player.set_player_profile(gender="female", age_desc="四十上下", face_attire="她穿着一件洗得发白的素色长衫。")
    profile = player.get_player_profile()
    assert profile["gender"] == "female"
    assert profile["age_desc"] == "四十上下"
    assert profile["face_attire"] == "她穿着一件洗得发白的素色长衫。"

    value = render_self(player)
    assert "你穿着一件洗得发白的素色长衫。" in value
    assert "你约莫四十上下。" in value


def test_look_self_has_five_parts_and_equipment():
    value = render_self(player_at())
    assert "你穿着一身洗得发白的青布劲装" in value
    assert "你约莫二十来岁。" in value
    assert "你看起来武功初入门径" in value
    assert "你气色尚可，看不出有什么伤病。" in value
    assert "你装备着：" in value
    assert "木剑(mu jian)" in value
    assert "布衣(bu yi)" not in value
    for label in ("关系：", "势力：", "攻击：", "防御：", "【环境】", "【可前往地点】"):
        assert label not in value


@pytest.mark.parametrize("alias", ["自己", "我", "自身", "self"])
def test_self_look_aliases(alias):
    value = render_self(player_at(), alias=alias)
    assert "你装备着：" in value
    assert "你约莫二十来岁。" in value
    assert actor_display.is_self_target(alias)


@pytest.mark.parametrize(
    "level,expected",
    [
        (1, "初入门径"),
        (5, "已有小成"),
        (9, "武功不弱"),
        (15, "武功高强"),
    ],
)
def test_player_power_line_tracks_level(level, expected):
    player = player_at()
    player.level = level
    value = render_self(player)
    assert expected in value


@pytest.mark.parametrize(
    "hp,expected",
    [
        (100, "气色尚可"),
        (90, "带着些轻伤"),
        (50, "伤势不轻"),
        (20, "伤得很重"),
    ],
)
def test_player_health_line_tracks_hp(hp, expected):
    player = player_at()
    player.hp = hp
    player.max_hp = 100
    value = render_self(player)
    assert expected in value


def test_player_profile_persists_in_existing_world_state(tmp_path):
    player = Player("存档形貌")
    player.set_player_profile(gender="female", age_desc="三十上下", face_attire="她穿一身素白衣衫。")
    target = tmp_path / "alpha304_save.json"
    capture(player.save_to_file, str(target), verbose=False)
    assert target.exists()
    output, loaded = capture(Player.load_from_file, str(target))
    assert loaded is not None
    assert loaded.get_player_profile() == {
        "gender": "female",
        "age_desc": "三十上下",
        "face_attire": "她穿一身素白衣衫。",
    }
    assert "player_profile" in loaded.world_state["variables"]
    assert "读档成功" in output


def test_talk_has_no_npc_metadata_panel():
    player = player_at(tick=0)
    value, _ = capture(handle_talk_and_ask, player, ["药铺老板"])
    title = engine.NPCS["药铺老板"].get("title", "药铺老板")
    assert f"【{title}】" not in value
    assert "关系：" not in value
    assert "门派立场：" not in value
    assert "状态：" not in value
    assert f"{actor_display.npc_talk_verb('药铺老板')}：“" in value


def test_busy_talk_uses_natural_prose_without_status_label():
    player = player_at()
    player.set_npc_state("药铺老板", "busy", duration=5, reason="正在坐堂配药")
    before = player.get_relation("药铺老板")
    value, result = capture(handle_talk_and_ask, player, ["药铺老板"])
    assert result is False
    assert "状态：" not in value
    assert "药铺老板正在坐堂配药" in value
    assert "只匆匆应了一声" in value
    assert "说道" not in value
    assert "【可接取委托】" not in value
    assert player.get_relation("药铺老板") == before


def test_busy_topic_dialogue_stays_busy_free_but_offers_quests():
    player = player_at()
    player.set_npc_state("药铺老板", "busy", duration=5, reason="正在坐堂配药")
    value, _ = capture(handle_talk_and_ask, player, ["药铺老板", "委托"])
    assert "状态：" not in value
    assert "【可接取委托】" in value
    assert "无暇交谈" not in value


def test_relations_panel_includes_state_and_impression():
    player = player_at()
    player.set_npc_state("药铺老板", "busy", duration=5, reason="正在坐堂配药")
    value, _ = capture(handle_relations, player, ["药铺老板"])
    assert "【百草堂主(yao pu lao ban)】" in value
    assert "身份：百草堂主（商贾）" in value
    assert "势力：青石村" in value
    assert "关系：中立 (+0)" in value
    assert "状态：忙碌（正在坐堂配药）" in value
    assert "印象：暂无特别印象" in value


@pytest.mark.parametrize(
    "injury_level,expected",
    [
        ("light", "身上带着些轻伤，气息还算平稳。"),
        ("serious", "伤势不轻，脸色有些发白。"),
        ("critical", "伤得很重，气息已经有些虚弱。"),
    ],
)
def test_injury_level_controls_look_health_line(injury_level, expected):
    player = player_at()
    assert player.set_npc_state(
        "药铺老板", "injured", duration=5, reason="被山贼所伤", injury_level=injury_level
    )
    assert player.get_npc_state_record("药铺老板")["injury_level"] == injury_level
    value, _ = capture(look, player, ["药铺老板"])
    assert "他" + expected in value


def test_invalid_injury_level_is_ignored():
    player = player_at()
    assert player.set_npc_state("药铺老板", "injured", duration=5, reason="受伤", injury_level="deadly")
    record = player.get_npc_state_record("药铺老板")
    assert "injury_level" not in record
    value, _ = capture(look, player, ["药铺老板"])
    assert "他" + "身上带着些轻伤，气息还算平稳。" in value
