"""Alpha319：商铺货架重分配、青石书铺、火折子夜探与江湖舆图。"""
import contextlib
import io
import json
import os
import tempfile
from pathlib import Path

import engine
import main
from actions import (
    apply_consumable,
    handle_explore,
    handle_inn_service,
    handle_quest,
    handle_skills,
    handle_talk_and_ask,
    handle_trading,
    look,
)
from player import Player

ROOT = Path(__file__).resolve().parents[1]
NIGHT_CLOCK = 12   # 18:00
DAY_CLOCK = 6      # 12:00
QUEST = "夜探旧柴场"
TOKEN = "焦黑木牌"
TOKEN_FLAG = "night_woodlot:token_found"


def _data(name):
    return json.loads((ROOT / "data" / name).read_text(encoding="utf-8"))


def capture(fn, *args):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        result = fn(*args)
    return out.getvalue(), result


def test_four_existing_shops_have_the_reviewed_shelves():
    npcs = _data("npcs.json")
    assert npcs["药铺老板"]["shop"] == ["疗伤药", "回内丹", "金创药", "大还丹", "护体丹", "草药", "蛇胆"]
    assert npcs["掌柜"]["shop"] == ["粗粮馒头", "热汤面", "酱香烧鸡", "竹叶青", "干粮"]
    assert npcs["杂货铺老板"]["shop"] == ["采药小锄", "麻绳", "火折子", "干粮", "粗粮馒头"]
    assert npcs["书铺掌柜"]["shop"] == ["基础拳谱", "流云步谱", "江湖舆图"]

    medicines = {"疗伤药", "回内丹", "金创药", "大还丹", "护体丹"}
    assert not medicines & set(npcs["掌柜"]["shop"])
    assert not medicines & set(npcs["杂货铺老板"]["shop"])
    assert "采药小锄" not in npcs["药铺老板"]["shop"]
    assert npcs["杂货铺老板"]["shop"].count("采药小锄") == 1


def test_inn_shop_lists_lodging_service_without_creating_an_item():
    player = Player("客栈服务验收", "散人")
    player.location = "inn"
    player.gold = 50
    player.set_var("quest_clock", 7)
    shelf, _ = capture(handle_trading, player, "shop", [])
    assert "6. 住店 - 12 两" in shelf
    assert "输入“住店”" in shelf
    assert "疗伤药" not in shelf and "护体丹" not in shelf
    assert "住店" not in engine.ITEMS

    inventory_before = list(player.inventory)
    stay, steps = capture(handle_inn_service, player, "住店")
    assert steps == 17
    assert player.gold == 38
    assert player.inventory == inventory_before
    assert "这一觉过去 17 个世界时刻" in stay


def test_bookshop_is_east_of_village_gate_with_live_shopkeeper():
    rooms = _data("rooms.json")
    npcs = _data("npcs.json")
    room = rooms["village_bookshop"]
    assert room["coord"] == [3, 1]
    assert room["exits"] == {"西": "village_gate"}
    assert rooms["village_gate"]["exits"]["东"] == "village_bookshop"
    assert "书铺掌柜" in room["npcs"]
    assert npcs["书铺掌柜"]["home_room"] == "village_bookshop"
    assert npcs["书铺掌柜"]["shop"] == ["基础拳谱", "流云步谱", "江湖舆图"]

    player = Player("书铺验收", "散人")
    player.location = "village_bookshop"
    assert "书铺掌柜" in player.get_npcs_in_room(player.location)


