# -*- coding: utf-8 -*-
"""
main.py - 孤侠初入江湖总引擎入口
"""

import os
import random
from engine import ROOMS, SAVE_PATH, Color, clear_screen, reload_game_data, battle_pause, clear_statuses, p_statuses_global
from player import Player
from combat import combat, handle_attack
from actions import look, handle_talk_and_ask, handle_quest, handle_trading, handle_equipment_and_items, handle_forge


CMD_MAP = {
    "n": "北", "s": "南", "e": "东", "w": "西",
    "north": "北", "south": "南", "east": "东", "west": "西",
    "l": "look", "i": "inventory", "st": "status",
    "h": "help", "help": "help",
    "dazuo": "heal", "heal": "heal",
    "f": "forge", "q": "quit", "rl": "reload",
    "talk": "talk", "chat": "talk", "ask": "talk", "问": "talk", "交谈": "talk", "t": "talk",
    "k": "kill", "attack": "kill", "fight": "kill",
    "flee": "run",
    "quest": "quests", "quests": "quests", "renwu": "quests",
    "jiequ": "jiequ", "jiaofu": "jiaofu",
    "buy": "buy", "sell": "sell", "wield": "wield", "wear": "wear", "use": "use",
    "m": "map", "map": "map", "ditu": "map", "地图": "map"
}


def parse_command(user_input):
    parts = user_input.strip().split()
    if not parts:
        return "", []
    cmd = parts[0].lower()
    args = parts[1:] if len(parts) > 1 else []
    cmd = CMD_MAP.get(cmd, cmd)
    return cmd, args


def show_map(player):
    from engine import MAP_ENGINE
    print(MAP_ENGINE.render(player.location))


def show_status(player):
    print(f"\n{Color.CYAN}---------- 侠客面板 ----------{Color.RESET}")
    print(f"姓名：{Color.BOLD}{player.name}{Color.RESET}  门派：{Color.MAGENTA}{player.sect}{Color.RESET}")
    from engine import draw_bar, format_statuses
    print(f"等级：{player.level}  修为：{draw_bar(player.exp, player.exp_to_level, length=8, fill_color=Color.YELLOW)}")
    print(f"气血：{draw_bar(player.hp, player.max_hp, fill_color=Color.RED)}")
    print(f"内力：{draw_bar(player.mp, player.max_mp, fill_color=Color.BLUE)}")
    print(f"攻击：{player.get_total_atk()} (基础{player.atk})  防御：{player.get_total_defense()} (基础{player.defense})")
    print(f"银两：{Color.YELLOW}{player.gold} 两{Color.RESET}")
    w_name = player.equipment.get('weapon') or '无'
    w_lv = player.equip_enhance.get('weapon', 0)
    a_name = player.equipment.get('armor') or '无'
    a_lv = player.equip_enhance.get('armor', 0)
    print(f"兵刃：{Color.GREEN}{w_name} (+{w_lv}){Color.RESET}  防具：{Color.GREEN}{a_name} (+{a_lv}){Color.RESET}")
    print(f"身中状态：{format_statuses(p_statuses_global)}")
    print(f"{Color.CYAN}------------------------------{Color.RESET}")


def show_inventory(player):
    print(f"\n{Color.CYAN}---------- 背包行囊 ----------{Color.RESET}")
    if not player.inventory:
        print("身无长物。")
    else:
        from collections import Counter
        from engine import ITEMS
        counts = Counter(player.inventory)
        for item, cnt in counts.items():
            desc = ITEMS.get(item, {}).get("desc", "未知")
            print(f"- {Color.GREEN}{item}{Color.RESET} x{cnt}：{desc}")
    print(f"{Color.CYAN}------------------------------{Color.RESET}")


def show_help():
    print(f"\n{Color.BRIGHT_YELLOW}========== 江湖指令大全 =========={Color.RESET}")
    print(" 🚶 移动探索：n/s/e/w (移动), look/l [目标] (观察环境或观察NPC/怪物), map/m (地图), search (采集)")
    print(" 🎒 物品装备：i (背包), wield <武器> (装备), wear <防具> (穿戴), use <药剂>")
    print(" ⚔️ 战斗互动：kill <目标> (攻击), talk <NPC> [话题] (交谈/打听信息)")
    print(" 📜 任务系统：renwu (查看任务), jiequ <任务名> (接取), jiaofu <任务名> (交付)")
    print(" 💆 调息打坐：dazuo / heal (打坐调息恢复气血与内力，古庙打坐可驱散病邪)")
    print(" 💰 交易打造：shop / list (货架), buy <物品>, sell <物品>, forge (打铁)")
    print(" 💾 系统功能：save (手动存档), load (读档), status/st (属性面板), h (帮助), rl (热重载)")
    print(f"{Color.BRIGHT_YELLOW}=================================={Color.RESET}\n")


