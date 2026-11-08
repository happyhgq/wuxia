# -*- coding: utf-8 -*-
"""世界主动动态消息：把 NPC 移动、天色变化与场景声响自然推到玩家面前。

本模块只读取既有世界时钟与 V12 `world_state.variables`，推送标记写入
`ambient_world` 子字典；不新增存档顶层字段，不启动线程或定时器。
消息在玩家按下回车之后、指令产生反馈之前输出，最多五条。

推送顺序：普通行动为“NPC 移动 > 车马过客（低频）> 天色 > 天气 > 节气 > 场景声响”；
“停留”指令必推车马过客，按“NPC 移动 > 车马过客 > 天色 > 天气 > 节气 > 场景声响”
取用，同一 NPC 只保留最后一条移动。普通行动每 12 个世界时刻按“时刻+场景”
确定性抽取一次车马，连续两次至少间隔 2 个时刻，不排队、不补推。
同一方向、同一出口、同一移动类型的多人移动合并为一句，人名全部保留；
不同方向、不同移动类型与特殊移动不合并。车马过客按场景取词：街巷野外用行人车马；
客栈一楼大堂与二楼走廊改用客人、伙计等室内过客；标记 `indoor` 的店铺、厅堂、
洞窟与暗道改用脚步声、人影等室内过客和室内声响；无方位出口的室内不生成过客。
换天文案对标记 `window_view` 的室内（客栈二楼走廊与客房）使用“窗外”视角，
其余室内使用“檐外”视角。天色与室外天气措辞不假定城镇街巷：山地、荒野与
城镇共用同一套室外文案，室内另用一套只写光线与屋内动静的文案。
露天街巷、院落与演武场即使有院墙也保持室外取词。
天色播报比较的是“当前阶段”：单步行动逐时辰推进时会依次经过黎明、清晨、
正午、黄昏、入夜、深夜，不会跳段；若一次行动跨越多段（如客栈过夜、
连续推进多个时辰），只播报抵达时的阶段，不补报中间已经错过的天色，
避免一次输出多条过期消息。场景声响按世界时刻计，每 6 个时刻最多一条。
天气通常只在黎明变化，持续 1~3 天，且只影响文案；新角色首日有一段固定
引导天气（晴 → 阴 → 小雨），让新手在前 20 次行动内至少看到一次变化。
非晴天的天色播报会改用对应天气措辞，室内仍保留常规天色描述。
节气每 15 天播报一次。
无消息时不输出空行；有消息时只在首条前留一个空行，消息之间不空行。
"""

import zlib

import engine
import weather
import world_time
from ui_output import safe_print as print

AMBIENCE_KEY = "ambient_world"
MAX_MESSAGES = 5
SCENE_INTERVAL_TICKS = 6
NORMAL_TRAFFIC_PERIOD = 12
NORMAL_TRAFFIC_GAP = 2

# 天色阶段按 4 小时左右切换一次；同一阶段只播报一次。
# 室外措辞不假定街巷、屋脊或更鼓，山地、荒野与城镇都能成立。
_PHASE_TABLE = (
    (5, "dawn", "天色微明，晨雾自远处缓缓散去。"),
    (8, "morning", "日头升高，四下渐渐有了声响。"),
    (12, "noon", "日头当空，地上的影子缩成一线。"),
    (16, "dusk", "天色渐暗，暮色四合。"),
    (20, "night", "夜色沉沉，四下渐渐静了下来。"),
    (23, "late_night", "夜深人静，只余风声偶尔传来。"),
)
PHASE_MESSAGES = {phase: text for _hour, phase, text in _PHASE_TABLE}

# 室内没有街巷与屋脊可写，只描述透进来的光线与屋里的动静。
_INDOOR_PHASE_MESSAGES = {
    "dawn": "晨光透进来，屋里的暗影淡了些。",
    "morning": "日头升高，屋里的光线也亮了些。",
    "noon": "日头当空，屋内的影子缩成一线。",
    "dusk": "天色渐暗，暮色四合。",
    "night": "夜色沉沉，屋里渐渐安静下来。",
    "late_night": "夜深人静，四下没有半点声响。",
}

