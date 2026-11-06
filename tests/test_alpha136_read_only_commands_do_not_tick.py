"""Alpha136：只读界面不能推进任务时钟、NPC 日程或商队日程。"""
import main


def test_read_only_player_views_do_not_advance_world_clock():
    read_only = (
        "look", "map", "status", "inventory", "profession", "build", "caravan",
        "relations", "factions", "conflicts", "region", "notice_board",
        "npc_actions", "world_activity",
    )
    for cmd in read_only:
        assert not main.command_advances_world(cmd), cmd


def test_mixed_read_and_action_commands_keep_correct_clock_behavior():
    assert not main.command_advances_world("events", [])
    assert main.command_advances_world("events", ["触发"])
    assert not main.command_advances_world("skills", [])
    assert not main.command_advances_world("skills", ["查看", "太极拳"])
    assert main.command_advances_world("skills", ["学习", "太极拳"])
    assert main.command_advances_world("search")
    assert main.command_advances_world("mine")
    assert main.command_advances_world("sell")


def test_system_commands_and_talk_keep_existing_no_tick_rule():
    for cmd in ("save", "load", "help", "reload", "quit", "alias", "history", "talk", "knock"):
        assert not main.command_advances_world(cmd), cmd
