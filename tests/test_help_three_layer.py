"""三层帮助系统：主目录、分类页、指令详情与帮助内序号导航。"""
import contextlib
import io
import re
from pathlib import Path

import combat
import help_system
import main
from ui_output import BODY_WIDTH

CATEGORY_NAMES = [
    "查看与移动", "交谈与人物", "任务与委托", "门派与师承", "武学与招式",
    "状态与成长", "背包与装备", "采集与生产", "战斗与恢复", "商店与交易",
    "客栈与休息", "江湖与消息", "系统与帮助", "世界规则",
]


def render(topic=None):
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        help_system.show(topic)
    return help_system._ANSI_RE.sub("", buffer.getvalue())


def assert_clean_output(text, label):
    for line in text.splitlines():
        assert "\t" not in line, (label, line)
        assert help_system.visible_width(line) <= BODY_WIDTH, (label, line, help_system.visible_width(line))


def test_main_page_has_fourteen_categories_in_two_columns():
    text = render()
    assert "【江湖帮助】" in text
    for number, name in enumerate(CATEGORY_NAMES, 1):
        assert f"【{help_system.CN_NUMBERS_REVERSE[number]}】{name}" in text
    first_row = next(line for line in text.splitlines() if "查看与移动" in line)
    assert "交谈与人物" in first_row
    assert "帮助 分类序号 / 帮助 分类名 / 帮助 指令名" in text
    assert "示例：帮助 1" in text
    assert "【看】" not in text
    assert "look" not in text
    assert_clean_output(text, "main")


def test_category_page_layout_and_pagination():
    first_page = render("13")
    assert "【十三 系统与帮助】 第 1/2 页" in first_page
    assert "12【下条】" in first_page
    assert "13【新手引导】" not in first_page
    assert "0 或“帮助”返回主目录" in first_page
    assert "输入“帮助 指令名”查看详情" in first_page
    assert_clean_output(first_page, "system page 1")

    second_page = render("13 页2")
    assert "【十三 系统与帮助】 第 2/2 页" in second_page
    assert "13【新手引导】" in second_page
    assert "输入“上页”翻页" in second_page
    assert_clean_output(second_page, "system page 2")

    single_page = render("1")
    assert "第 1/1 页" not in single_page
    assert "查看与移动" in single_page


def test_category_rows_use_fixed_width_columns():
    text = render("1")
    for number, entry_id in enumerate(help_system.CATEGORIES[0]["entries"], 1):
        entry = help_system.ENTRIES[entry_id]
        label = f"{number:>2}【{entry['name']}】"
        prefix = " " + help_system._pad(label, 17)
        row = next(line for line in text.splitlines() if line.startswith(prefix.rstrip()))
        assert row.startswith(prefix), (entry_id, row)
        assert entry["purpose"] in row
        assert_clean_output(row + "\n", entry_id)


def test_detail_page_fields_and_no_notes():
    text = render("看")
    assert "【看】" in text
    assert "用途：查看当前场景、人物、自己或物品的信息。" in text
    assert "用法：看 [对象名称]" in text
    assert "别名：查看、观察、l" in text
    assert "示例：看" in text
    assert "相关：" in text
    assert "0 返回分类　帮助 返回主目录" in text
    assert "注意：" not in text
    assert_clean_output(text, "look detail")


def test_every_detail_page_has_required_fields_and_no_notes():
    for category_no, category in enumerate(help_system.CATEGORIES, 1):
        for entry_no, entry_id in enumerate(category["entries"], 1):
            text = render(f"{category_no} {entry_no}")
            assert "用途：" in text, entry_id
            assert "用法：" in text, entry_id
            assert "别名：" in text, entry_id
            assert "示例：" in text, entry_id
            assert "注意：" not in text, entry_id
            assert_clean_output(text, entry_id)


def test_all_public_commands_are_registered_and_usage_is_real():
    public = {
        entry["command"] for entry in help_system.ENTRIES.values() if entry.get("command")
    }
    assert "reload" not in public
    covered = public | set().union(*help_system.MULTI_COMMAND_ENTRIES.values())
    assert set(main.CMD_MAP.values()) - covered == {"reload"}

    registered = set(main.CMD_MAP)
    for entry_id, entry in help_system.ENTRIES.items():
        usage = re.sub(r"\[[^\]]*\]", "", entry["usage"])
        for alternative in usage.split("/"):
            alternative = alternative.strip()
            if not alternative:
                continue
            assert alternative.split()[0] in registered, (entry_id, alternative)


