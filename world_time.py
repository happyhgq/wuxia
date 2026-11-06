# -*- coding: utf-8 -*-
"""世界时钟的唯一换算入口。

内部 tick 是最小时间单位，1 tick = 1 小时；tick 0 对应卯时初（06:00）。
NPC 日程、营生工时和界面钟点都必须经过这里，避免同一个 tick
在不同模块被解释成不同时间。
"""

WORLD_CLOCK_OFFSET = 6
SHICHEN_NAMES = ("子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥")


def world_hour(tick):
    """把世界 tick 换算为 0~23 的钟点；异常输入按卯时初处理。"""
    try:
        value = int(tick)
    except (TypeError, ValueError, OverflowError):
        value = 0
    return (value + WORLD_CLOCK_OFFSET) % 24


def shichen_name(tick):
    """返回 tick 所在时辰名；每个时辰覆盖两个小时。"""
    return SHICHEN_NAMES[((world_hour(tick) + 1) % 24) // 2]


def format_world_clock(tick):
    """用于界面显示的钟点，例如“卯时 06:00”。"""
    return f"{shichen_name(tick)}时 {world_hour(tick):02d}:00"


def ticks_until_next_dawn(tick, dawn_hour=WORLD_CLOCK_OFFSET):
    """返回从当前时刻睡到下一次黎明所需的整点 tick 数。

    恰好站在黎明时取下一天，因此结果始终大于 0；客栈过夜与
    其他“睡到天亮”的场景都应经过这里换算，避免各自硬编码钟点。
    """
    hour = world_hour(tick)
    return (dawn_hour - hour) % 24 or 24
