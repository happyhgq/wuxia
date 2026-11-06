"""P4.0：命令策略已独立于主循环，旧入口保持兼容。"""
import command_policy
import main


def test_main_reexports_command_policy_functions_for_compatibility():
    assert main.command_will_be_handled is command_policy.command_will_be_handled
    assert main.command_advances_world is command_policy.command_advances_world


def test_unknown_command_does_not_advance_world():
    assert command_policy.command_will_be_handled("not_a_real_command", {}) is False


def test_read_only_and_mutating_command_contracts_are_preserved():
    assert command_policy.command_advances_world("背包") is False
    assert command_policy.command_advances_world("sell") is True
    assert command_policy.command_advances_world("events", []) is False
    assert command_policy.command_advances_world("events", ["处理"]) is True


def test_registered_command_aliases_are_not_rejected_before_dispatch():
    room = {"exits": {}}
    for command in ("world_activity", "sect_join", "security_governance"):
        assert command_policy.command_will_be_handled(command, room) is True


def test_security_status_is_read_only_but_assistance_advances_world():
    assert command_policy.command_advances_world("security_governance", []) is False
    assert command_policy.command_advances_world("security_governance", ["悬赏"]) is False
    assert command_policy.command_advances_world("security_governance", ["协助"]) is True


def test_every_registered_command_alias_passes_pre_dispatch_admission():
    # 方向键是否可用取决于当前房间出口，这里给出含全部方向出口的房间。
    room = {"exits": {d: f"room_{d}" for d in
                      ("北", "南", "东", "西", "上", "下", "内", "外", "后", "前")}}
    for alias, target in main.CMD_MAP.items():
        assert command_policy.command_will_be_handled(target, room), (alias, target)


def test_task_acceptance_spellings_are_blocked_as_direct_commands():
    for raw in (
        "接取 新手采药·认识资源",
        "任务 接取 新手采药·认识资源",
        "任务 接取任务 新手采药·认识资源",
        "任务 接受任务 新手采药·认识资源",
    ):
        assert main._is_direct_quest_accept_command(*main.parse_command(raw)), raw
