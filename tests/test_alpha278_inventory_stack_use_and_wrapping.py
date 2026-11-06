"""Alpha278：背包叠放物品使用、输入归一化、简洁反馈与折行排版。"""
import io
import re
import unicodedata
from contextlib import redirect_stdout

import actions
import engine
from main import show_inventory
from player import Player
from ui_output import _ANSI_RE, wrap_player_text


def plain(value):
    return _ANSI_RE.sub("", value)


def display_width(value):
    return sum(2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1 for ch in plain(value))


def capture(callback, *args):
    stream = io.StringIO()
    with redirect_stdout(stream):
        callback(*args)
    return plain(stream.getvalue())


def _no_official_save(monkeypatch):
    calls = []

    def fake_save(self, filename=None, verbose=True):
        calls.append(verbose)
        return True

    monkeypatch.setattr(Player, "save_to_file", fake_save)
    return calls


def test_stacked_item_is_used_as_one_stack_and_leaves_remaining(monkeypatch):
    saves = _no_official_save(monkeypatch)
    player = Player("叠放测试", "散人")
    player.inventory = ["金创药", "金创药"]
    player.hp = 10

    output = capture(actions.handle_equipment_and_items, player, "use", ["金创药"])

    assert player.inventory == ["金创药"]
    assert player.hp == 100
    assert "你服下了【金创药】，恢复 90 点气血" in output
    assert "剩余：金创药 ×1" in output
    assert "匹配到" not in output
    assert saves == [False]


def test_bracketed_item_input_is_normalized_without_nested_brackets(monkeypatch):
    _no_official_save(monkeypatch)
    player = Player("括号测试", "散人")
    player.inventory = ["金创药"]
    player.hp = 1

    output = capture(actions.handle_equipment_and_items, player, "use", ["【金创药】"])

    assert player.inventory == []
    assert "你服下了【金创药】" in output
    assert "【【" not in output
    assert "行囊里没有" not in output


def test_ambiguous_use_lists_numbered_choices_and_supports_number_selection(monkeypatch):
    saves = _no_official_save(monkeypatch)
    player = Player("歧义测试", "散人")
    player.inventory = ["疗伤药", "金创药"]
    player.hp = 10

    prompt = capture(actions.handle_equipment_and_items, player, "use", ["药"])

    assert "1. 疗伤药 ×1" in prompt
    assert "2. 金创药 ×1" in prompt
    assert "使用 1" in prompt
    assert player.inventory == ["疗伤药", "金创药"]
    assert saves == []

    result = capture(actions.handle_equipment_and_items, player, "use", ["2"])

    assert player.inventory == ["疗伤药"]
    assert player.hp == 100
    assert "你服下了【金创药】" in result
    assert saves == [False]


def test_stale_numbered_choice_does_not_consume_after_inventory_changes(monkeypatch):
    _no_official_save(monkeypatch)
    player = Player("过期选项测试", "散人")
    player.inventory = ["疗伤药", "金创药"]

    capture(actions.handle_equipment_and_items, player, "use", ["药"])
    player.inventory = ["金创药"]

    output = capture(actions.handle_equipment_and_items, player, "use", ["1"])

    assert player.inventory == ["金创药"]
    assert "没有可选择的物品序号" in output


def test_use_feedback_is_concise_without_save_or_system_noise(monkeypatch):
    _no_official_save(monkeypatch)
    player = Player("反馈测试", "散人")
    player.inventory = ["疗伤药"]
    player.hp = 10

    output = capture(actions.handle_equipment_and_items, player, "use", ["疗伤药"])
    feedback_lines = [line.strip() for line in output.splitlines() if line.strip()]

    assert feedback_lines == ["你服下了【疗伤药】，恢复 50 点气血。已消耗 1 件，剩余：疗伤药 ×0。"]
    assert "物品使用结果" not in output
    assert "[存档成功]" not in output
    assert "背包变化已记录" not in output


def test_inventory_description_wraps_on_punctuation_without_orphan_marks(monkeypatch):
    long_desc = (
        "从野猪身上取得的新鲜兽肉，可卖给商贩换取银两，"
        "也可用于食物制作，是山野间常见的食材。"
    )
    monkeypatch.setattr(
        engine, "ITEMS",
        {"野猪肉": {"type": "material", "desc": long_desc, "price": 6}},
    )
    player = Player("排版测试", "散人")
    player.inventory = ["野猪肉"]

    output = capture(show_inventory, player)
    lines = output.splitlines()

    assert long_desc in output.replace("\n", "")
    assert any(line.startswith("  野猪肉 ×1") for line in lines)
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        assert display_width(line) <= 80
        assert not re.fullmatch(r"[，。、；：！？]+", stripped)
        assert not stripped.startswith(("，", "。", "、", "；", "：", "！", "？"))
    assert not any(
        lines[index].rstrip().endswith("食物制") and lines[index + 1].lstrip().startswith("作")
        for index in range(len(lines) - 1)
    )


def test_wrap_prefers_punctuation_and_keeps_visible_text(monkeypatch):
    text = "从野猪身上取得的新鲜兽肉，可卖给商贩换取银两，也可用于食物制作，是山野间常见的食材。"
    wrapped = wrap_player_text(text, width=24)

    assert wrapped.splitlines()
    assert text.replace("\n", "") == _ANSI_RE.sub("", wrapped).replace("\n", "")
    for line in wrapped.splitlines():
        assert display_width(line) <= 24
        assert line.strip() not in ("，", "。", "、", "；", "：", "！", "？")
        assert not line.strip().startswith(("，", "。", "、", "；", "：", "！", "？"))


def test_item_lookup_normalizes_brackets_for_equipment_commands(monkeypatch):
    _no_official_save(monkeypatch)
    player = Player("装备匹配测试", "散人")
    player.inventory = ["精铁剑"]

    assert actions._find_inventory_item(player, "【精铁剑】") == "精铁剑"
    actions.handle_equipment_and_items(player, "equip", ["【精铁剑】"])

    assert player.equipment["weapon"] == "精铁剑"
    assert "精铁剑" not in player.inventory


def test_distinct_quality_variants_are_numbered_and_use_the_selected_one(monkeypatch):
    _no_official_save(monkeypatch)
    monkeypatch.setitem(
        engine.ITEMS, "金创药·精制",
        {"type": "consumable", "desc": "精选药材制成的金创药。", "effect": {"hp": 60}, "price": 90,
         "base_item": "金创药", "quality": "精制"},
    )
    player = Player("品质选择测试", "散人")
    player.inventory = ["金创药", "金创药·精制"]
    player.hp = 10

    prompt = capture(actions.handle_equipment_and_items, player, "use", ["金创"])

    assert "1. 金创药 ×1" in prompt
    assert re.search(r"2\. 金创药·精制.*×1", prompt)
    assert player.inventory == ["金创药", "金创药·精制"]

    result = capture(actions.handle_equipment_and_items, player, "use", ["2"])

    assert player.inventory == ["金创药"]
    assert player.hp == 70
    assert "你服下了【金创药·精制】" in result
