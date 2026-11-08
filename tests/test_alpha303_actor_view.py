"""Alpha303：统一角色视图、五段式 NPC 观察与人物标签。"""
import contextlib
import io
import json
import os
from unittest.mock import patch

import actor_display
from actions import handle_relations, look
from player import Player

BASE = os.path.dirname(os.path.dirname(__file__))


def read(name):
    with open(os.path.join(BASE, "data", name), encoding="utf-8") as f:
        return json.load(f)


def render(player, *args):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        look(player, list(args) if args else None)
    return out.getvalue()


def test_every_npc_has_display_identity():
    npcs = read("npcs.json")
    for name, data in npcs.items():
        assert str(data.get("id", "")).strip(), name
        assert str(data.get("name", "")).strip(), name
        assert data.get("gender") in ("male", "female", "neutral"), name
        assert isinstance(data.get("power_tier"), int) and 0 <= data["power_tier"] <= 5, name
        assert str(data.get("face_attire", "")).strip(), name
        assert str(data.get("age_desc", "")).strip(), name
    ids = [data["id"] for data in npcs.values()]
    assert len(ids) == len(set(ids))


def test_every_item_has_display_id_and_buyi_is_clothing():
    items = read("items.json")
    ids = []
    for name, data in items.items():
        assert str(data.get("id", "")).strip(), name
        ids.append(data["id"])
    assert len(ids) == len(set(ids))
    assert items["布衣"].get("clothing") is True
    assert items["铁剑"].get("clothing") is None


def test_room_label_uses_rank_nickname_name_and_id():
    data = {"rank_title": "青石村", "nickname": "铁面", "name": "守卫", "id": "shou wei"}
    assert actor_display.format_room_label("守卫", data) == "青石村「铁面」守卫"
    assert actor_display.format_room_label("守卫", data, include_id=True) == "青石村「铁面」守卫(shou wei)"
    assert actor_display.format_room_label("守卫", read("npcs.json")["守卫"]) == "青石村守卫"
    assert actor_display.format_room_label("路人甲", {}) == "路人甲"


def test_find_npc_supports_key_name_id_and_rank():
    names = ["守卫"]
    assert actor_display.find_npc("守卫", names) == "守卫"
    assert actor_display.find_npc("shou wei", names) == "守卫"
    assert actor_display.find_npc("青石村守卫", names) == "守卫"
    assert actor_display.find_npc("青石村", names) == "守卫"
    assert actor_display.find_npc("沈青霜", names) is None
    assert actor_display.find_npc("铁匠", ["百炼铁铺铁匠", "铁匠"]) == "铁匠"


def test_look_npc_has_five_parts_and_no_meta_labels():
    player = Player("测试侠客")
    player.set_var("quest_clock", 0)
    player.location = "medicine_shop"
    output = render(player, "百草堂主")
    assert "他穿着一件墨绿长袍" in output
    assert "他约莫四十上下。" in output
    assert "他看起来不会武功。" in output
    assert "他气色尚可" in output
    assert "他装备着：" in output
    assert "  □ 捣药棒(dao yao bang)" in output
    assert "布衣" not in output
    for label in ("【", "关系：", "势力：", "相貌衣着", "言谈声音", "行事气度", "相处提示", "攻击", "防御"):
        assert label not in output


def test_look_npc_by_english_id_with_spaces():
    player = Player("测试侠客")
    player.set_var("quest_clock", 7)
    player.location = "village_gate"
    output = render(player, "shou", "wei")
    assert "他穿着一身粗布甲胄" in output
    assert "红缨枪(hong ying qiang)" in output


def test_female_npc_uses_female_pronoun_and_no_gear_section_when_empty():
    player = Player("测试侠客")
    view = actor_display.build_npc_view(player, "沈青霜")
    lines = actor_display.format_look(view)
    assert view["pronoun"] == "她"
    assert "她约莫二十来岁。" in lines
    assert "她看起来武功不弱，剑势清冷，出手极快。" in lines
    assert "  □ 长剑(chang jian)" in lines

    view = actor_display.build_npc_view(player, "苏挽晴")
    lines = actor_display.format_look(view)
    assert view["gear"] == []
    assert not any("装备着" in line for line in lines)


def test_busy_status_reuses_schedule_reason():
    player = Player("测试侠客")
    assert player.set_npc_state("守卫", "busy", duration=3, reason="正在巡逻村口")
    view = actor_display.build_npc_view(player, "守卫")
    assert view["health_line"] == "他正在巡逻村口。"

    assert player.set_npc_state("守卫", "busy", duration=3, reason="处理村务")
    view = actor_display.build_npc_view(player, "守卫")
    assert view["health_line"] == "他正忙着处理村务。"


def test_faction_conflict_reason_does_not_leak_into_look():
    player = Player("测试侠客")
    player.set_npc_state("守卫", "busy", duration=3,
                         reason="青石村与黑市局势升级至对峙",
                         source="faction_conflict:青石村:黑市")
    view = actor_display.build_npc_view(player, "守卫")
    assert "对峙" not in view["health_line"]


def test_injury_level_changes_health_prose():
    player = Player("测试侠客")
    assert player.set_npc_state("守卫", "injured", duration=3, reason="被山贼所伤")
    view = actor_display.build_npc_view(player, "守卫")
    assert "轻伤" in view["health_line"]

    for level, phrase in (("serious", "伤势不轻"), ("critical", "伤得很重")):
        with patch.object(player, "get_npc_state_record",
                          return_value={"state": "injured", "injury_level": level}):
            view = actor_display.build_npc_view(player, "守卫")
            assert phrase in view["health_line"]


def test_condition_trait_renders_for_uninjured_npc():
    player = Player("测试侠客")
    with patch.object(player, "get_npc_state_record", return_value={"state": "normal"}):
        view = actor_display.build_npc_view(player, "被绑村民")
    assert "身上留着绳索勒出的伤痕，气色尚可。" in view["health_line"]


def test_room_npc_list_uses_display_label_and_single_period():
    player = Player("测试侠客")
    player.set_var("quest_clock", 0)
    player.location = "medicine_shop"
    output = render(player)
    people = output.split("【人物】", 1)[1]
    assert "百草堂主：" in people
    assert "药铺老板" not in people
    assert "。。" not in people


def test_relations_command_carries_identity_faction_and_relation():
    player = Player("测试侠客")
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        handle_relations(player, ["青石村守卫"])
    value = out.getvalue()
    assert "【青石村守卫(shou wei)】" in value
    assert "身份：青石村守卫（百姓）" in value
    assert "势力：青石村" in value
    assert "关系：" in value
