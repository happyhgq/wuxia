# -*- coding: utf-8 -*-
"""玩家界面输出防泄漏层：避免内部标识、路径和调试对象进入游戏文本。"""
import os
import re
import sys

# 统一正文折行宽度：终端 80 列下保留少量边距，避免贴边自动折行。
BODY_WIDTH = 78

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")

# 颜色模式：auto 按终端与 NO_COLOR 判断，on/off 由玩家显式指定。
_color_mode = "auto"


def set_color_mode(mode):
    """切换颜色模式，返回实际生效的模式名。"""
    global _color_mode
    value = str(mode or "").strip().lower()
    if value not in ("auto", "on", "off"):
        raise ValueError("颜色模式只能是 auto、on 或 off。")
    _color_mode = value
    return _color_mode


def get_color_mode():
    return _color_mode


def colors_enabled():
    """当前是否应输出 ANSI 颜色；重定向日志与 NO_COLOR 环境下自动关闭。"""
    if _color_mode == "off":
        return False
    if _color_mode == "on":
        return True
    if "NO_COLOR" in os.environ:
        return False
    if str(os.environ.get("TERM", "")).strip().lower() == "dumb":
        return False
    return bool(getattr(sys.stdout, "isatty", lambda: False)())
_PATH_RE = re.compile(r"(?:(?:[A-Za-z]:\\|(?<![A-Za-z0-9])/)[^\s<>\"']+|[\w./\\-]+\.(?:py|json|jsonl|zip|bak|tmp))", re.IGNORECASE)
_TRACE_RE = re.compile(r"(?i)(?:traceback \(most recent call last\)|\b(?:traceback|stack trace|exception|debug dump|valueerror|typeerror|keyerror|indexerror|attributeerror|importerror|oserror|jsondecodeerror|filenotfounderror|runtimeerror|nameerror|syntaxerror)\b)")
_NAMESPACED_ID_RE = re.compile(r"(?<![\w])(?:quest|world|npc|region|explore|visited_zone|faction_action|npc_event|event|flag|variable|zone|room|skill|item|enemy|save|schema|data):[A-Za-z0-9_:\-]+", re.IGNORECASE)
_SNAKE_ID_RE = re.compile(r"(?<![\w])(?=[A-Za-z0-9_]*_[A-Za-z0-9_]*)([A-Za-z][A-Za-z0-9]*(?:_[A-Za-z0-9]+){1,})(?![\w])")
# 玩家可见文本中常见的内部状态值与事件原因，统一转换为武侠语境中文。
_INTERNAL_LABELS = {
    "confrontation": "对峙", "conflict": "冲突", "escalation": "升级",
    "war": "战乱", "tension": "紧张", "calm": "平静",
    "normal": "正常", "busy": "忙碌", "injured": "受伤",
    "fear": "恐惧", "angry": "愤怒", "away": "暂离",
    "event_affected": "受事件影响", "relieved": "释然",
    "conflict_fatigue": "冲突暂歇", "faction_conflict": "势力对峙",
    "npc_intervention": "人物介入", "npc_proactive_timeout": "久未处理，事态恶化",
    "npc_intervention_stagnation": "局势恶化", "time_limit": "超时未完成",
    "condition": "条件未满足", "active": "进行中", "completed": "已完成",
    "failed": "已失败", "resolved": "已解决", "pending": "待处理",
}
_INTERNAL_LABEL_RE = re.compile(r"(?<![A-Za-z0-9_])(" + "|".join(re.escape(k) for k in sorted(_INTERNAL_LABELS, key=len, reverse=True)) + r")(?![A-Za-z0-9_])", re.IGNORECASE)

def _localize_internal_labels(text):
    return _INTERNAL_LABEL_RE.sub(lambda match: _INTERNAL_LABELS.get(match.group(0).lower(), match.group(0)), text)


def sanitize_player_text(value):
    """把动态输出转换为玩家可读文本；结构化对象不允许直接打印。"""
    if isinstance(value, (dict, list, tuple, set)):
        return "相关信息暂不可查看。"
    text = _localize_internal_labels(str(value))
    if _TRACE_RE.search(_ANSI_RE.sub("", text)):
        return "相关操作未能完成，请稍后重试。"
    text = _PATH_RE.sub("相关内容", text)
    text = _NAMESPACED_ID_RE.sub("相关线索", text)
    text = _SNAKE_ID_RE.sub("相关内容", text)
    text = re.sub(r"(?i)\bNPC\b", "人物", text)
    text = re.sub(r"(?i)\bV\d+\b", "当前版本", text)
    return text



