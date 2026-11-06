"""Alpha114：场景说明使用清晰一致的分区标题。"""
from io import StringIO
from unittest.mock import patch
import re

import actions

ANSI = re.compile(r"\x1b\[[0-9;]*m")


class FakePlayer:
    location = "village_gate"
    economy_state = {}

    def propagate_npc_information(self, _):
        pass

    def get_region_ecology(self, _):
        return {"level": "calm", "danger": "safe", "security": 80, "commerce": 50, "travel": 80}

    def get_npcs_in_room(self, _):
        return []

    def get_npc_encounters(self, _):
        return []


def render_scene(guidance=True):
    output = StringIO()
    with patch("sys.stdout", output):
        actions.look(FakePlayer(), show_guidance=guidance)
    return ANSI.sub("", output.getvalue())


def test_scene_has_environment_and_situation_sections_before_next_step_guidance():
    output = render_scene()
    assert "【环境】" in output
    assert "【区域局势】" in output
    assert "【可前往地点】" in output
    assert "【下一步可以做什么】" in output
    assert output.index("【环境】") < output.index("【区域局势】")
    assert output.index("【区域局势】") < output.index("【可前往地点】")
    assert output.index("【可前往地点】") < output.index("【下一步可以做什么】")
    assert "可用操作：" in output and "建议" in output


def test_scene_does_not_show_next_step_section_when_guidance_is_disabled():
    output = render_scene(guidance=False)
    assert "【环境】" in output
    assert "【下一步可以做什么】" not in output
    assert "可用操作：" not in output
