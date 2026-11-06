# -*- coding: utf-8 -*-
"""Alpha293：语义色表、颜色开关、提示符与统一正文宽度。"""
import contextlib
import io

import pytest

import combat
import engine
import main
import ui_output
from command_policy import command_advances_world, command_will_be_handled
from player import Player
from ui_output import BODY_WIDTH, _ANSI_RE


@pytest.fixture(autouse=True)
def _reset_color_mode():
    previous = ui_output.get_color_mode()
    ui_output.set_color_mode("auto")
    yield
    ui_output.set_color_mode(previous)


def capture(callback, *args, **kwargs):
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        callback(*args, **kwargs)
    return stream.getvalue()


def test_semantic_roles_keep_body_plain_and_color_only_meaningful_parts():
    assert engine.style("普通正文", "body") == "普通正文"
    assert engine.style("未知角色", "no_such_role") == "未知角色"
    for role in ("title", "heading", "hint", "success", "failure", "warning",
                 "gain", "loss", "npc", "enemy", "exit", "item", "quest",
                 "system", "damage", "heal", "crit", "phase", "skill"):
        assert role in engine.ROLE_COLORS
    assert engine.style("标题", "title") == f"{engine.Color.BRIGHT_CYAN}标题{engine.Color.RESET}"
    assert engine.style("会心一击！", "crit") == "\033[1;91m会心一击！\033[0m"


def test_auto_color_mode_respects_no_color_dumb_terminal_and_tty(monkeypatch):
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.delenv("TERM", raising=False)
    monkeypatch.setattr("sys.stdout.isatty", lambda: True, raising=False)
    assert ui_output.colors_enabled() is True

    monkeypatch.setattr("sys.stdout.isatty", lambda: False, raising=False)
    assert ui_output.colors_enabled() is False

    monkeypatch.setattr("sys.stdout.isatty", lambda: True, raising=False)
    monkeypatch.setenv("TERM", "dumb")
    assert ui_output.colors_enabled() is False

    monkeypatch.delenv("TERM", raising=False)
    monkeypatch.setenv("NO_COLOR", "1")
    assert ui_output.colors_enabled() is False


def test_explicit_switch_overrides_environment_and_strips_redirected_output(capsys, monkeypatch):
    monkeypatch.setenv("NO_COLOR", "1")
    ui_output.set_color_mode("off")
    ui_output.safe_print(engine.style("关闭颜色", "title"))
    assert _ANSI_RE.sub("", capsys.readouterr().out) == "关闭颜色\n"

    ui_output.set_color_mode("on")
    ui_output.safe_print(engine.style("强制上色", "title"))
    output = capsys.readouterr().out
    assert "\033[" in output and "强制上色" in output


def test_redirected_logs_are_ansi_free_in_auto_mode(monkeypatch):
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.delenv("TERM", raising=False)
    monkeypatch.setattr("sys.stdout.isatty", lambda: False, raising=False)
    ui_output.set_color_mode("auto")
    output = capture(lambda: ui_output.safe_print(engine.style("日志正文", "npc")))
    assert output == "日志正文\n"


def test_color_command_switches_modes_and_rejects_unknown_argument(capsys):
    main.handle_color_command([])
    assert "颜色模式：自动" in capsys.readouterr().out

    main.handle_color_command(["关"])
    assert "颜色已关闭" in capsys.readouterr().out
    assert ui_output.colors_enabled() is False

    main.handle_color_command(["开"])
    assert "颜色已开启" in capsys.readouterr().out
    assert ui_output.colors_enabled() is True

    main.handle_color_command(["自动"])
    assert "颜色已设为自动" in capsys.readouterr().out

    main.handle_color_command(["乱写"])
    assert "用法：颜色" in capsys.readouterr().out


def test_color_command_is_registered_and_does_not_advance_world():
    assert main.parse_command("颜色 关") == ("color", ["关"])
    assert command_will_be_handled("color", {}) is True
    assert command_advances_world("color") is False


def test_normal_prompt_and_combat_prompt_are_compact():
    player = Player("提示符测试", "散人")
    assert main.make_prompt(player) == "> "
    prompt = combat.make_combat_prompt(player, "山贼", 45, 90)
    assert prompt == f"〔气血 {player.hp}/{player.max_hp}｜山贼 50%〕> "
    assert "\033[" not in prompt


def test_body_width_is_used_for_display_wrapping():
    assert BODY_WIDTH == 78
    text = "江湖路远，侠客沿着长街缓缓前行，远处传来商队的驼铃与客栈的招呼声。" * 3
    wrapped = ui_output.wrap_player_text(text, width=BODY_WIDTH)
    assert len(wrapped.splitlines()) > 1
    for line in wrapped.splitlines():
        assert engine.get_display_width(line) <= BODY_WIDTH


def test_wide_character_input_line_clears_by_display_width():
    output = capture(main._render_input_line, "> ", list("江湖"), 0)
    assert " " * engine.get_display_width("> 江湖") in output
    assert output.endswith("> 江湖")

    output = capture(main._render_input_line, "> ", list("江"), engine.get_display_width("> 江湖"))
    assert " " * engine.get_display_width("> 江湖") in output
    assert output.endswith("> 江")