def _sgr_style_groups(params):
    """把 SGR 参数拆成可独立启停的样式组（含 256 色与 RGB 色）。"""
    raw = params.split(";") if params else ["0"]
    values = [part or "0" for part in raw]
    groups = []
    i = 0
    while i < len(values):
        code = values[i]
        if code in ("38", "48", "58") and i + 1 < len(values):
            mode = values[i + 1]
            count = 3 if mode == "5" else (5 if mode == "2" else 1)
            group = values[i:i + min(count, len(values) - i)]
            groups.append((code, ";".join(group)))
            i += len(group)
        else:
            groups.append((code, code))
            i += 1
    return groups


_CLOSING_PUNCTUATION = set("，。、；：？！）】》」』〕〉”’…,.;:!?%)]}")
_OPENING_PUNCTUATION = set("（【《「『〔〈“‘([{")
_BREAK_AFTER_PUNCTUATION = set("，。、；：？！）】》」』〕〉”’…,.;:!?")


def _apply_sgr_state(active_styles, sequence):
    """把一段 SGR 序列并入当前样式状态，供折行后重建续行前缀。"""
    reset_codes = {"22": ("bold", "dim"), "23": ("italic",), "24": ("underline",),
                   "25": ("blink",), "27": ("inverse",), "28": ("conceal",),
                   "29": ("strike",), "39": ("fg",), "49": ("bg",), "54": ("frame",),
                   "55": ("overline",), "59": ("underline_color",)}
    style_codes = {"1": "bold", "2": "dim", "3": "italic", "4": "underline",
                   "21": "underline", "5": "blink", "6": "blink", "7": "inverse",
                   "8": "conceal", "9": "strike", "51": "frame", "52": "frame",
                   "53": "overline"}
    for code, group in _sgr_style_groups(sequence[2:-1]):
        if code == "0":
            active_styles.clear()
        elif code in reset_codes:
            for key in reset_codes[code]:
                active_styles.pop(key, None)
        elif code in ("38", "48", "58"):
            key = {"38": "fg", "48": "bg", "58": "underline_color"}[code]
            active_styles[key] = (code, group)
        elif code in style_codes:
            active_styles[style_codes[code]] = (code, group)
        elif code in ("30", "31", "32", "33", "34", "35", "36", "37", "90", "91", "92", "93", "94", "95", "96", "97"):
            active_styles["fg"] = (code, group)
        elif code in ("40", "41", "42", "43", "44", "45", "46", "47", "100", "101", "102", "103", "104", "105", "106", "107"):
            active_styles["bg"] = (code, group)
        elif code not in ("10",):
            active_styles[f"other_{code}"] = (code, group)


def _display_width(ch):
    import unicodedata
    if ch == "\n":
        return 0
    return 0 if unicodedata.combining(ch) else (2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1)


def _is_ascii_word_char(ch):
    return ch.isascii() and (ch.isalnum() or ch in "_")


def _can_break_between(left, right):
    if left in _OPENING_PUNCTUATION or right in _CLOSING_PUNCTUATION:
        return False
    if left.isspace() or right.isspace():
        return True
    if _is_ascii_word_char(left) and _is_ascii_word_char(right):
        return False
    return True


def _break_priority(left, right):
    if left.isspace():
        return 3
    if left in _BREAK_AFTER_PUNCTUATION:
        return 2
    if right in _OPENING_PUNCTUATION:
        return 1
    return 0


