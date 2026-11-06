"""Alpha115: 操作结果反馈应显示真实库存与资金变化。"""

from main import _resource_result_status


class _FakeManager:
    resources = {
        "forest": {"item": "木材", "capacity": 30},
        "mine": {"item": "铁矿石", "capacity": 24},
    }

    def __init__(self, remaining):
        self.remaining = remaining

    def export_state(self):
        return {"resources": {"forest": {"remaining": self.remaining}, "mine": {"remaining": self.remaining}}}


def test_resource_result_feedback_reports_actual_remaining_stock():
    assert _resource_result_status(_FakeManager(17), "forest") == "当前地点剩余木材储量：17/30。"
    assert _resource_result_status(_FakeManager(0), "mine") == "当前地点剩余铁矿石储量：0/24。"


def test_resource_result_feedback_omits_unconfigured_locations():
    assert _resource_result_status(_FakeManager(5), "ordinary_room") == ""


def test_resource_result_feedback_clamps_invalid_or_out_of_range_values():
    manager = _FakeManager(999)
    assert _resource_result_status(manager, "forest") == "当前地点剩余木材储量：30/30。"
    manager.remaining = "invalid"
    assert _resource_result_status(manager, "forest") == "当前地点剩余木材储量：30/30。"
