# -*- coding: utf-8 -*-
"""命令准入与世界时钟策略。

此模块只判断命令是否可处理、是否推进世界，不执行游戏动作；
main.py 保留同名导入以兼容现有调用与测试。
"""

_DIRECTION_ALIASES = {
    "n": "北", "s": "南", "e": "东", "w": "西", "u": "上", "d": "下",
    "内": "内", "外": "外", "后": "后", "前": "前",
}


def command_will_be_handled(cmd, curr_room):
    """在推进任务时钟前验证命令；未知输入不应改变游戏世界。"""
    handled = {
        "look", "inventory", "status", "profession", "help", "encyclopedia", "advice", "talk",
        "save", "load", "quit", "exit", "reload", "attributes", "build",
        "relations", "sect", "factions", "conflicts", "局势", "region",
        "regions", "区域", "区域局势", "influence", "skills", "information",
        "info", "rumors", "消息", "传闻", "notice_board", "memory",
        "npc_actions", "world_activity", "business_rumor", "sect_join", "security_governance",
        "explore", "wait", "events", "quests", "jiequ", "jiaofu",
        "xuanze", "fangqi", "abandon", "shop", "list", "buy", "sell",
        "wield", "wear", "equip", "use", "compare", "unequip", "equipment",
        "inn_stay", "inn_meal", "inn_tea", "inn_rumor",
        "装备", "kill", "attack", "heal", "search", "collect", "mine", "chop", "forge", "run",
        "alias", "unalias", "history", "history_up", "history_down", "knock",
        "map", "travel", "caravan", "color", "n", "s", "e", "w", "u", "d",
    }
    if cmd in handled:
        return True
    resolved_exit = _DIRECTION_ALIASES.get(cmd, cmd)
    if resolved_exit in curr_room.get("exits", {}):
        return True
    hidden = curr_room.get("hidden_exits", {})
    return isinstance(hidden, dict) and resolved_exit in hidden


_QUEST_ACTION_WORDS = {
    "接取", "接受", "接任务", "接取任务", "接受任务",
    "交付", "交任务", "完成", "放弃", "放弃任务",
    "选择", "分支", "选择分支",
    "jiequ", "jiaofu", "fangqi", "xuanze", "abandon",
}
_SECT_VIEW_WORDS = {
    "info", "详情", "查看", "rank", "身份", "授阶记录",
    "rep", "reputation", "声望", "relations", "relation", "关系",
    "列表", "list", "view",
}
_ATTRIBUTE_VIEW_WORDS = {"查看", "view", "show", "help", "?", "帮助", "info"}
_MENTORSHIP_VIEW_WORDS = {"查看", "身份", "状态", "status", "view"}


def command_advances_world(cmd, args=None):
    """判断指令是否推进世界时钟；纯查看操作不应让 NPC/商队暗中行动。"""
    if isinstance(args, str):
        args = args.split()
    args = list(args or [])
    first = str(args[0]).strip().lower() if args else ""
    read_only = {
        "look", "看", "inventory", "背包", "status", "状态", "profession",
        "build", "map", "caravan", "encyclopedia", "advice", "relations",
        "factions", "conflicts", "局势", "region", "regions", "区域", "区域局势",
        "notice_board", "npc_actions", "world_activity", "business_rumor", "商情", "color",
        # 货架、任务详情、属性、门派资料、江湖消息、记忆、装备比较等纯查看入口。
        "shop", "list", "memory", "equipment", "装备", "compare", "influence",
    }
    if cmd in read_only:
        return False
    if cmd == "travel" and not args:
        return False
    # 这些入口既能查看，也能执行改变世界/角色状态的子操作。
    if cmd in ("quests", "renwu"):
        return first in _QUEST_ACTION_WORDS
    if cmd == "attributes":
        return bool(args) and first not in _ATTRIBUTE_VIEW_WORDS
    if cmd == "sect":
        if not args or first in _SECT_VIEW_WORDS:
            return False
        if first in ("师徒", "师承", "mentorship", "师门"):
            return len(args) > 1 and str(args[1]).strip().lower() not in _MENTORSHIP_VIEW_WORDS
        return True
    if cmd in ("information", "info", "rumors", "消息", "传闻"):
        return bool(args) and first not in ("memory", "memories", "记忆", "评价")
    if cmd == "forge":
        return not (args and first in ("preview", "预览", "查看"))
    if cmd == "events" and not args:
        return False
    if cmd == "security_governance" and (not args or first in ("悬赏", "目标", "查看", "榜", "bounty")):
        return False
    if cmd == "skills" and (not args or first in ("查看", "详情", "info")):
        return False
    return cmd not in {
        "save", "load", "help", "reload", "quit", "exit", "alias", "unalias",
        "history", "history_up", "history_down", "knock", "run", "talk",
    }


