"""Alpha161：少林高阶区域的实际交互内容。"""
import contextlib
import io

import engine
from actions import handle_talk_and_ask
from player import Player


def capture(fn, *args):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        fn(*args)
    return out.getvalue()


def test_shaolin_corridor_has_patrol_monk_and_useful_interaction():
    assert "少林巡院僧" in engine.ROOMS["shaolin_abbot_corridor"]["npcs"]
    assert "shaolin_abbot_corridor" in engine.NPCS["少林巡院僧"].get("autonomy_profile", {}).get("route", []) or "少林巡院僧" in engine.NPCS
    p = Player("外廊交互测试", "少林")
    p.location = "shaolin_abbot_corridor"
    before = p.get_relation("少林巡院僧")
    output = capture(handle_talk_and_ask, p, ["少林巡院僧", "清修"])
    assert "收敛脚步" in output
    assert p.get_relation("少林巡院僧") >= before


def test_shaolin_dharma_hall_topics_are_available_once():
    p = Player("讲经堂交互测试", "少林")
    p.location = "shaolin_dharma_hall"
    output = capture(handle_talk_and_ask, p, ["少林戒律僧", "晨课"])
    assert "晨课重在持心与守戒" in output
    assert p.is_dialogue_choice_used("少林戒律僧", "shaolin_dharma_daily_lesson")
    again = capture(handle_talk_and_ask, p, ["少林戒律僧", "晨课"])
    assert "已经与对方谈过了" in again


def test_shaolin_scripture_courtyard_has_catalogue_and_borrowing_guidance():
    p = Player("藏经阁交互测试", "少林")
    p.location = "shaolin_scripture_court"
    output = capture(handle_talk_and_ask, p, ["少林守阁僧", "藏经目录"])
    assert "经、律、论各有分门" in output
    assert "藏经目录" in engine.NPCS["少林守阁僧"]["info"]


def test_shaolin_room_hints_match_existing_npcs_and_topics():
    rooms = engine.ROOMS
    assert "晨课" in rooms["shaolin_dharma_hall"]["desc"]
    assert "少林巡院僧" in rooms["shaolin_abbot_corridor"]["npcs"]
    assert "借阅规矩" in rooms["shaolin_scripture_court"]["desc"]
