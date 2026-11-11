# -*- coding: utf-8 -*-
"""角色观察视图：把 NPC 数据整理成传统 MUD 的五段式描述（只读展示层）。"""

import re
import unicodedata

import engine

POWER_LINES = {
    0: "看起来不会武功",
    1: "看起来粗通拳脚",
    2: "看起来有些拳脚底子",
    3: "看起来武功不弱",
    4: "看起来武功高强",
    5: "看起来深不可测",
}

INJURY_LINES = {
    "light": "身上带着些轻伤，气息还算平稳。",
    "serious": "伤势不轻，脸色有些发白。",
    "critical": "伤得很重，气息已经有些虚弱。",
}

STATE_LINES = {
    "fear": "神色惊惶，似乎还没从惊吓中缓过来。",
    "angry": "面带怒色，气息有些急促。",
    "busy": "正忙着手里的事，一时顾不上旁人的打量。",
    "away": "像是还有别的事，随时准备离开。",
    "event_affected": "神色有些异样，似乎刚受了什么影响。",
}

NPC_STATE_LABELS = {
    "normal": "正常",
    "busy": "忙碌",
    "injured": "受伤",
    "fear": "恐惧",
    "angry": "愤怒",
    "away": "暂离",
    "event_affected": "受事件影响",
    "relieved": "释然",
}

SELF_ALIASES = {"自己", "我", "自身", "你自己", "本座", "self", "me", "myself"}

PLAYER_POWER_LINES = (
    (3, "你看起来武功初入门径，拳脚尚显生涩"),
    (6, "你看起来武功已有小成，出手渐稳"),
    (10, "你看起来武功不弱，举手投足已有章法"),
)
PLAYER_POWER_LINE_MAX = "你看起来武功高强，气息沉稳内敛"


def is_self_target(value):
    return _normalize(value) in {_normalize(alias) for alias in SELF_ALIASES}


def npc_talk_verb(npc_name):
    """固定 NPC 的对话动词；未配置时沿用“说道”。"""
    verb = _text(_npc_data(npc_name).get("talk_verb"))
    return verb or "说道"


def busy_clause(actor, reason):
    """把忙碌原因接在人物称呼后，保留“正在/在/正忙着”的自然语序。"""
    reason = _text(reason).rstrip("。.!！")
    if not reason:
        return ""
    if reason.startswith("正在"):
        return f"{actor}{reason}"
    if reason.startswith("在"):
        return f"{actor}正{reason}"
    for prefix in ("清晨", "清早", "早晨", "上午", "午后", "傍晚", "夜间", "夜里", "今日", "今天"):
        if reason.startswith(prefix):
            reason = reason[len(prefix):]
            break
    if not reason:
        return ""
    return f"{actor}正忙着{reason}"


def _text(value):
    return str(value or "").strip()


def _normalize(value):
    text = unicodedata.normalize("NFKC", _text(value))
    return re.sub(r"\s+", "", text).casefold()


def _npc_data(npc_name):
    data = engine.NPCS.get(npc_name, {})
    return data if isinstance(data, dict) else {}


def _pronoun(data):
    return "她" if _text(data.get("gender")) == "female" else "他"


def _label_parts(npc_name, data):
    name = _text(data.get("name")) or npc_name
    rank_title = _text(data.get("rank_title"))
    nickname = _text(data.get("nickname"))
    display_id = _text(data.get("id"))
    nickname_part = f"「{nickname}」" if nickname else ""
    # 部分 NPC 的 name 已含 rank_title，重复拼接会显示成“归云城归云城捕头”。
    prefix = "" if rank_title and name.startswith(rank_title) else rank_title
    label = f"{prefix}{nickname_part}{name}"
    return name, rank_title, nickname, display_id, label


def _search_candidates(npc_name, data):
    name, _rank, _nickname, display_id, label = _label_parts(npc_name, data)
    return [value for value in (
        npc_name,
        name,
        display_id,
        _text(data.get("title")),
        label,
        label.replace("「", "").replace("」", ""),
    ) if value]


def _exact_candidates(npc_name, data):
    _name, rank_title, nickname, _display_id, _label = _label_parts(npc_name, data)
    return _search_candidates(npc_name, data) + [v for v in (rank_title, nickname) if v]


def _exact_match(target, npc_name):
    target_key = _normalize(target)
    if not target_key:
        return False
    return any(_normalize(value) == target_key for value in _exact_candidates(npc_name, _npc_data(npc_name)))