def _choose_break_index(chars, start, index, width):
    """在 [start, index) 内选择折行点：优先标点，其次词边界，且避免行首缩进被单独甩出。"""
    min_fill = max(1, width // 2)
    best_priority = -1
    best = None
    fallback = None
    for candidate in range(index, start, -1):
        left = chars[candidate - 1]
        right = chars[candidate] if candidate < index else chars[index]
        if not _can_break_between(left, right):
            continue
        if fallback is None:
            fallback = candidate
        prefix_width = sum(_display_width(item) for item in chars[start:candidate])
        if prefix_width < min_fill:
            continue
        priority = _break_priority(left, right)
        if priority > best_priority:
            best_priority = priority
            best = candidate
    return best if best is not None else fallback


def wrap_player_text(value, width=72):
    """按终端显示宽度折行：保留 ANSI 样式，并优先在标点或词边界处分行。"""
    text = sanitize_player_text(value)
    width = max(24, int(width or 72))

    chars = []
    ansi_before = []
    styles_before = []
    pending_ansi = []
    active_styles = {}
    i = 0
    while i < len(text):
        if text[i] == "\x1b":
            match = _ANSI_RE.match(text, i)
            if match:
                sequence = match.group(0)
                pending_ansi.append(sequence)
                _apply_sgr_state(active_styles, sequence)
                i = match.end()
                continue
        chars.append(text[i])
        ansi_before.append(pending_ansi)
        # 只保存样式参数，续行时重新开启，不重复原始复位指令。
        styles_before.append(tuple(active_styles[key][1] for key in sorted(active_styles)))
        pending_ansi = []
        i += 1
    trailing_ansi = pending_ansi

    if not chars:
        return ""

    total = len(chars)
    ranges = []
    line_start = 0
    col = 0
    i = 0
    while i < total:
        ch = chars[i]
        if ch == "\n":
            ranges.append((line_start, i, ansi_before[i]))
            line_start = i + 1
            col = 0
            i += 1
            continue
        char_width = _display_width(ch)
        if col + char_width > width and i > line_start:
            break_at = _choose_break_index(chars, line_start, i, width)
            if break_at is None:
                if ch in _CLOSING_PUNCTUATION:
                    # 宁可让收尾标点略微超出，也不把它单独甩到下一行。
                    col += char_width
                    i += 1
                    continue
                break_at = i
            if break_at <= line_start:
                break_at = i
            ranges.append((line_start, break_at, ()))
            line_start = break_at
            col = sum(_display_width(item) for item in chars[line_start:i])
            continue
        col += char_width
        i += 1
    if line_start < total:
        ranges.append((line_start, total, ()))
    elif not ranges:
        ranges.append((0, 0, ()))

    lines = []
    for start, end, tail_ansi in ranges:
        style_groups = styles_before[start] if start < total else ()
        pieces = []
        if style_groups:
            pieces.append(f"\x1b[{';'.join(style_groups)}m")
        if start < end:
            pieces.extend(ansi_before[start])
            pieces.append(chars[start])
            for index in range(start + 1, end):
                pieces.extend(ansi_before[index])
                pieces.append(chars[index])
        pieces.extend(tail_ansi)
        if end == total:
            pieces.extend(trailing_ansi)
        lines.append("".join(pieces).rstrip())
    return "\n".join(lines)


def safe_print(*values, **kwargs):
    """与 print 兼容的玩家界面输出入口，统一清理每个输出参数。"""
    import builtins
    cleaned = []
    colors_on = colors_enabled()
    for value in values:
        text = sanitize_player_text(value)
        if not colors_on:
            text = _ANSI_RE.sub("", text)
        cleaned.append(text)
    builtins.print(*cleaned, **kwargs)


def format_labeled_fields(fields, label_width=10):
    """将纵向字段标签按中文终端显示宽度对齐，值部分原样保留（可含 ANSI 颜色）。"""
    import unicodedata
    normalized = [(str(label), str(value)) for label, value in fields]
    measured = [sum(2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1 for ch in label) for label, _ in normalized]
    width = max([int(label_width or 0), *measured])
    return [f"{label}{' ' * (width - label_width_width + 1)}{value}" for (label, value), label_width_width in zip(normalized, measured)]


def format_action_feedback(action, success, summary, detail=None, next_step=None):
    """统一玩家操作反馈：先给结论，再给实际变化，最后给可执行的下一步。"""
    action = str(action or "操作").strip() or "操作"
    summary = str(summary or "操作未提供结果").strip()
    status = "完成" if success else "未完成"
    lines = [f"【{action}{status}】{summary}"]
    if detail:
        lines.append(f"结果：{str(detail).strip()}")
    if next_step:
        lines.append(f"接下来：{str(next_step).strip()}")
    return lines
