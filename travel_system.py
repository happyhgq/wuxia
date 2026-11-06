# -*- coding: utf-8 -*-
"""已探索道路上的快速旅行；路线与解锁状态写入既有 V12 world_state.flags。"""
from collections import deque
import engine
from entry_events import trigger_entry_events


def _visited(player, room_id):
    return bool(player.get_flag(f"visited:{room_id}"))


def room_access_denial(player, room):
    """返回进入地点的阻拦说明；空字符串表示允许进入。"""
    rule = room.get("access") or {}
    if rule.get("locked"):
        return str(rule.get("blocked_text", "房门紧锁，暂时无法进入。"))
    sect = rule.get("sect")
    is_sect_member = bool(sect and player.get_sect() == sect)
    has_guest_access = bool(sect and player.get_flag(f"sect:{sect}:guest_access"))
    if sect and not is_sect_member and not has_guest_access:
        return str(rule.get("blocked_text", f"此处属于【{sect}】门内区域，需取得相应身份后方可进入。"))
    if sect and rule.get("min_rank_index") is not None:
        # 客人通行许可只允许进入普通门内区域，不能代替正式门派身份，
        # 更不能绕过讲经堂、真武殿、议事堂等有明确身份门槛的场所。
        try:
            required_index = int(rule.get("min_rank_index", 0))
        except (TypeError, ValueError):
            required_index = 0
        rank_index = player.get_sect_official_rank_index(sect) if is_sect_member and hasattr(player, "get_sect_official_rank_index") else -1
        if rank_index < required_index:
            return str(rule.get("blocked_text", f"此处需要门派身份达到第 {required_index + 1} 阶。"))
    return ""


def _allowed(player, room_id):
    room = engine.ROOMS.get(room_id, {})
    return not room_access_denial(player, room)


def _known_route(player, start, target):
    """只允许走过的房间组成的路线；不穿越未探索路段或身份受限地点。"""
    queue = deque([(start, [start])])
    seen = {start}
    while queue:
        current, path = queue.popleft()
        if current == target:
            return path
        room = engine.ROOMS.get(current, {})
        for nxt in (room.get("exits", {}) or {}).values():
            if nxt in seen or nxt not in engine.ROOMS or not _visited(player, nxt) or not _allowed(player, nxt):
                continue
            seen.add(nxt)
            queue.append((nxt, path + [nxt]))
    return None


def available_destinations(player):
    current = player.location
    current_room = engine.ROOMS.get(current, {})
    if not current_room.get("travel_hub"):
        return [], "此处不是可供远行的交通节点。请先前往村口、城门或已开放的山门等交通节点。"
    # 当前所在地点即视为已抵达；旧 V12 存档无需补写 visited 标记。
    options = []
    for rid, room in engine.ROOMS.items():
        if rid == current or not room.get("travel_hub") or not _visited(player, rid) or not _allowed(player, rid):
            continue
        path = _known_route(player, current, rid)
        if path and len(path) > 1:
            options.append((rid, room.get("name", rid), len(path) - 1))
    return sorted(options, key=lambda x: (x[1], x[0])), ""


def handle_travel(player, args=None):
    args = args or []
    options, error = available_destinations(player)
    if error:
        print(error)
        return False
    if not options:
        print("目前没有已完整走过、且可供快速往返的其他交通节点。先亲自走通一条路线，再来查看。")
        return False
    if not args:
        print("【已探索路线】")
        for i, (_rid, name, steps) in enumerate(options, 1):
            print(f"{i}. {name}（已探索路线 {steps} 段）")
        print("用法：旅行 目的地名称。只会开放你实际走过的路线，不会跳过未探索区域。")
        return True
    query = " ".join(str(a) for a in args).strip()
    matches = [x for x in options if query == x[1] or query == x[0]]
    if query.isdigit():
        idx = int(query) - 1
        matches = [options[idx]] if 0 <= idx < len(options) else []
    if len(matches) != 1:
        print("没有找到唯一的可前往地点。请先输入“旅行”查看已开放的路线。")
        return False
    target, name, steps = matches[0]
    player.location = target
    player.mark_visited(target)
    print(f"你沿着已经熟悉的道路行进，抵达【{name}】。本次略过 {steps} 段已探索路程。")
    from actions import look
    look(player)
    trigger_entry_events(player, target)
    return True
