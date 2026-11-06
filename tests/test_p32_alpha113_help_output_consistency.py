"""Alpha113：帮助菜单与具体指令说明保持单一、清晰的呈现。"""
import contextlib
import io
from pathlib import Path

import help_system
import main


def render_help(topic=None):
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        main.show_help(topic)
    return help_system._ANSI_RE.sub("", output.getvalue())


def test_direct_command_lookup_does_not_repeat_same_command_card():
    output = render_help("查看")
    assert output.count("【看】") == 1
    assert "用途：" in output
    assert "用法：" in output


def test_top_menu_has_one_numbered_source_for_all_thirteen_categories():
    output = render_help()
    for number, category in enumerate(help_system.CATEGORIES, 1):
        label = f"【{help_system.CN_NUMBERS_REVERSE[number]}】{category['name']}"
        assert output.count(label) == 1, label
    assert output.count("【一】查看与移动") == 1


def test_help_source_does_not_keep_a_second_dead_menu_definition():
    for module in (main, help_system):
        source = Path(module.__file__).read_text(encoding="utf-8")
        assert "menu_groups = [" not in source
    main_source = Path(main.__file__).read_text(encoding="utf-8")
    start = main_source.index("def show_help(")
    end = main_source.index("def show_encyclopedia(", start)
    assert main_source[start:end].count("help_system.show") == 1


def test_help_command_aliases_share_the_same_readable_card_format():
    for topic in ("采集", "穿戴", "交谈", "采矿"):
        output = render_help(topic)
        assert "用途：" in output, topic
        assert "用法：" in output, topic
        assert "Traceback" not in output, topic