def _loose_match(target, npc_name):
    target_key = _normalize(target)
    if not target_key:
        return False
    for value in _search_candidates(npc_name, _npc_data(npc_name)):
        candidate = _normalize(value)
        if candidate and (target_key in candidate or candidate in target_key):
            return True
    return False


def find_npc(target, npc_names):
    """按精确名称优先、模糊包含兜底，返回当前房间内的 NPC 键名。"""
    names = list(npc_names)
    for npc_name in names:
        if _exact_match(target, npc_name):
            return npc_name
    for npc_name in names:
        if _loose_match(target, npc_name):
            return npc_name
    return None


def format_room_label(npc_name, npc_data=None, include_id=False):
    data = npc_data if isinstance(npc_data, dict) else _npc_data(npc_name)
    if not data:
        return npc_name
    _name, _rank, _nickname, display_id, label = _label_parts(npc_name, data)
    if include_id and display_id:
        label = f"{label}({display_id})"
    return label or npc_name


def display_name(npc_name, npc_data=None):
    """玩家可见文案统一使用房间标签，避免内部键名泄漏到公告与对话。"""
    return format_room_label(npc_name, npc_data)


def prose_name(npc_name, npc_data=None):
    """叙述用称谓：优先使用数据中的 prose，缺失时保持原有简短键名/标签回退。"""
    data = npc_data if isinstance(npc_data, dict) else _npc_data(npc_name)
    prose = _text(data.get("prose")) if data else ""
    if prose:
        return prose
    label = format_room_label(npc_name, npc_data)
    return npc_name if npc_name and npc_name in label else label


def text_candidates(npc_name):
    """可用于在玩家输入中识别该 NPC 的称谓集合（键、姓名、称号、ID、标签）。"""
    return list(_exact_candidates(npc_name, _npc_data(npc_name)))


def match_name_prefix(raw_text, npc_names):
    """按内部键、姓名、称号、拼音 ID 与显示标签做最长前缀匹配。

    返回 (npc_key, matched_length)；长度按去掉空白后的字符数计，
    便于调用方从原输入中剥离角色名称。
    """
    normalized = _normalize(raw_text)
    if not normalized:
        return None, 0
    best_key, best_len = None, 0
    for npc_name in npc_names:
        for candidate in _exact_candidates(npc_name, _npc_data(npc_name)):
            candidate_key = _normalize(candidate)
            if candidate_key and normalized.startswith(candidate_key) and len(candidate_key) > best_len:
                best_key, best_len = npc_name, len(candidate_key)
    return best_key, best_len


def _gear_rows(data):
    rows = _equipment_rows(data.get("equipment", {}))
    seen = {name for name, _item_id in rows}
    gear_display = data.get("gear_display", [])
    if isinstance(gear_display, list):
        for entry in gear_display:
            if isinstance(entry, dict):
                name, item_id = _text(entry.get("name")), _text(entry.get("id"))
            elif isinstance(entry, str):
                name, item_id = _text(entry), ""
            else:
                continue
            if name and name not in seen:
                seen.add(name)
                rows.append((name, item_id))
    return rows


def _equipment_rows(equipment):
    rows = []
    seen = set()
    if not isinstance(equipment, dict):
        return rows
    for item_name in equipment.values():
        item_name = _text(item_name)
        if not item_name or item_name in seen:
            continue
        info = engine.ITEMS.get(item_name, {})
        if isinstance(info, dict) and info.get("clothing") is True:
            continue
        info = info if isinstance(info, dict) else {}
        seen.add(item_name)
        rows.append((item_name, _text(info.get("id"))))
    return rows


def _power_line(pronoun, data):
    try:
        tier = int(data.get("power_tier", 2))
    except (TypeError, ValueError):
        tier = 2
    tier = max(0, min(5, tier))
    line = f"{pronoun}{POWER_LINES[tier]}"
    style_hint = _text(data.get("martial_style"))
    if tier > 0 and style_hint:
        line += f"，{style_hint}"
    return line + "。"


def _age_line(pronoun, data):
    age_desc = _text(data.get("age_desc"))
    if not age_desc:
        return ""
    if age_desc in ("看不出年纪", "看不出年龄"):
        return f"{pronoun}看不出具体年纪。"
    if age_desc.startswith("年"):
        return f"{pronoun}{age_desc}。"
    return f"{pronoun}约莫{age_desc}。"


