import contextlib
import io

import actions
from actions import handle_region_ecology, look
from player import Player


def _capture(callback, *args):
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        callback(*args)
    return stream.getvalue()


def test_look_labels_faction_mood_apart_from_environment_danger():
    player = Player("区域标签回归", "散人")
    player.location = "duanhun_camp"
    output = _capture(look, player)
    assert "势力动向：平静" in output
    assert "危险度：极危" in output
    assert "【区域局势】 平静 | 危险度" not in output


def test_region_command_uses_same_faction_label():
    player = Player("区域指令回归", "散人")
    player.location = "duanhun_camp"
    output = _capture(handle_region_ecology, player, ["断魂岭"])
    assert "势力动向：平静" in output
    assert "危险度：极危" in output


def test_safe_zone_keeps_single_safe_label():
    player = Player("安全区回归", "散人")
    player.location = "inn_upper_hall"
    output = _capture(look, player)
    assert "【区域局势】 安全" in output