def test_bookshop_manuals_are_level_gated_and_consumed_only_on_success():
    items = _data("items.json")
    assert items["基础拳谱"]["teaches_skill"] == "江湖散手"
    assert items["流云步谱"]["teaches_skill"] == "流云步"
    assert items["基础拳谱"]["type"] == items["流云步谱"]["type"] == "manual"
    manual_flags = {
        row["name"]: row.get("manual_learnable")
        for row in engine.SKILLS["散人"]
        if isinstance(row, dict) and row.get("name") in ("江湖散手", "流云步")
    }
    assert manual_flags == {"江湖散手": True, "流云步": True}

    player = Player("秘籍门槛验收", "散人")
    player.level = 2
    player.inventory.append("基础拳谱")
    out, ok = capture(apply_consumable, player, "基础拳谱")
    assert not ok and not player.get_skill_progress("江湖散手")["learned"]
    assert player.inventory.count("基础拳谱") == 1
    assert "需要达到 3 级" in out

    player.level = 3
    out, ok = capture(apply_consumable, player, "基础拳谱")
    assert ok and player.get_skill_progress("江湖散手")["learned"]
    assert player.inventory.count("基础拳谱") == 0
    assert "你从秘籍中领会了【江湖散手】" in out

    player.level = 3
    player.inventory.append("流云步谱")
    out, ok = capture(apply_consumable, player, "流云步谱")
    assert not ok and not player.get_skill_progress("流云步")["learned"]
    assert player.inventory.count("流云步谱") == 1
    assert "需要达到 4 级" in out

    player.level = 4
    out, ok = capture(apply_consumable, player, "流云步谱")
    assert ok and player.get_skill_progress("流云步")["learned"]
    assert player.inventory.count("流云步谱") == 0


def test_manual_and_teacher_routes_produce_identical_learned_state():
    manual_player = Player("秘籍同源验收", "散人")
    manual_player.level = 3
    manual_player.inventory.append("基础拳谱")
    capture(apply_consumable, manual_player, "基础拳谱")

    teacher_player = Player("师承同源验收", "散人")
    teacher_player.level = 3
    teacher_player.location = "village_square"
    teacher_player.gold = 50
    capture(handle_skills, teacher_player, ["学习", "江湖散手"])

    assert manual_player.get_skill_progress("江湖散手") == teacher_player.get_skill_progress("江湖散手")


def test_teacher_lesson_fees_and_insufficient_gold_failure_cost_no_time():
    fees = engine.SECTS["散人"]["lesson_fees"]
    assert fees == {"江湖散手": 10, "流云步": 20}
    assert engine.SECTS["散人"]["skill_teachers"]["基础吐纳"] == "江湖武师"
    assert engine.SECTS["散人"]["skill_teachers"]["江湖散手"] == "江湖武师"
    assert engine.SECTS["散人"]["skill_teachers"]["流云步"] == "江湖武师"

    wushi = engine.NPCS["江湖武师"]
    lesson_choice = next(c for c in wushi["dialogue_choices"] if c["id"] == "wushi_learn_basics")
    assert "流云步" in lesson_choice["keywords"]
    assert "基础吐纳不收学费" in lesson_choice["response"]
    assert "江湖散手 10 两" in lesson_choice["response"]
    assert "流云步 20 两" in lesson_choice["response"]
    assert "江湖散手 10 两" in wushi["info"]["学武"]

    talker = Player("武师学费文案验收", "散人")
    talker.location = "village_square"
    talker.set_var("quest_clock", 7)
    out, _ = capture(handle_talk_and_ask, talker, ["武师", "学武"])
    assert "江湖散手 10 两" in out
    assert "流云步 20 两" in out

    player = Player("学费不足验收", "散人")
    player.level = 3
    player.location = "village_square"
    player.gold = 5
    player.set_var("quest_clock", 7)
    out, _ = capture(handle_skills, player, ["学习", "江湖散手"])
    assert "需付 10 两" in out
    assert player.gold == 5
    assert not player.get_skill_progress("江湖散手")["learned"]
    assert player.get_quest_clock() == 7

    player.gold = 50
    out, _ = capture(handle_skills, player, ["学习", "江湖散手"])
    assert "你向江湖武师付了 10 两学费" in out
    assert player.gold == 40
    assert player.get_skill_progress("江湖散手")["learned"]


def test_liuyunbu_teacher_gate_is_still_village_square_only():
    player = Player("流云步师承验收", "散人")
    player.level = 4
    player.location = "village_gate"
    player.gold = 50
    out, _ = capture(handle_skills, player, ["学习", "流云步"])
    assert "学习本门武学须前往村中广场" in out
    assert not player.get_skill_progress("流云步")["learned"]
    assert player.gold == 50

    player.location = "village_square"
    out, _ = capture(handle_skills, player, ["学习", "流云步"])
    assert "你向江湖武师付了 20 两学费" in out
    assert player.get_skill_progress("流云步")["learned"]
    assert player.gold == 30


