"""世界规则帮助：门派声望、选择与后果、终局目标三页概念说明。"""
import contextlib
import io

import help_system
import main
from ui_output import BODY_WIDTH

RULES = {
    "rule_sect": "门派声望",
    "rule_choice": "选择与后果",
    "rule_endgame": "终局目标",
}


def render(topic=None):
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        help_system.show(topic)
    return help_system._ANSI_RE.sub("", buffer.getvalue())


def test_world_rules_category_is_fourteenth_and_lists_three_pages():
    assert help_system.CATEGORIES[-1]["id"] == "world_rules"
    assert help_system.CATEGORIES[-1]["entries"] == list(RULES)
    assert help_system.category_number("world_rules") == 14
    assert help_system.CN_NUMBERS_REVERSE[14] == "十四"
    assert "【十四】世界规则" in render()
    page = render("14")
    assert "【十四 世界规则】" in page
    for index, name in enumerate(RULES.values(), 1):
        assert f"{index}【{name}】" in page, name


def test_rules_pages_are_looked_up_by_name_and_alias():
    for entry_id, name in RULES.items():
        assert help_system.classify(name)["entry_id"] == entry_id
    assert help_system.classify("规则")["category"]["id"] == "world_rules"
    assert help_system.classify("世界规则")["category"]["id"] == "world_rules"
    assert help_system.classify("门派声望与立场")["entry_id"] == "rule_sect"
    assert help_system.classify("后果")["entry_id"] == "rule_choice"
    assert help_system.classify("设计上限")["entry_id"] == "rule_endgame"
    assert help_system.classify("门派")["entry_id"] == "sect"
    assert help_system.classify("状态")["entry_id"] == "status"


def test_rules_pages_are_concepts_without_commands():
    for entry_id in RULES:
        entry = help_system.ENTRIES[entry_id]
        assert "command" not in entry, entry_id
        assert entry["extra"], entry_id
    assert not set(help_system.command_entry_ids()) & set(RULES)


def test_rules_pages_render_full_fields_within_width():
    for entry_id, name in RULES.items():
        text = render(name)
        assert f"【{name}】" in text, entry_id
        assert "用途：" in text, entry_id
        assert "用法：" in text, entry_id
        assert "别名：" in text and "别名：无" not in text, entry_id
        assert "示例：" in text, entry_id
        assert "0 返回分类　帮助 返回主目录" in text, entry_id
        for line in text.splitlines():
            assert "\t" not in line, (entry_id, line)
            assert help_system.visible_width(line) <= BODY_WIDTH, (entry_id, line)


def test_rules_state_the_shipped_numbers_and_commands():
    sect = " ".join(render("门派声望").split())
    assert "-1000 到 1000" in sect
    assert "本门 +8" in sect
    assert "其余三门各 -2" in sect
    assert "门派 声望" in sect

    choice = " ".join(render("选择与后果").split())
    assert "任务 选择 任务名称 分支名称" in choice
    assert "交付 任务名称|序号" in choice
    for label in ("安全度", "商路", "通行"):
        assert label in choice

    endgame = " ".join(render("终局目标").split())
    assert "3500" in endgame and "L16" in endgame
    assert "断魂精铁" in endgame
    assert "按 5" in endgame


def test_help_navigation_enters_and_leaves_rules_category():
    assert main.next_help_navigation_state("help", ["14"]) == "category:world_rules:1"
    assert main.next_help_navigation_state(
        "help", ["__help_detail_hint__", "world_rules", "rule_choice"]
    ) == "detail:world_rules:2"
    assert main.resolve_help_menu_input("1", "category:world_rules:1") == "帮助 14 1"
    assert main.resolve_help_menu_input("0", "detail:world_rules:2") == "帮助 14 页1"


def test_newbie_points_to_world_rules():
    assert "帮助 世界规则" in render("新手")