# 天气转换按室外/室内取词；室内不写雨雪实景，只保留檐外声响与光线变化。
# 有窗的室内（如客栈二楼）另用“窗外”视角，避免把窗口写成檐下。
_WEATHER_TRANSITIONS = {
    "clear": ("云开天青，日头重新照了下来。", "檐外的天色放晴了。"),
    "cloudy": ("云层压了下来，天色转阴。", "檐外的光线暗了些，像是阴了天。"),
    "rain": ("细雨落了下来，四下很快有了水声。", "檐外传来细密的雨声。"),
    "storm": ("乌云翻涌，雷声自远处滚过。", "远处闷雷滚过，檐外雨声大作。"),
    "snow": ("雪片悄然飘落，地面渐渐白了。", "檐外悄无声息地飘起了雪。"),
    "fog": ("雾气漫起，近处的景物渐渐模糊。", "檐外雾气漫起，近处一片白茫茫。"),
}

_WINDOW_WEATHER_TRANSITIONS = {
    "clear": "窗外天色放晴了。",
    "cloudy": "窗外的光线暗了些，像是阴了天。",
    "rain": "窗外落着细雨，檐角滴着水。",
    "storm": "窗外乌云翻涌，远处闷雷滚过。",
    "snow": "窗外悄无声息地飘起了雪。",
    "fog": "窗外雾气漫起，近处一片白茫茫。",
}

# 非晴天时，室外天色文案改为与天气一致的措辞；室内沿用室内天色。
_WEATHER_PHASE_MESSAGES = {
    "rain": {
        "dawn": "细雨在晨色里落个不停。",
        "morning": "雨势不大，四下已是一片湿意。",
        "noon": "雨丝斜斜落下，远处的景物都模糊了。",
        "dusk": "暮色里雨声更密了些。",
        "night": "夜雨淅沥，四下只剩雨声。",
        "late_night": "夜雨未歇，四下只剩淅沥声。",
    },
    "storm": {
        "dawn": "雷声在云后低低滚动，天色发沉。",
        "morning": "风势见长，乌云压得很低。",
        "noon": "雷声骤起，雨点砸了下来。",
        "dusk": "雷雨未停，暮色被闪电照得发白。",
        "night": "夜雷滚过天际，雨声铺天盖地。",
        "late_night": "雷声渐远，雨还在下。",
    },
    "snow": {
        "dawn": "雪光映着晨色，天地格外安静。",
        "morning": "雪片无声落着，地面一片素白。",
        "noon": "雪势渐缓，日头藏在铅云后面。",
        "dusk": "暮色与雪光混在一处，路影模糊。",
        "night": "夜雪静静落着，脚步声显得很轻。",
        "late_night": "雪还在下，四野寂静无声。",
    },
    "fog": {
        "dawn": "晨雾浓得化不开，几步外便看不清人影。",
        "morning": "雾气未散，日头只透出一团昏黄。",
        "noon": "雾里日影朦胧，远近都失了轮廓。",
        "dusk": "暮色沉进雾里，天光显得格外昏黄。",
        "night": "夜雾漫起，四下只剩一片昏沉。",
        "late_night": "浓雾未散，四下静得听不见回声。",
    },
}

_MOUNTAIN_SCENE = (
    "山风掠过檐角，铜铃轻响。",
    "远处山寺传来一声悠长的钟响。",
    "风穿过松林，发出细碎的涛声。",
)

_SCENE_MESSAGES = {
    "main": (
        "巷口传来几声犬吠。",
        "远处传来一声钟响。",
        "一阵风卷着落叶从街面掠过。",
    ),
    "northfront_town": (
        "镇口的旗幡被风吹得猎猎作响。",
        "远处传来几声马蹄。",
        "街角的茶摊上有人低声谈笑。",
    ),
    "guiyun_city": (
        "街角有人低声交谈，又很快散去。",
        "更远处传来打更的梆子声。",
        "一阵车马声由远及近，又渐渐远去。",
    ),
    "mistwood": (
        "林间惊起几只飞鸟。",
        "风穿过树梢，簌簌作响。",
        "远处传来一声不知名的兽鸣。",
    ),
    "inn_upper": (
        "隔壁传来杯盏轻碰的声响。",
        "走廊尽头传来轻轻的脚步声。",
        "楼下隐约传来店小二的吆喝。",
    ),
    "sunken_ruins": (
        "废墟深处传来碎石滑落的声响。",
        "一阵阴风穿过断墙。",
        "远处似有铁器轻碰的回声。",
    ),
    "bandit_zone": (
        "岭上传来几声鸦鸣。",
        "远处隐约响起刀兵碰撞的脆响。",
        "山道旁的灌木被风压得沙沙作响。",
    ),
    "duanhun_ridge": (
        "岭上传来几声鸦鸣。",
        "远处的烽台在风里静默伫立。",
        "一阵寒风卷过栈道，带起细碎砂石。",
    ),
    "shaolin_mountain": _MOUNTAIN_SCENE,
    "wudang_mountain": _MOUNTAIN_SCENE,
    "huashan_mountain": _MOUNTAIN_SCENE,
    "tieyi_mountain": _MOUNTAIN_SCENE,
}
_DEFAULT_SCENE = ("远处传来几声隐约的响动。",)