# 只读预检只覆盖“处理器必然失败、且推进一个世界时刻不会改变结论”的条件。
# 依赖 NPC 是否在场、资源恢复、事件冷却的失败仍按原时序计时。
_SECT_ENTRY_GATES = {
    "华山": ("huashan_guest_hall", "sect:huashan:entry_interview"),
    "少林": ("shaolin_guest_hall", "sect:shaolin:entry_interview"),
    "武当": ("wudang_guest_hall", "sect:wudang:entry_interview"),
    "铁衣门": ("tieyi_guest_hall", "sect:tieyi:entry_interview"),
}
_SECT_PROMOTE_SECTS = ("华山", "少林", "武当", "铁衣门")
_ATTRIBUTE_ALIASES = {
    "力量": "strength", "力": "strength", "str": "strength",
    "体魄": "constitution", "体": "constitution", "con": "constitution",
    "内息": "internal", "内": "internal", "int": "internal",
    "身法": "agility", "敏捷": "agility", "agi": "agility",
    "洞察": "insight", "感知": "insight", "wis": "insight",
}


MEDITATION_UNSAFE = "unsafe"
MEDITATION_FULL_HP = "full_hp"
MEDITATION_INSUFFICIENT_MP = "insufficient_mp"


def check_meditation_allowed(player, room=None):
    """打坐前置条件；返回失败原因，None 表示可以打坐。"""
    room = room if isinstance(room, dict) else {}
    if getattr(player, "_in_combat", False):
        return MEDITATION_UNSAFE
    if room.get("safe") is not True:
        return MEDITATION_UNSAFE
    if room.get("secret_realm") is True or room.get("is_secret_realm") is True:
        return MEDITATION_UNSAFE
    try:
        hp = int(getattr(player, "hp", 0) or 0)
        max_hp = int(getattr(player, "max_hp", 0) or 0)
        if hp >= max_hp:
            return MEDITATION_FULL_HP
        mp = int(getattr(player, "mp", 0) or 0)
        max_mp = int(getattr(player, "max_mp", 0) or 0)
        mp_cost = max(1, int(max_mp * 0.10))
        if mp < mp_cost:
            return MEDITATION_INSUFFICIENT_MP
    except (TypeError, ValueError, OverflowError):
        return MEDITATION_UNSAFE
    return None


def preflight_guaranteed_failure(player, cmd, args, room=None):
    """命令是否必然失败且一个 Tick 不会改变结果；仅在确定时返回 True。"""
    args = [str(part) for part in (args or [])]
    room = room if isinstance(room, dict) else {}
    try:
        if cmd == "heal":
            return check_meditation_allowed(player, room) is not None
        if cmd == "attributes":
            return _attributes_failure(player, args)
        if cmd == "sect":
            return _sect_failure(player, args)
        if cmd == "sect_join":
            return _sect_join_failure(player, ["join"] + args)
        if cmd == "skills":
            return _skills_failure(player, args)
        if cmd == "events":
            return _events_failure(player, args)
        if cmd == "security_governance":
            return _security_failure(args)
        if cmd in ("search", "collect", "mine", "chop"):
            return _gathering_failure(player, cmd, room)
    except (KeyError, TypeError, ValueError, AttributeError, ImportError, OSError):
        return False
    return False