def _night_player(with_light):
    player = Player("夜探火折子验收", "散人")
    player.location = "old_woodlot"
    player.set_var("quest_clock", NIGHT_CLOCK)
    if with_light:
        player.inventory.append("火折子")
    return player


def test_token_needs_night_and_light_and_cannot_be_farmed():
    room = _data("rooms.json")["old_woodlot"]
    assert room["night_hours"] == [18, 6]
    event = room["exploration_events"][0]
    assert event["night_only"] is True
    assert event["requires"] == {"items": {"火折子": 1}, "not_flags": [TOKEN_FLAG]}
    assert event["consume_items"] == {"火折子": 1}
    assert "一次夜探后便会烧尽" in _data("items.json")["火折子"]["desc"]

    daylight = _night_player(True)
    daylight.set_var("quest_clock", DAY_CLOCK)
    out, _ = capture(handle_explore, daylight)
    assert daylight.inventory.count(TOKEN) == 0
    assert "获得：焦黑木牌" not in out

    dark = _night_player(False)
    out, _ = capture(handle_explore, dark)
    assert dark.inventory.count(TOKEN) == 0
    assert "获得：焦黑木牌" not in out
    assert "需要火折子照明" in out

    lit = _night_player(True)
    out, _ = capture(handle_explore, lit)
    assert lit.inventory.count(TOKEN) == 1
    assert lit.world_state["flags"].get(TOKEN_FLAG) is True
    assert "获得：焦黑木牌 ×1" in out
    assert "消耗：火折子 ×1（剩余 0）" in out
    assert lit.inventory.count("火折子") == 0
    out, _ = capture(handle_explore, lit)
    assert lit.inventory.count(TOKEN) == 1
    assert lit.inventory.count("火折子") == 0


def test_quest_delivery_consumes_token(monkeypatch):
    quest = _data("quests.json")[QUEST]
    assert quest["turn_in_npc"] == "守卫"
    assert quest["target_type"] == "collect"
    assert quest["target_name"] == TOKEN
    assert quest["required_cnt"] == 1

    monkeypatch.setattr(Player, "save_to_file", lambda self, filename=None: True)
    player = Player("木牌交付验收", "散人")
    player.location = "village_gate"
    player.set_var("quest_clock", 7)
    player.inventory.append(TOKEN)
    player.active_quests[QUEST] = 1
    player.quest_states[QUEST] = {"stage": 0, "progress": 1}
    gold_before = player.gold

    out, _ = capture(handle_quest, player, "jiaofu", [QUEST])
    assert "交付物品：焦黑木牌 ×1（剩余 0）" in out
    assert player.inventory.count(TOKEN) == 0
    assert QUEST not in player.active_quests
    assert QUEST in player.completed_quests
    assert player.gold == gold_before + quest["reward"]["gold"]


def test_map_view_lists_current_exits_without_consuming_the_map():
    player = Player("舆图验收", "散人")
    player.location = "village_gate"
    player.inventory.append("江湖舆图")
    out, _ = capture(look, player, ["江湖舆图"])
    assert "【江湖舆图】" in out
    assert "所在：青石村口" in out
    assert "北：青石长街" in out
    assert "南：黄土官道" in out
    assert "东：青石书铺" in out
    assert player.inventory.count("江湖舆图") == 1
    assert "舆图" not in main.CMD_MAP and "江湖舆图" not in main.CMD_MAP


def test_v12_roundtrip_keeps_new_items_flag_and_quest_progress():
    player = Player("Alpha319存档验收", "散人")
    player.level = 3
    player.location = "old_woodlot"
    player.set_var("quest_clock", NIGHT_CLOCK)
    player.inventory.extend(["火折子", TOKEN, "江湖舆图"])
    player.set_flag(TOKEN_FLAG, True)
    player.active_quests[QUEST] = 1
    player.quest_states[QUEST] = {"stage": 0, "progress": 1}

    fd, path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            player.save_to_file(path)
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        assert raw["version"] == engine.SAVE_VERSION == 12
        assert len(raw) == 24
        with contextlib.redirect_stdout(io.StringIO()):
            loaded = Player.load_from_file(path)
    finally:
        os.remove(path)

    assert {"火折子", TOKEN, "江湖舆图"} <= set(loaded.inventory)
    assert loaded.get_flag(TOKEN_FLAG) is True
    assert loaded.active_quests.get(QUEST) == 1
    assert loaded.quest_states.get(QUEST) == {"stage": 0, "progress": 1}