# 停留时路过的车马行人；方向和邻接地名取自当前场景的真实出口，避免与地图矛盾。
_TRAFFIC_TEMPLATES = (
    "一名青衫客骑着枣红马，朝{dir}边（{place}）疾驰而去。",
    "一位白衣女侠骑着玉色骏马，从{dir}边（{place}）一路疾驰而来。",
    "一队镖师护着镖车，从{dir}边（{place}）缓缓行来。",
    "两名捕快按着腰刀，往{dir}边（{place}）快步去了。",
    "一辆驴车吱呀驶过，转向{dir}边（{place}）去了。",
    "有个挑担货郎，沿{dir}边（{place}）走远了。",
    "几名骑士并辔而过，马蹄声渐渐消失在{dir}边（{place}）的方向。",
    "一位行脚僧托着钵，从{dir}边（{place}）缓步而来。",
    "一个背着书箱的书生，朝{dir}边（{place}）匆匆赶去。",
    "一辆牛车慢慢碾过石板路，往{dir}边（{place}）去了。",
)
_CARDINAL_EXITS = ("北", "南", "东", "西")

# 室内场景不能出现镖车、牛车、马匹；按楼层与安全内室分开取词。
_LOBBY_TRAFFIC_TEMPLATES = (
    "店小二端着茶盘，从{dir}边（{place}）匆匆走过。",
    "一位客人掀起门帘，从{dir}边（{place}）走了进来。",
    "一位行商背着包袱，朝{dir}边（{place}）去了。",
    "柜台后有人应了一声，又低头忙自己的事。",
    "门帘轻响，有人从{dir}边（{place}）走了进来。",
)
_UPPER_TRAFFIC_TEMPLATES = (
    "一名伙计提着水壶，从{dir}边（{place}）走过。",
    "一位客人推门而出，往{dir}边（{place}）去了。",
    "廊下传来脚步声，有人朝{dir}边（{place}）走去了。",
    "隔壁房门轻轻开合，有人从{dir}边（{place}）经过。",
    "有人倚在窗边低声交谈，随后朝{dir}边（{place}）去了。",
)
# 普通室内不出现街面车马，也不假定一定有客栈柜台或门帘。
_INDOOR_TRAFFIC_TEMPLATES = (
    "有脚步声从{dir}边（{place}）传来，片刻又远去。",
    "一个人影从{dir}边（{place}）经过，没有停留。",
    "有人从{dir}边（{place}）走来，又悄然离去。",
    "远处传来低低的说话声，随后归于安静。",
)
# 通用室内声响，兼顾店铺、厅堂、洞窟与暗道。
_INDOOR_SCENE = (
    "角落里传来细微的响动。",
    "有风从缝隙里透进来，带着凉意。",
    "远处传来一声轻响，很快又归于安静。",
)
_LOBBY_SCENE = (
    "柜台后的算盘珠轻轻响了几声。",
    "后厨传来一阵锅铲碰撞的声响。",
    "大堂里有人低声交谈，又很快压下声音。",
)
_WAIT_FEEDBACK = (
    "你停下脚步，留意四周的动静。",
    "你放缓脚步，听着四周细微的声响。",
    "你驻足片刻，打量眼前的景象。",
    "你静立片刻，等周围的动静过去。",
    "你停了停，留心近处的变化。",
)


def phase_for_hour(hour):
    """把 0~23 的钟点换算成天色阶段；异常输入按深夜处理。"""
    try:
        hour = int(hour) % 24
    except (TypeError, ValueError, OverflowError):
        hour = 0
    phase = "late_night"
    for start, name, _text in _PHASE_TABLE:
        if hour >= start:
            phase = name
    return phase


def phase_for_tick(tick):
    return phase_for_hour(world_time.world_hour(tick))


