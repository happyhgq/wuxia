"""P4.0 契约测试：固定命令解析与世界时钟边界，避免后续重构改变玩家体验。"""
import main


def test_command_chain_supports_ascii_and_fullwidth_semicolon_and_caps_at_eight():
    assert main.split_command_chain("看；状态;背包") == ["看", "状态", "背包"]
    raw = ";".join(f"命令{i}" for i in range(1, 12))
    assert len(main.split_command_chain(raw)) == 8


def test_read_only_commands_do_not_advance_world():
    for command in ("look", "看", "inventory", "背包", "status", "状态", "map", "caravan", "区域"):
        assert main.command_advances_world(command) is False, command


def test_mutating_commands_advance_world():
    for command in ("buy", "sell", "mine", "chop", "forge", "attack", "search"):
        assert main.command_advances_world(command) is True, command


def test_context_sensitive_commands_keep_read_only_exceptions():
    assert main.command_advances_world("events", []) is False
    assert main.command_advances_world("events", ["处理"]) is True
    assert main.command_advances_world("skills", ["查看"]) is False
    assert main.command_advances_world("skills", ["修习"]) is True


def test_unknown_commands_are_rejected_before_world_tick():
    assert main.command_will_be_handled("definitely_not_a_command", {}) is False


def test_travel_route_listing_is_read_only_but_actual_travel_advances_world():
    assert main.command_advances_world('travel', []) is False
    assert main.command_advances_world('travel', ['华山山门']) is True