def test_manual_prices_stay_fixed_while_ordinary_goods_float():
    player = Player("秘籍定价验收", "散人")
    player.location = "village_bookshop"
    player.economy_state.setdefault("events", {})["market_event_rate"] = 1.5
    shelf, _ = capture(handle_trading, player, "shop", [])
    assert "基础拳谱 - 买入 40 两 / 回收 20 两" in shelf
    assert "流云步谱 - 买入 60 两 / 回收 30 两" in shelf
    assert "买入 41 两" not in shelf and "买入 61 两" not in shelf
    assert "江湖舆图 - 买入 30 两" in shelf

    look_shelf, _ = capture(look, player, ["货架"])
    assert look_shelf == shelf
    inventory_before = list(player.inventory)
    gold_before = player.gold
    counter_view, _ = capture(look, player, ["柜台"])
    goods_view, _ = capture(look, player, ["商品"])
    assert counter_view == goods_view == shelf
    assert player.inventory == inventory_before and player.gold == gold_before


def test_map_view_adds_only_walked_second_ring():
    player = Player("舆图二环验收", "散人")
    player.location = "village_gate"
    player.inventory.append("江湖舆图")
    player.mark_visited("village_gate")
    fresh, _ = capture(look, player, ["江湖舆图"])
    assert "北：青石长街" in fresh
    assert "再往" not in fresh

    player.mark_visited("village_square")
    out, _ = capture(look, player, ["江湖舆图"])
    assert "再往北：村中广场" in out
    assert "未曾踏足的地方仍是空白" in out


def test_schedule_boundary_talk_and_turn_in_refresh_before_check(monkeypatch):
    monkeypatch.setattr(Player, "save_to_file", lambda self, filename=None: True)
    player = Player("换班边界验收", "散人")
    player.location = "village_gate"
    player.set_var("quest_clock", 23)
    player.refresh_npc_schedules()
    assert player.get_npc_location("守卫", refresh=False) is None
    player.set_var("quest_clock", 24)

    out, _ = capture(handle_talk_and_ask, player, ["守卫"])
    assert "青石长街" in out
    assert "往北边过去" in out

    player.inventory.append(TOKEN)
    player.active_quests[QUEST] = 1
    player.quest_states[QUEST] = {"stage": 0, "progress": 1}
    out, ok = capture(handle_quest, player, "jiaofu", [QUEST])
    assert not ok
    assert "请回到【守卫】处交付任务" in out
    assert "青石长街" in out
    assert QUEST in player.active_quests

    player.location = "village_south_street"
    out, ok = capture(handle_quest, player, "jiaofu", [QUEST])
    assert ok
    assert QUEST not in player.active_quests and QUEST in player.completed_quests


def test_blacksmith_shelf_includes_iron_ore_and_is_purchasable():
    npcs = _data("npcs.json")
    assert npcs["铁匠"]["shop"] == ["铁剑", "精铁剑", "皮甲", "锁子甲", "砍柴斧", "矿镐", "铁矿石"]

    player = Player("打铁铺货架验收", "散人")
    player.location = "blacksmith"
    player.gold = 50
    shelf, _ = capture(look, player, ["货架"])
    assert "铁矿石 - 买入 12 两" in shelf
    for item in ("铁剑", "精铁剑", "皮甲", "锁子甲", "砍柴斧", "矿镐"):
        assert item in shelf
    before = player.inventory.count("铁矿石")
    out, ok = capture(handle_trading, player, "buy", ["铁矿石", "1"])
    assert ok
    assert player.inventory.count("铁矿石") == before + 1
    assert player.gold == 38