def _state(player):
    world_state = getattr(player, "world_state", None)
    if not isinstance(world_state, dict):
        return {}
    variables = world_state.setdefault("variables", {})
    if not isinstance(variables, dict):
        variables = {}
        world_state["variables"] = variables
    state = variables.get(AMBIENCE_KEY)
    if not isinstance(state, dict):
        state = {}
        variables[AMBIENCE_KEY] = state
    return state


def _room_is_indoor(player):
    room = engine.ROOMS.get(getattr(player, "location", ""), {}) or {}
    floor = room.get("floor")
    return (
        room.get("indoor") is True
        or room.get("window_view") is True
        or bool(room.get("safe_zone"))
        or (isinstance(floor, int) and not isinstance(floor, bool) and floor >= 1)
    )


def _weather_message(player, kind):
    variants = _WEATHER_TRANSITIONS.get(kind)
    if not variants:
        return None
    outdoor, indoor = variants
    if _room_is_indoor(player):
        room = engine.ROOMS.get(getattr(player, "location", ""), {}) or {}
        if room.get("window_view") is True:
            return _WINDOW_WEATHER_TRANSITIONS.get(kind, indoor)
        return indoor
    return outdoor


def _time_covers_weather(player, kind):
    """天色文案是否已经带出天气；只有专门写了该天气的天色才算覆盖。"""
    return kind in _WEATHER_PHASE_MESSAGES and not _room_is_indoor(player)


def _time_message(player, tick, kind="clear"):
    phase = phase_for_tick(tick)
    state = _state(player)
    previous = state.get("phase")
    if previous == phase:
        return None
    state["phase"] = phase
    # 旧存档首次推送只记录当前阶段，避免一进游戏就补报一条过期天色。
    if not isinstance(previous, str):
        return None
    if _room_is_indoor(player):
        return _INDOOR_PHASE_MESSAGES.get(phase, PHASE_MESSAGES.get(phase))
    if kind != "clear":
        return _WEATHER_PHASE_MESSAGES.get(kind, {}).get(phase, PHASE_MESSAGES.get(phase))
    return PHASE_MESSAGES.get(phase)


def _scene_pool(location):
    room = engine.ROOMS.get(location, {})
    floor = room.get("floor")
    if isinstance(floor, int) and floor >= 2:
        return _SCENE_MESSAGES["inn_upper"]
    if isinstance(floor, int) and floor >= 1:
        return _LOBBY_SCENE
    if room.get("indoor") is True or room.get("safe_zone"):
        return _INDOOR_SCENE
    zone = str(room.get("zone", "main") or "main")
    return _SCENE_MESSAGES.get(zone, _DEFAULT_SCENE)


def _traffic_pool(room):
    floor = room.get("floor")
    if isinstance(floor, int) and floor >= 2:
        return _UPPER_TRAFFIC_TEMPLATES
    if isinstance(floor, int) and floor >= 1:
        return _LOBBY_TRAFFIC_TEMPLATES
    if room.get("indoor") is True or room.get("safe_zone"):
        return _INDOOR_TRAFFIC_TEMPLATES
    return _TRAFFIC_TEMPLATES


def _scene_message(player, tick):
    state = _state(player)
    last = state.get("last_scene_tick")
    if not isinstance(last, int) or isinstance(last, bool):
        state["last_scene_tick"] = tick
        return None
    if tick - last < SCENE_INTERVAL_TICKS:
        return None
    state["last_scene_tick"] = tick
    pool = _scene_pool(getattr(player, "location", ""))
    index = zlib.crc32(f"{tick}:{getattr(player, 'location', '')}".encode("utf-8")) % len(pool)
    return pool[index]


def _traffic_message(player, tick):
    location = getattr(player, "location", "")
    room = engine.ROOMS.get(location, {}) or {}
    choices = [
        (direction, engine.ROOMS.get(room.get("exits", {}).get(direction), {}).get("name", ""))
        for direction in _CARDINAL_EXITS
        if room.get("exits", {}).get(direction) in engine.ROOMS
    ]
    if not choices:
        return None
    state = _state(player)
    pool = _traffic_pool(room)
    direction, place = choices[zlib.crc32(f"traffic-dir:{tick}:{location}".encode("utf-8")) % len(choices)]
    template_index = zlib.crc32(f"traffic:{tick}:{location}".encode("utf-8")) % len(pool)
    template = pool[template_index]
    text = template.format(dir=direction, place=place)
    # 连续两次停留不复用同一句，也不复用同一句式，避免过客显得像复读。
    previous_text = state.get("last_traffic")
    previous_template = state.get("last_traffic_template")
    if text == previous_text or template == previous_template:
        for offset in range(1, len(pool)):
            candidate = pool[(template_index + offset) % len(pool)]
            candidate_text = candidate.format(dir=direction, place=place)
            if candidate != previous_template and candidate_text != previous_text:
                template, text = candidate, candidate_text
                break
    state["last_traffic"] = text
    state["last_traffic_template"] = template
    state["last_traffic_tick"] = tick
    return text


