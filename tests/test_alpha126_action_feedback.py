"""Alpha126：核心操作反馈统一先报结论，再报告实际结果。"""
from ui_output import format_action_feedback


def test_success_feedback_has_consistent_action_heading_and_actual_detail():
    assert format_action_feedback(
        "交易", True, "买入【金创药】×2，共花费 12 两。", "行囊中现有【金创药】×2；剩余银两 38 两。"
    ) == [
        "【交易完成】买入【金创药】×2，共花费 12 两。",
        "结果：行囊中现有【金创药】×2；剩余银两 38 两。",
    ]


def test_failure_feedback_can_give_a_clear_next_step():
    assert format_action_feedback(
        "采矿", False, "行囊已满，无法继续开采。", next_step="先整理或出售物品，再回来采矿。"
    ) == [
        "【采矿未完成】行囊已满，无法继续开采。",
        "接下来：先整理或出售物品，再回来采矿。",
    ]


def test_feedback_omits_optional_lines_when_not_supplied():
    assert format_action_feedback("采集", True, "获得【草药】×1，已放入行囊。") == [
        "【采集完成】获得【草药】×1，已放入行囊。"
    ]