def _allocate_attribute_fails(player, name, points):
    key = _ATTRIBUTE_ALIASES.get(str(name).lower(), str(name).lower())
    attributes = getattr(player, "attributes", {}) or {}
    if key not in attributes:
        return True
    try:
        amount = int(points)
    except (TypeError, ValueError, OverflowError):
        return True
    if amount < 1:
        return True
    return amount > int(getattr(player, "attribute_points", 0) or 0)


def _attributes_failure(player, args):
    if not args:
        return False
    first = args[0].lower()
    if first in ("help", "?", "帮助", "view", "show", "查看", "info"):
        return False
    if first in ("add", "addpoint", "加点", "投入"):
        if len(args) < 2:
            return True
        return _allocate_attribute_fails(player, args[1], args[2] if len(args) >= 3 else "1")
    return _allocate_attribute_fails(player, args[0], args[1] if len(args) >= 2 else "1")


def _split_sect_args(args):
    if len(args) == 1 and " " in args[0].strip():
        return args[0].split()
    return list(args)


def _sect_join_failure(player, args):
    if len(args) < 2:
        return True
    import engine
    sect_name = " ".join(args[1:])
    if sect_name not in engine.SECTS or sect_name == "散人":
        return True
    gate = _SECT_ENTRY_GATES.get(sect_name)
    if gate:
        room_id, flag = gate
        if player.location != room_id or not player.get_flag(flag, False):
            return True
    try:
        level = int(getattr(player, "level", 1) or 1)
    except (TypeError, ValueError, OverflowError):
        level = 1
    try:
        entry_level = max(1, int((engine.SECTS.get(sect_name, {}) or {}).get("entry_level", 3) or 3))
    except (TypeError, ValueError):
        entry_level = 3
    if level < entry_level:
        return True
    return player.get_sect() != "散人"


def _sect_failure(player, args):
    args = _split_sect_args(args)
    if not args:
        return False
    import engine
    sub = args[0].lower()
    if sub in ("info", "详情", "查看"):
        return False
    if sub in ("join", "加入", "拜入", "拜师"):
        return _sect_join_failure(player, args)
    if sub in ("promote", "promotion", "晋升", "授阶"):
        sect_name = player.get_sect()
        if sect_name == "散人":
            return True
        if sect_name in _SECT_PROMOTE_SECTS:
            training = (engine.SECTS.get(sect_name, {}) or {}).get("training", {}) or {}
            training_room = training.get("room_id", {
                "华山": "huashan_training_ground", "少林": "shaolin_training_ground",
                "武当": "wudang_training_ground", "铁衣门": "tieyi_training_ground",
            }[sect_name])
            if player.location != training_room:
                return True
        return False
    if sub in ("修习", "请教", "门派修习", "练功"):
        training = (engine.SECTS.get(player.get_sect(), {}) or {}).get("training", {}) or {}
        if not training.get("room_id") or not training.get("lesson_teacher"):
            return True
        return player.location != training["room_id"]
    if sub in ("师徒", "师承", "mentorship", "师门"):
        sect_name = player.get_sect()
        training = (engine.SECTS.get(sect_name, {}) or {}).get("training", {}) or {}
        if sect_name == "散人" or not training.get("lesson_teacher"):
            return True
        if player.location != training.get("room_id"):
            return True
        operation = str(args[1]).lower() if len(args) >= 2 else "查看"
        if operation in ("拜师", "建立", "行礼"):
            try:
                level = int(getattr(player, "level", 1) or 1)
            except (TypeError, ValueError, OverflowError):
                level = 1
            return level < 10 or player.get_sect_official_rank_index(sect_name) < 2
        return False
    if sub in ("leave", "退出", "退门"):
        return player.get_sect() == "散人"
    if sub in ("受戒", "剃度", "戒仪"):
        if player.get_sect() != "少林":
            return True
        return player.location != "shaolin_dharma_hall"
    if sub in ("rank", "身份", "授阶记录", "rep", "reputation", "声望",
               "relations", "relation", "关系"):
        return False
    return True