def _normal_traffic_due(player, tick):
    """普通行动的低频车马：按 tick 与场景确定性抽取，连续两次不留太近。"""
    location = getattr(player, "location", "")
    room = engine.ROOMS.get(location, {}) or {}
    exits = room.get("exits", {}) or {}
    if not any(exits.get(direction) in engine.ROOMS for direction in _CARDINAL_EXITS):
        return False
    roll = zlib.crc32(f"passersby:{tick}:{location}".encode("utf-8")) % NORMAL_TRAFFIC_PERIOD
    if roll:
        return False
    last = _state(player).get("last_traffic_tick")
    if isinstance(last, int) and not isinstance(last, bool) and tick - last < NORMAL_TRAFFIC_GAP:
        return False
    return True


def wait_feedback(player):
    """无动态可推时的停留反馈；连续两次停留不重复同一句。"""
    state = _state(player)
    last = state.get("last_wait_feedback")
    if not isinstance(last, str):
        text = _WAIT_FEEDBACK[0]
    else:
        index = zlib.crc32(f"wait:{player.get_quest_clock()}".encode("utf-8")) % len(_WAIT_FEEDBACK)
        text = _WAIT_FEEDBACK[index]
        if text == last:
            text = _WAIT_FEEDBACK[(index + 1) % len(_WAIT_FEEDBACK)]
    state["last_wait_feedback"] = text
    return text


def _collect_movement_events(player):
    drain_events = getattr(player, "drain_npc_movement_events", None)
    if callable(drain_events):
        return [event for event in drain_events() if str(event.get("text", "")).strip()]
    drain = getattr(player, "drain_npc_movement_messages", None)
    if callable(drain):
        return [
            {"kind": "special", "npc": "", "text": str(text).strip()}
            for text in drain()
            if str(text).strip()
        ]
    return []


def _merge_movement_events(events):
    """同一方向、同一出口、同一移动类型的多人移动压缩成一句。

    上楼/下楼各有独立类型；传送、消失、离开等特殊移动不合并。
    人名全部保留，只是把“每人一条”压成“甲、乙、丙从南边走来”。
    """
    merged = []
    groups = {}
    for event in events:
        text = str(event.get("text", "")).strip()
        if not text:
            continue
        npc = str(event.get("npc", "")).strip()
        kind = str(event.get("kind", "special"))
        if kind in ("in", "out"):
            key = (kind, event.get("direction"), event.get("place"))
        elif kind in ("up_in", "down_in", "up_out", "down_out"):
            key = (kind,)
        else:
            key = None
        if key is None:
            merged.append({"key": None, "text": text})
            continue
        entry = groups.get(key)
        if entry is None:
            entry = {
                "key": key,
                "kind": kind,
                "direction": event.get("direction", ""),
                "place": event.get("place", ""),
                "names": [],
            }
            groups[key] = entry
            merged.append(entry)
        if npc and npc not in entry["names"]:
            entry["names"].append(npc)
    result = []
    for entry in merged:
        if entry["key"] is None:
            result.append(entry["text"])
            continue
        names = "、".join(entry["names"])
        if not names:
            continue
        kind = entry["kind"]
        direction = entry["direction"]
        place = entry["place"]
        suffix = f"（{place}）" if place else ""
        if kind == "in":
            result.append(f"{names}从{direction}边{suffix}走来。")
        elif kind == "out":
            result.append(f"{names}往{direction}边{suffix}去了。")
        elif kind == "up_in":
            result.append(f"{names}从楼上下来。")
        elif kind == "down_in":
            result.append(f"{names}从楼下走来。")
        elif kind == "up_out":
            result.append(f"{names}上楼去了。")
        elif kind == "down_out":
            result.append(f"{names}下楼去了。")
    return result


