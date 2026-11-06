"""Alpha100：商旅公告、场景显示与有效驻留状态保持一致。"""
from io import StringIO
import re
from unittest.mock import patch

import actions

ANSI = re.compile(r"\x1b\[[0-9;]*m")


class FakePlayer:
    location = "village_square"
    economy_state = {
        "tick": 10,
        "events": {
            "active_caravans": {
                "北路商队:village_square": {"name": "北路商队", "room": "village_square", "until_tick": 13},
                "南路商队:village_square": {"name": "南路商队", "room": "village_square", "until_tick": 12},
                "村镇行商:village_square": {"name": "村镇行商", "room": "village_square", "until_tick": 11},
                "过期商队:village_square": {"name": "过期商队", "room": "village_square", "until_tick": 10},
                "异地商队:other": {"name": "异地商队", "room": "guiyun_central_square", "until_tick": 13},
            }
        },
    }

    def propagate_npc_information(self, _):
        pass

    def get_region_ecology(self, _):
        return {"level": "tension", "danger": "normal", "security": 69, "commerce": 66, "travel": 76}

    def get_npcs_in_room(self, _):
        return ["木匠老许"]

    def get_npc_daily_activity(self, _):
        return {"reason": "在住处休息"}

    def get_npc_encounters(self, _):
        return []


def test_look_displays_active_caravans_as_visible_scene_entities():
    output = StringIO()
    with patch("sys.stdout", output):
        actions.look(FakePlayer())
    visible = ANSI.sub("", output.getvalue())
    assert "商旅：北路商队、南路商队、村镇行商" in visible
    assert "商店 北路商队" in visible
    assert "出售 物品 数量 给 村镇行商" in visible
    assert "过期商队" not in visible
    assert "异地商队" not in visible
