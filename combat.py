# -*- coding: utf-8 -*-
"""
combat.py - 回合制战斗引擎、招式选择与胜负结算
"""

import random
from copy import deepcopy
from engine import ENEMIES, SKILLS, ITEMS, Color, draw_bar, format_statuses, process_status_effects, apply_shield, battle_pause, p_statuses_global


def pick_enemy_skill(enemy_data):
    skills = enemy_data.get("skills", [])
    if not skills:
        return None
    for sk in skills:
        if random.random() < sk.get("chance", 0.3):
            return sk
    return None


def combat(player, enemy_name):
    e_data = deepcopy(ENEMIES.get(enemy_name, {}))
    if not e_data:
        print(f"找不到关于【{enemy_name}】的战斗数据！")
        return

    e_hp, e_max_hp = e_data["hp"], e_data["hp"]
    e_atk, e_def = e_data["atk"], e_data["defense"]

    p_statuses = p_statuses_global
    e_statuses = {}

    print(f"\n{Color.BRIGHT_RED}========== 战斗开始：{enemy_name} =========={Color.RESET}")

    while player.hp > 0 and e_hp > 0:
        print("\n--------------------------------------------")
        print(f"{player.name}: 气血 {draw_bar(player.hp, player.max_hp, fill_color=Color.RED)} "
              f"内力 {draw_bar(player.mp, player.max_mp, fill_color=Color.BLUE)}")
        print(f"{enemy_name}: 气血 {draw_bar(e_hp, e_max_hp, fill_color=Color.BRIGHT_RED)}")
        print(f"玩家状态: {format_statuses(p_statuses)} | 敌人状态: {format_statuses(e_statuses)}")

        p_dmg, p_stun, p_msgs = process_status_effects(p_statuses)
        e_dmg, e_stun, e_msgs = process_status_effects(e_statuses)
        player.hp = max(0, player.hp + p_dmg)
        e_hp = max(0, e_hp + e_dmg)

        for m in p_msgs: print(f"你: {m}")
        for m in e_msgs: print(f"{enemy_name}: {m}")

        if player.hp <= 0 or e_hp <= 0: break

        # 玩家回合
        if not p_stun:
            print("\n行动选项: [1] 普通攻击  [2] 武学招式  [3] 使用物品  [4] 尝试逃跑")
            act = input("请选择行动：").strip()

            if act == "4":
                if random.random() < 0.55:
                    print(f"{Color.GREEN}你拔腿施展轻功，成功摆脱敌人！{Color.RESET}")
                    p_statuses.pop("shield", None)
                    player.save_to_file()
                    return
                else:
                    print(f"{Color.RED}逃跑失败，被对方一把拦住去路！{Color.RESET}")
            elif act == "3":
                from actions import apply_consumable
                consumables = [i for i in list(dict.fromkeys(player.inventory)) if ITEMS.get(i, {}).get("type") == "consumable"]
                if not consumables:
                    print("行囊中无可用消耗品。")
                else:
                    for idx, item in enumerate(consumables, 1):
                        print(f"  {idx}. {item}")
                    use_c = input("使用物品序号 (0取消)：").strip()
                    if use_c.isdigit() and 0 < int(use_c) <= len(consumables):
                        apply_consumable(player, consumables[int(use_c) - 1])
            elif act == "2":
                avail = [s for s in SKILLS.get(player.sect, SKILLS["散人"]) if player.level >= s["level"]]
                for idx, sk in enumerate(avail, 1):
                    print(f"  {idx}. {sk['name']} (耗内 {sk['mp_cost']} / 威力 {int(sk['power']*100)}%)")
                sk_c = input("选择招式序号 (0取消)：").strip()
                if sk_c.isdigit() and 0 < int(sk_c) <= len(avail):
                    sk = avail[int(sk_c) - 1]
                    if player.mp >= sk["mp_cost"]:
                        player.mp -= sk["mp_cost"]
                        dmg = max(1, int(player.get_total_atk() * sk["power"] - e_def))
                        e_hp = max(0, e_hp - dmg)
                        print(f"{Color.YELLOW}你一式【{sk['name']}】轰出，造成 {dmg} 点伤害！{Color.RESET}")
                    else:
                        dmg = max(1, int(player.get_total_atk() - e_def))
                        e_hp = max(0, e_hp - dmg)
                        print(f"内力不足，改为普通攻击，造成 {dmg} 点伤害！")
            else:
                dmg = max(1, int(player.get_total_atk() - e_def))
                e_hp = max(0, e_hp - dmg)
                print(f"你挥舞兵刃发起攻击，造成 {dmg} 点伤害！")

        if e_hp <= 0:
            print(f"\n{Color.BRIGHT_GREEN}你击败了【{enemy_name}】！{Color.RESET}")
            p_statuses.pop("shield", None)
            player.gain_exp(e_data.get("exp", 10))
            player.gold += e_data.get("gold", 5)
            player.update_quest_progress(enemy_name)
            for drop in e_data.get("drops", []):
                if random.random() < drop["chance"]:
                    player.inventory.append(drop["item"])
                    print(f"{Color.GREEN}搜刮战利品，获得了【{drop['item']}】！{Color.RESET}")
            player.save_to_file()
            return

        # 敌人回合
        if not e_stun:
            e_skill = pick_enemy_skill(e_data)
            from engine import add_status
            if e_skill:
                p_pwr = e_skill.get("power", 1.2)
                raw_dmg = max(1, int(e_atk * p_pwr - player.get_total_defense()))
                print(f"{Color.RED}{enemy_name} 施展出技能【{e_skill['name']}】！{Color.RESET}")
                dmg = apply_shield(p_statuses, raw_dmg)
                if dmg > 0:
                    player.hp = max(0, player.hp - dmg)
                    print(f"技能对你造成了 {Color.RED}{dmg}{Color.RESET} 点伤害！")
                if "effect" in e_skill:
                    add_status(p_statuses, e_skill["effect"], e_skill.get("turns", 2), e_skill.get("value", 3))
            else:
                raw_dmg = max(1, int(e_atk - player.get_total_defense()))
                dmg = apply_shield(p_statuses, raw_dmg)
                if dmg > 0:
                    player.hp = max(0, player.hp - dmg)
                    print(f"{enemy_name} 发起攻击，对你造成 {dmg} 点伤害！")

        battle_pause(0.5)

    if player.hp <= 0:
        print(f"\n{Color.BRIGHT_RED}你重伤倒地，晕厥过去……（已被热心村民抬回古庙养伤）{Color.RESET}")
        player.hp = int(player.max_hp * 0.5)
        player.location = "temple"
        from engine import clear_statuses
        clear_statuses()
        player.save_to_file()


def handle_attack(player, args):
    room = ROOMS.get(player.location, {})
    enemies = room.get("enemies", [])
    npcs = room.get("npcs", [])

    if not args:
        if enemies:
            combat(player, enemies[0])
        else:
            print("这里没有可以攻击的敌对目标。")
        return

    target = args[0]
    for e in enemies:
        if target in e:
            combat(player, e)
            return

    for n in npcs:
        if target in n:
            print(f"{Color.YELLOW}【{n}】并非可战之敌，不可胡乱出手！{Color.RESET}")
            return

    print(f"未在此处找到目标【{target}】。")