def _skill_learned(player, name):
    world_state = getattr(player, "world_state", None)
    variables = world_state.get("variables") if isinstance(world_state, dict) else None
    skills = variables.get("skill_progress") if isinstance(variables, dict) else None
    entry = skills.get(name) if isinstance(skills, dict) else None
    return bool(entry.get("learned", False)) if isinstance(entry, dict) else False


def _skills_failure(player, args):
    if not args:
        return False
    import engine
    sub = args[0].lower()
    name = " ".join(args[1:]) if len(args) > 1 else ""
    if sub in ("learn", "学习", "修习"):
        if not name:
            return True
        if not player.can_learn_skill(name)[0]:
            return True
        owner = next((sect for sect, rows in engine.SKILLS.items()
                      if any(isinstance(row, dict) and row.get("name") == name for row in (rows or []))), None)
        if owner and owner == player.get_sect() and not _skill_learned(player, name):
            sect_info = engine.SECTS.get(owner, {}) or {}
            training = sect_info.get("training", {}) or {}
            required_teacher = sect_info.get("skill_teachers", {}).get(name)
            room_id = training.get("room_id")
            if required_teacher and room_id:
                if player.location != room_id:
                    return True
                if required_teacher not in player.get_npcs_in_room(player.location):
                    return True
            fee_table = sect_info.get("lesson_fees", {}) or {}
            try:
                fee = max(0, int(fee_table.get(name, 0) or 0))
            except (TypeError, ValueError):
                fee = 0
            if fee > 0 and int(getattr(player, "gold", 0)) < fee:
                return True
        return False
    if sub in ("forget", "遗忘", "忘却"):
        if not name:
            return True
        if not player.get_skill_info(name):
            return True
        owner = next((sect for sect, rows in engine.SKILLS.items()
                      if any(isinstance(row, dict) and row.get("name") == name for row in (rows or []))), None)
        if owner != player.get_sect():
            return True
        return not _skill_learned(player, name)
    if sub in ("info", "详情", "查看"):
        return False
    return True


def _events_failure(player, args):
    if not args:
        return False
    import engine
    if args[0].lower() not in ("trigger", "触发", "resolve", "处理"):
        return True
    if len(args) < 2:
        return False
    raw_id = " ".join(args[1:])
    event_id = next((key for key, value in engine.WORLD_EVENTS.items()
                     if key == raw_id or (isinstance(value, dict) and value.get("title") == raw_id)), raw_id)
    info = engine.WORLD_EVENTS.get(event_id)
    if not isinstance(info, dict):
        return True
    zone = engine.ROOMS.get(player.location, {}).get("zone", "main")
    if info.get("region") != zone:
        return True
    if info.get("once"):
        state = player.get_world_event_state(event_id)
        try:
            return int(state.get("count", 0) or 0) > 0
        except (TypeError, ValueError, OverflowError):
            return False
    return False


def _security_failure(args):
    if not args:
        return False
    return args[0].lower() not in (
        "悬赏", "目标", "查看", "榜", "bounty", "协助", "处置", "救援", "平乱",
    )


def _gathering_failure(player, cmd, room):
    if cmd in ("mine", "chop"):
        from economy import EconomyManager, TradeService
        manager = EconomyManager(getattr(player, "economy_state", {}))
        cfg = manager.resources.get(player.location)
        if not isinstance(cfg, dict) or str(cfg.get("action", "mine")) != cmd:
            return True
        return TradeService.inventory_slots_free(player) <= 0
    forage = room.get("forage")
    if not isinstance(forage, dict) or not forage:
        return True
    from economy import EconomyManager
    manager = EconomyManager(getattr(player, "economy_state", {}))
    cfg = manager.resources.get(player.location)
    configured_item = str(cfg.get("item")) if isinstance(cfg, dict) else ""
    usable = (
        isinstance(cfg, dict)
        and cfg.get("action") == "gather"
        and configured_item in {str(item) for item in forage}
    )
    if not usable:
        return True
    if cmd == "collect":
        if not player.get_flag(f"resource_discovered:{player.location}", False):
            return True
        from economy import TradeService
        return TradeService.inventory_slots_free(player) <= 0
    return False