def collect_messages(player, blocked=False, include_traffic=False):
    """收集本轮候选消息，供播报与诊断共用。

    返回字典含：`movement_pool`（全部待推送移动）、`movement_selected`
    （截断后实际播报的移动）、`traffic`、`weather`（本轮换天文案）、
    `weather_kind`、`time`、`term`（节气文案）、`scene`、`messages`、
    `deferred`（因已满五条而本轮未评估的来源）。
    """
    result = {
        "blocked": bool(blocked),
        "movement_pool": [],
        "movement_selected": [],
        "traffic": None,
        "weather": None,
        "weather_kind": None,
        "time": None,
        "term": None,
        "scene": None,
        "messages": [],
        "deferred": [],
    }
    if blocked:
        return result
    tick = player.get_quest_clock()
    result["tick"] = tick
    ambience = _state(player)
    first_read = "weather_seen" not in ambience
    if first_read:
        # 首次读取只记录当前天气，避免旧档一进游戏就补报过期换天。
        current = weather._state(player, tick)
        ambience["weather_seen"] = [current["kind"], current["until_tick"]]
    # 天气状态始终推进到当前时刻，保证状态面板显示与实际一致；
    # 换天文案仍只在有空位时输出，被挤占时留到下次补上最新一条。
    weather.advance(player, tick)
    result["movement_events"] = _collect_movement_events(player)
    result["movement_pool"] = _merge_movement_events(result["movement_events"])
    result["movement_selected"] = result["movement_pool"][:MAX_MESSAGES]
    messages = list(result["movement_selected"])
    if include_traffic:
        if len(messages) < MAX_MESSAGES:
            result["traffic"] = _traffic_message(player, tick)
            if result["traffic"]:
                messages.append(result["traffic"])
        else:
            result["deferred"].append("traffic")
    elif not first_read and len(messages) < MAX_MESSAGES and _normal_traffic_due(player, tick):
        # 普通行动也按低概率遇到行人车马，不额外排队；没空位时直接放弃。
        result["traffic"] = _traffic_message(player, tick)
        if result["traffic"]:
            messages.append(result["traffic"])
    if len(messages) < MAX_MESSAGES:
        kind = weather.current_kind(player, tick)
        result["weather_kind"] = kind
        result["time"] = _time_message(player, tick, kind)
        if result["time"]:
            messages.append(result["time"])
    else:
        result["deferred"].append("time")
    # 室外非晴天时，天色文案已经按新天气取词，不再追加换天消息；
    # 室内仍用常规天色，放晴也需要单独说明，这两种情况保留换天消息。
    # 消息被前五条挤占时不丢弃，记下未确认的天气，下次正常播报补上最新一条。
    current = weather._state(player, tick)
    token = [current["kind"], current["until_tick"]]
    if _state(player).get("weather_seen") != token:
        kind = current["kind"]
        if result["time"] and _time_covers_weather(player, kind):
            _state(player)["weather_seen"] = token
        elif len(messages) < MAX_MESSAGES:
            result["weather"] = _weather_message(player, kind)
            _state(player)["weather_seen"] = token
            if result["weather"]:
                messages.append(result["weather"])
        else:
            result["deferred"].append("weather")
    if len(messages) < MAX_MESSAGES:
        result["term"] = weather.term_message(player, tick)
        if result["term"]:
            messages.append(result["term"])
    elif weather.term_is_pending(player, tick):
        result["deferred"].append("term")
    if len(messages) < MAX_MESSAGES:
        result["scene"] = _scene_message(player, tick)
        if result["scene"]:
            messages.append(result["scene"])
    else:
        result["deferred"].append("scene")
    result["messages"] = messages
    return result


def announce(player, blocked=False, include_traffic=False):
    """按“移动 > 车马 > 天色 > 天气 > 节气 > 场景”输出最多五条消息。

    `include_traffic=True` 供“停留”指令使用，在移动之后必推车马过客；
    普通行动按低概率自动抽取车马。同方向、同出口、同类型的多人移动先
    合并为一句，再参与上限截断。天色与换天同轮发生时合并为一条按新天气
    取词的天色消息。
    `blocked` 供面板或战斗调用方显式抑制推送；被抑制时保留待推送的
    NPC 移动消息、天气、天色阶段与节气，等下一次正常调用再补推。
    """
    collected = collect_messages(player, blocked=blocked, include_traffic=include_traffic)
    messages = collected["messages"]
    if not messages:
        return []
    print()
    for text in messages:
        print(text)
    return messages
