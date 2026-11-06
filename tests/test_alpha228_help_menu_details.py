"""Alpha228：编号帮助菜单中的每个条目都必须提供完整详情。"""
import contextlib
import io

import help_system
import main


def render_help(topic=None):
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        main.show_help(topic)
    return help_system._ANSI_RE.sub("", output.getvalue())


def test_main_menu_lists_all_thirteen_categories():
    menu = render_help()
    for number, category in enumerate(help_system.CATEGORIES, 1):
        assert f"【{help_system.CN_NUMBERS_REVERSE[number]}】{category['name']}" in menu


def test_every_numbered_category_entry_has_detail_fields():
    for category_no, category in enumerate(help_system.CATEGORIES, 1):
        for entry_no in range(1, len(category["entries"]) + 1):
            page = render_help(f"{category_no} {entry_no}")
            assert "详细说明正在整理中" not in page, (category["id"], entry_no)
            assert "用途：" in page, (category["id"], entry_no)
            assert "用法：" in page, (category["id"], entry_no)
            assert "别名：" in page, (category["id"], entry_no)
            assert "示例：" in page, (category["id"], entry_no)
            assert "注意：" not in page, (category["id"], entry_no)


def test_region_help_has_consistent_explanation_and_usage_card():
    output = render_help("区域")
    assert "用途：查看当前区域局势与危险程度（含安全程度）。" in output
    assert "用法：区域" in output