def _health_line(pronoun, data, state, record):
    if state == "injured":
        injury = _text(record.get("injury_level")) or "light"
        return pronoun + INJURY_LINES.get(injury, INJURY_LINES["light"])
    if state == "busy":
        source = _text(record.get("source"))
        reason = _text(record.get("reason"))
        if reason and not source.startswith("faction_conflict:"):
            clause = busy_clause(pronoun, reason)
            if clause:
                return clause + "。"
        return pronoun + STATE_LINES["busy"]
    if state in STATE_LINES:
        return pronoun + STATE_LINES[state]
    trait = _text(data.get("condition_trait"))
    if trait:
        return f"{pronoun}{trait}，气色尚可。"
    return f"{pronoun}气色尚可，看不出有什么伤病。"


def build_npc_view(player, npc_name):
    data = _npc_data(npc_name)
    pronoun = _pronoun(data)
    face_attire = _text(data.get("face_attire")) or _text(data.get("appearance")) or _text(data.get("desc"))
    if not face_attire:
        face_attire = "看起来普普通通，没什么特别的。"
    if not face_attire.startswith(("他", "她")):
        face_attire = pronoun + face_attire
    record = player.get_npc_state_record(npc_name) if hasattr(player, "get_npc_state_record") else {}
    record = record if isinstance(record, dict) else {}
    state = _text(record.get("state")) or "normal"
    return {
        "key": npc_name,
        "pronoun": pronoun,
        "face_attire": face_attire,
        "age_line": _age_line(pronoun, data),
        "power_line": _power_line(pronoun, data),
        "health_line": _health_line(pronoun, data, state, record),
        "state": state,
        "gear": _gear_rows(data),
    }


def _player_face_attire(profile):
    custom = _text(profile.get("face_attire"))
    if custom:
        for prefix in ("他", "她"):
            if custom.startswith(prefix):
                return "你" + custom[1:]
        return custom if custom.startswith("你") else f"你{custom}"
    gender = _text(profile.get("gender"))
    if gender == "female":
        return "你穿着一身洗得发白的青布衣裙，腰间束着旧布带，衣角沾着些风尘。"
    if gender == "neutral":
        return "你穿着一身洗得发白的青布衣衫，腰间束着旧布带，衣角沾着些风尘。"
    return "你穿着一身洗得发白的青布劲装，腰间束着旧布带，衣角沾着些风尘。"


def _player_power_line(player):
    try:
        level = max(1, int(getattr(player, "level", 1) or 1))
    except (TypeError, ValueError):
        level = 1
    for threshold, line in PLAYER_POWER_LINES:
        if level < threshold:
            return line + "。"
    return PLAYER_POWER_LINE_MAX + "。"


def _player_health_line(player):
    try:
        hp = max(0, int(getattr(player, "hp", 0) or 0))
        max_hp = max(1, int(getattr(player, "max_hp", 1) or 1))
    except (TypeError, ValueError):
        hp, max_hp = 1, 1
    ratio = hp / max_hp
    if ratio <= 0.3:
        return "你伤得很重，气息已经有些虚弱。"
    if ratio <= 0.6:
        return "你伤势不轻，脸色有些发白。"
    if ratio < 0.95:
        return "你身上带着些轻伤，气息还算平稳。"
    return "你气色尚可，看不出有什么伤病。"


def build_player_view(player):
    profile = player.get_player_profile() if hasattr(player, "get_player_profile") else {}
    profile = profile if isinstance(profile, dict) else {}
    return {
        "key": str(getattr(player, "name", "自己") or "自己"),
        "pronoun": "你",
        "face_attire": _player_face_attire(profile),
        "age_line": _age_line("你", {"age_desc": profile.get("age_desc")}),
        "power_line": _player_power_line(player),
        "health_line": _player_health_line(player),
        "state": "player",
        "gear": _equipment_rows(getattr(player, "equipment", {})),
    }


def format_look(view):
    """返回五段式描述行；装备为空时不输出装备段。"""
    lines = [
        view.get("face_attire", ""),
        view.get("age_line", ""),
        view.get("power_line", ""),
        view.get("health_line", ""),
    ]
    gear = view.get("gear") or []
    if gear:
        lines.append(f"{view.get('pronoun', '他')}装备着：")
        for name, item_id in gear:
            suffix = f"({item_id})" if item_id else ""
            lines.append(f"  □ {name}{suffix}")
    return [line for line in lines if line]
