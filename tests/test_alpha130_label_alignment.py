"""Alpha130：统一状态、装备、物品详情中的纵向标签对齐。"""
import io
import re
from contextlib import redirect_stdout

import actions
from main import show_status
from player import Player
from ui_output import format_labeled_fields

ANSI = re.compile(r"\x1b\[[0-9;]*m")


def visible_width(text):
    import unicodedata
    text = ANSI.sub("", text)
    return sum(2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1 for ch in text)


def capture(fn, *args):
    stream = io.StringIO()
    with redirect_stdout(stream):
        fn(*args)
    return ANSI.sub("", stream.getvalue())


def test_formatter_aligns_chinese_labels_by_terminal_width():
    lines = format_labeled_fields([("姓名：", "阿青"), ("门派职位：", "武当弟子"), ("等级：", "12")], label_width=10)
    values_start = [visible_width(line) - visible_width(line.split("阿青")[-1]) if "阿青" in line else None for line in lines]
    # Every value begins at the same visible column despite different label lengths.
    starts = []
    for line, label in zip(lines, ("姓名：", "门派职位：", "等级：")):
        starts.append(visible_width(line[:line.index(label)]) + visible_width(label) + len(line[len(label):]) - len(line[len(label):].lstrip()))
    assert len(set(starts)) == 1
    assert len(values_start) == 3


def test_equipment_panel_has_aligned_vertical_labels():
    player = Player("排版测试", "散人")
    output = capture(actions.show_equipment, player)
    lines = [line for line in output.splitlines() if any(line.startswith(label) for label in ("兵刃：", "防具：", "总攻击：", "总防御：", "命中词条："))]
    starts = []
    for line in lines:
        label = next(label for label in ("兵刃：", "防具：", "总攻击：", "总防御：", "命中词条：") if line.startswith(label))
        starts.append(visible_width(line[:len(label)]) + len(line[len(label):]) - len(line[len(label):].lstrip()))
    assert len(lines) == 5
    assert len(set(starts)) == 1


def test_status_keeps_aligned_labels_and_compact_route_line():
    player = Player("排版测试", "散人")
    output = capture(show_status, player, "sect") + capture(show_status, player, "combat") + capture(show_status, player, "growth") + capture(show_status, player, "main")
    assert "姓名：" in output and "门派职位：" in output and "等级：" in output
    assert "路线倾向：" in output
    assert "姓       名：" not in output