def main():
    player = None
    try:
        clear_screen()
        print(f"{Color.BRIGHT_YELLOW}==================================================")
        print("                孤 侠 初 入 江 湖                 ")
        print(f"=================================================={Color.RESET}")

        if os.path.exists(SAVE_PATH):
            c = input("检测到已有本地存档，是否载入旧进度？(y/n)：").strip().lower()
            if c in ("y", "yes", ""):
                player = Player.load_from_file()

        if not player:
            name = input("\n敢问少侠尊姓大名：").strip() or "无名侠客"
            print("\n请选择门派：\n1. 少林  2. 武当  3. 华山  4. 散人")
            choice = input("请选择 (1-4)：").strip()
            sect_map = {"1": "少林", "2": "武当", "3": "华山", "4": "散人"}
            player = Player(name, sect_map.get(choice, "散人"))
            clear_statuses()
            player.save_to_file()

        clear_screen()
        look(player)

        while True:
            curr_room = ROOMS.get(player.location, {})
            r_name = curr_room.get("name", "未知区域")
            raw_in = input(f"\n<{r_name}> 指令 > ").strip()
            cmd, args = parse_command(raw_in)

            if not cmd: continue

            if cmd in ("quit", "exit"):
                player.save_to_file()
                print("少侠保重，后会有期！")
                break
            elif cmd == "save":
                player.save_to_file()
            elif cmd == "load":
                loaded = Player.load_from_file()
                if loaded: player = loaded; look(player)
            elif cmd == "help":
                show_help()
            elif cmd == "map":
                show_map(player)
            elif cmd in ("reload", "热重载"):
                reload_game_data(); look(player)
            elif cmd in ("look", "看"):
                look(player, args)
            elif cmd in ("status", "状态"):
                show_status(player)
            elif cmd in ("inventory", "背包"):
                show_inventory(player)
            elif cmd == "talk":
                handle_talk_and_ask(player, args)
            elif cmd in ("quests", "jiequ", "jiaofu"):
                handle_quest(player, cmd, args)
            elif cmd in ("shop", "list", "buy", "sell"):
                handle_trading(player, cmd, args)
            elif cmd in ("wield", "wear", "use"):
                handle_equipment_and_items(player, cmd, args)
            elif cmd in ("kill", "attack"):
                handle_attack(player, args)
            elif cmd == "heal":
                is_temple = (player.location == "temple")
                bonus = 2 if is_temple else 1
                rec_hp = 30 * bonus
                rec_mp = 20 * bonus
                player.hp = min(player.max_hp, player.hp + rec_hp)
                player.mp = min(player.max_mp, player.mp + rec_mp)
                if is_temple:
                    clear_statuses()
                    print(f"{Color.BRIGHT_GREEN}古庙石佛前盘膝打坐，气血恢复 {rec_hp} 点，内力恢复 {rec_mp} 点，一身病邪异状皆被驱散！{Color.RESET}")
                else:
                    print(f"{Color.GREEN}盘膝打坐调息，恢复了 {rec_hp} 点气血与 {rec_mp} 点内力！{Color.RESET}")
            elif cmd == "search":
                if "forage" in curr_room:
                    found = False
                    for item, chance in curr_room["forage"].items():
                        if random.random() < chance:
                            player.inventory.append(item)
                            print(f"{Color.GREEN}一番仔细搜寻，找到了【{item}】！{Color.RESET}")
                            found = True
                    if not found: print("仔细搜寻了一圈，一无所获。")
                else: print("此地没有可采摘搜寻的资源。")
            elif cmd == "forge":
                handle_forge(player, args)
            elif cmd in curr_room.get("exits", {}):
                player.location = curr_room["exits"][cmd]
                clear_screen()
                look(player)

                next_room = ROOMS.get(player.location, {})
                if not next_room.get("safe", False) and next_room.get("enemies") and random.random() < 0.45:
                    e_name = random.choice(next_room["enemies"])
                    print(f"\n{Color.RED}跳出个【{e_name}】挡住去路！{Color.RESET}")
                    battle_pause(0.8)
                    combat(player, e_name)
            else:
                print(f"{Color.RED}未知指令。输入 h 或 help 可查看全部命令大全。{Color.RESET}")

    except KeyboardInterrupt:
        if player:
            player.save_to_file()
            print("\n游戏被手动中断，已自动为你保存当前进度。少侠后会有期！")
        else:
            print("\n游戏已退出。")


if __name__ == "__main__":
    main()