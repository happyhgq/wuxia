"""Alpha267：NPC 忙碌状态、场景在场名单与人物行为显示保持一致。"""
import contextlib
import io

from actions import handle_talk_and_ask, look
from player import Player


def capture(fn, *args, **kwargs):
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        result = fn(*args, **kwargs)
    return stream.getvalue(), result


def test_busy_talk_enters_dialogue_without_moving_npc_out_of_scene():
    player = Player("忙碌场景同步", "散人")
    player.location = "village_head_house"
    player.set_npc_state("村长", "busy", duration=4, reason="处理村务", source="faction_conflict:青石村:黑市")
    start_clock = player.get_quest_clock()

    for _ in range(4):
        output, result = capture(handle_talk_and_ask, player, ["村长"])
        # 忙碌且未提出具体话题时只展示状态，不推进世界时钟。
        assert result is False
        assert "村长" in output
        assert "状态：" not in output
        assert "无暇交谈" not in output
        assert player.get_npc_location("村长", refresh=False) == "village_head_house"
        assert "村长" in player.get_npcs_in_room("village_head_house")

    assert player.get_quest_clock() == start_clock
    assert player.get_npc_state("村长") == "busy"


def test_busy_duration_expires_after_other_world_activity_not_repeated_ask():
    player = Player("忙碌到期", "散人")
    # tick 0 = 06:00，药铺老板正在铺面；tick 1 = 07:00 仍处于同一段非忙碌日程。
    player.set_var("quest_clock", 0)
    player.location = "medicine_shop"
    player.set_npc_state("药铺老板", "busy", duration=1, reason="正在坐堂配药")
    for _ in range(3):
        output, result = capture(handle_talk_and_ask, player, ["药铺老板"])
        assert result is False
        assert "正在坐堂配药" in output
    assert player.get_npc_state("药铺老板") == "busy"
    player.tick_quest_clock(1)
    assert player.get_npc_state("药铺老板") != "busy"


def test_repeated_busy_talk_stays_available_and_keeps_status_description():
    player = Player("忙碌提示稳定", "散人")
    player.location = "village_head_house"
    player.set_npc_state("村长", "busy", duration=3, reason="处理村务")
    first, _ = capture(handle_talk_and_ask, player, ["村长"])
    second, _ = capture(handle_talk_and_ask, player, ["村长"])
    assert "正忙着处理村务" in first
    assert "正忙着处理村务" in second
    assert "无暇交谈" not in first and "无暇交谈" not in second
    assert player.get_npc_state("村长") == "busy"


def test_faction_conflict_reason_is_not_rendered_as_npc_activity():
    player = Player("人物状态局势分离", "散人")
    player.location = "village_head_house"
    player.set_npc_state("村长", "busy", duration=4,
                         reason="青石村与黑市局势升级至对峙",
                         source="faction_conflict:青石村:黑市")
    output, _ = capture(look, player)
    people_section = output.split("【人物】", 1)[1].split("【", 1)[0]
    assert "村长" in people_section
    assert "对峙" not in people_section
    # 冲突忙碌时不能沿用日程描述，否则与“脱不开身”的交谈应答互相矛盾。
    assert "急事缠住" in people_section
    assert "【区域局势】" in output


def test_busy_npc_remains_a_valid_present_interaction_target():
    player = Player("忙碌目标定位", "散人")
    player.location = "village_head_house"
    player.set_npc_state("村长", "busy", duration=5, reason="处理村务")
    output, result = capture(handle_talk_and_ask, player, ["村长"])
    assert result is False
    assert "当前地点没有" not in output
    assert "状态：" not in output and "处理村务" in output
    assert "只匆匆应了一声" in output
    assert "说道" not in output
    assert "【可接取委托】" in output