def test_hidden_aliases_work_but_are_not_advertised():
    assert main.CMD_MAP["look"] == "look"
    assert help_system.classify("look")["entry_id"] == "look"
    assert help_system.classify("l")["entry_id"] == "look"
    for page in (render(), render("1"), render("看")):
        assert "look" not in page


def test_developer_commands_stay_out_of_help():
    assert "reload" not in {entry.get("command") for entry in help_system.ENTRIES.values()}
    assert help_system.classify("重载")["kind"] == "not_found"
    assert help_system.classify("热重载")["kind"] == "not_found"
    for page in (render(), render("13"), render("帮助")):
        assert "重载" not in page


def test_category_aliases_and_command_name_collisions():
    expectations = {
        "人物": "交谈与人物", "npc": "交谈与人物", "社交": "交谈与人物",
        "物品": "背包与装备", "交易": "商店与交易", "系统": "系统与帮助",
        "江湖": "江湖与消息", "成长": "状态与成长", "移动": "查看与移动",
    }
    for alias, name in expectations.items():
        assert name in render(alias), alias
    assert main.CMD_MAP["门派"] == "sect"
    assert main.CMD_MAP["武学"] == "skills"
    assert "【四 门派与师承】" in render("门派与师承")
    assert "【门派】" in render("门派")


def test_help_numeric_navigation_only_inside_help_context():
    assert main.resolve_help_menu_input("2", None) == "2"
    assert main.resolve_help_menu_input("2", "") == "2"
    assert main.resolve_help_menu_input("2", "top") == "帮助 2"
    assert main.resolve_help_menu_input("0", "top") == "帮助"
    assert main.resolve_help_menu_input("2", "category:system:1") == "帮助 13 2"
    assert main.resolve_help_menu_input("下页", "category:system:1") == "帮助 13 页2"
    assert main.resolve_help_menu_input("0", "detail:system:13") == "帮助 13 页2"
    assert main.resolve_help_menu_input("2", "detail:system:13").startswith(
        "帮助 __help_detail_hint__ system newbie"
    )
    assert main.next_help_navigation_state("look", []) is None


def test_navigation_states_follow_three_layers():
    assert main.next_help_navigation_state("help", []) == "top"
    assert main.next_help_navigation_state("help", ["0"]) == "top"
    assert main.next_help_navigation_state("help", ["13"]) == "category:system:1"
    assert main.next_help_navigation_state("help", ["13", "页2"]) == "category:system:2"
    assert main.next_help_navigation_state("help", ["13", "13"]) == "detail:system:13"
    assert main.next_help_navigation_state(
        "help", ["__help_detail_hint__", "system", "newbie"]
    ) == "detail:system:13"


def test_zero_and_error_pages_are_actionable():
    assert "【江湖帮助】" in render("0")
    assert "【一 查看与移动】" in render("1 0")
    assert "【新手引导】" in render("13 13")

    invalid_top = render("15")
    assert "没有第 15 个分类" in invalid_top
    assert "【江湖帮助】" in invalid_top

    invalid_index = render("1 99")
    assert "帮助菜单编号无效" in invalid_index
    assert "【一 查看与移动】" in invalid_index

    invalid_page = render("13 页9")
    assert "这一页不存在" in invalid_page
    assert "第 2/2 页" in invalid_page

    missing = " ".join(render("并不存在的主题").split())
    assert "没有找到" in missing and "帮助 指令名" in missing


def test_status_panel_and_battle_menu_take_priority_over_help_numbers():
    main_source = Path(main.__file__).read_text(encoding="utf-8")
    assert main_source.index("status_panel = handle_status_panel_input(raw_in") < main_source.index(
        "raw_in = resolve_help_menu_input(raw_in"
    )
    combat_source = Path(combat.__file__).read_text(encoding="utf-8")
    assert "resolve_help_menu_input" not in combat_source
    assert "act = input(make_combat_prompt" in combat_source
