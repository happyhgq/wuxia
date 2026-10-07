# -*- coding: utf-8 -*-
"""
actions.py - 观察、交谈、任务、交易、装备与打铁铺强化
"""

import random
from collections import Counter
from engine import ROOMS, NPCS, ITEMS, QUESTS, Color, add_status, p_statuses_global


def look(player, args=None):
    room = ROOMS.get(player.location, ROOMS["village_gate"])

    if not args:
        print(f"\n{Color.BRIGHT_CYAN}【{room['name']}】{Color.RESET}")
        print(room["desc"])
        if room.get("exits"):
            print(f"{Color.YELLOW}出口：{', '.join(room['exits'].keys())}{Color.RESET}")
        if room.get("npcs"):
            print(f"人物：{Color.CYAN}{', '.join(room['npcs'])}{Color.RESET}")
        if room.get("enemies"):
            print(f"{Color.RED}出没的威胁：{', '.join(room['enemies'])}{Color.RESET}")
        return

    target = args[0]

    for npc_name in room.get("npcs", []):
        if target in npc_name or npc_name in target:
            npc_data = NPCS.get(npc_name, {})
            title = npc_data.get("title", npc_name)
            desc = npc_data.get("desc", "看起来普普通通，没什么特别的。")
            print(f"\n{Color.BRIGHT_YELLOW}【{title}】{Color.RESET}")
            print(f"{Color.CYAN}{desc}{Color.RESET}")
            if "shop" in npc_data:
                print(f"{Color.GREEN}提示：可以向其购买物品（输入 shop 查看货架）。{Color.RESET}")
            if npc_data.get("quests"):
                print(f"{Color.BRIGHT_YELLOW}提示：似乎有任务相托（输入 talk {npc_name} 交谈）。{Color.RESET}")
            return

    for enemy_name in room.get("enemies", []):
        if target in enemy_name or enemy_name in target:
            e_data = ROOMS.get("enemies", {}).get(enemy_name, {}) # 兼容
            from engine import ENEMIES
            e_data = ENEMIES.get(enemy_name, {})
            hp = e_data.get("hp", 0)
            atk = e_data.get("atk", 0)
            defense = e_data.get("defense", 0)
            print(f"\n{Color.BRIGHT_RED}【{enemy_name}】{Color.RESET}")
            print(f"眼神不善，充满敌意！属性评估：气血 {hp} | 攻击 {atk} | 防御 {defense}")
            print(f"{Color.RED}提示：输入 kill {enemy_name} 即可对其发起攻击。{Color.RESET}")
            return

    all_items = player.inventory + list(player.equipment.values())
    for item_name in set(all_items):
        if item_name and (target in item_name or item_name in target):
            i_data = ITEMS.get(item_name, {})
            i_type = i_data.get("type", "普通物品")
            type_cn = {"weapon": "兵刃", "armor": "防具", "consumable": "消耗药剂", "material": "材料"}.get(i_type, i_type)
            desc = i_data.get("desc", "暂无说明。")
            price = i_data.get("price", 0)
            print(f"\n{Color.BRIGHT_GREEN}【{item_name}】({type_cn}){Color.RESET}")
            print(f"描述：{desc}")
            print(f"价值：{price} 两银子")
            return

    print(f"周围和行囊里并没有找到与【{target}】相关的目标。")


def handle_talk_and_ask(player, args):
    room = ROOMS.get(player.location, {})
    npcs_in_room = room.get("npcs", [])

    if not npcs_in_room:
        print("此地空无一人，并无可以交谈的对象。")
        return

    target_npc = npcs_in_room[0]
    topic = None

    if args:
        matched = False
        for name in npcs_in_room:
            if args[0] in name:
                target_npc = name
                matched = True
                break

        if matched and len(args) > 1:
            topic = args[1]
        elif not matched:
            topic = args[0]

    npc_data = NPCS.get(target_npc, {})
    print(f"\n{Color.BRIGHT_YELLOW}【{npc_data.get('title', target_npc)}】{Color.RESET}")

    if topic:
        info_dict = npc_data.get("info", {})
        matched_info = None
        for key_phrase, val_text in info_dict.items():
            if topic in key_phrase or key_phrase in topic:
                matched_info = val_text
                break

        if matched_info:
            print(f"{target_npc} 压低声音回答说：“{Color.YELLOW}{matched_info}{Color.RESET}”")
        else:
            print(f"{target_npc} 摇了摇头：“关于‘{topic}’，老夫并不知道什么信息。”")
        return

    print(f"{Color.CYAN}{npc_data.get('desc', '一言不发。')}{Color.RESET}")
    dialogues = npc_data.get("dialogue", ["……"])
    line = random.choice(dialogues) if isinstance(dialogues, list) else dialogues
    print(f"\n{target_npc} 说道：“{Color.GREEN}{line}{Color.RESET}”")

    available_q = npc_data.get("quests", [])
    for q_name in available_q:
        if q_name in player.completed_quests:
            continue
        q_info = QUESTS.get(q_name, {})
        if q_name not in player.active_quests:
            print(f"\n{Color.BRIGHT_YELLOW}提示：{target_npc} 似乎有任务相托！输入 jiequ {q_name} 即可接取。{Color.RESET}")
        else:
            curr = player.active_quests[q_name]
            req = q_info.get("required_cnt", 1)
            if curr >= req:
                print(f"\n{Color.BRIGHT_GREEN}提示：你已完成【{q_name}】！输入 jiaofu {q_name} 交付任务。{Color.RESET}")


def handle_quest(player, cmd, args):
    if cmd in ("quests", "renwu"):
        print(f"\n{Color.CYAN}========== 当前任务列表 =========={Color.RESET}")
        if not player.active_quests:
            print("目前没有正在进行中的任务。")
        for q_name, progress in player.active_quests.items():
            q_info = QUESTS.get(q_name, {})
            req = q_info.get("required_cnt", 1)
            print(f"- {Color.YELLOW}{q_name}{Color.RESET}：({progress}/{req}) - {q_info.get('desc', '')}")
        print(f"{Color.CYAN}----------------------------------{Color.RESET}")

    elif cmd == "jiequ":
        if not args:
            print("请输入要接取的任务名称（格式：jiequ <任务名>）。")
            return
        q_name = args[0]
        if q_name not in QUESTS:
            print(f"不存在名为【{q_name}】的任务。")
            return
        if q_name in player.active_quests:
            print("你已经接取了该任务！")
            return
        if q_name in player.completed_quests:
            print("该任务你已经完成过了！")
            return
        player.active_quests[q_name] = 0
        print(f"{Color.BRIGHT_GREEN}成功接取任务：【{q_name}】！{Color.RESET}")

    elif cmd == "jiaofu":
        if not args:
            print("请输入要交付的任务名称（格式：jiaofu <任务名>）。")
            return
        q_name = args[0]
        if q_name not in player.active_quests:
            print("你未接取该任务！")
            return
        q_info = QUESTS.get(q_name, {})
        req = q_info.get("required_cnt", 1)
        if player.active_quests[q_name] < req:
            print(f"{Color.RED}任务目标未达成，无法交付！{Color.RESET}")
            return

        del player.active_quests[q_name]
        player.completed_quests.append(q_name)
        reward = q_info.get("reward", {})
        print(f"\n{Color.BRIGHT_YELLOW}🎉 恭喜完成任务【{q_name}】！获得奖励：{Color.RESET}")
        if "exp" in reward: player.gain_exp(reward["exp"])
        if "gold" in reward:
            player.gold += reward["gold"]
            print(f"银两 +{reward['gold']}")
        if "item" in reward:
            player.inventory.append(reward["item"])
            print(f"获得了物品：【{reward['item']}】！")
        player.save_to_file()


def apply_consumable(player, item_name):
    info = ITEMS.get(item_name, {})
    if info.get("type") != "consumable":
        print(f"【{item_name}】并非可直接使用的消耗道具。")
        return False

    player.inventory.remove(item_name)
    eff = info.get("effect", {})

    from engine import STATUS_EFFECTS
    if "hp" in eff:
        actual_gain = min(player.max_hp, player.hp + eff["hp"]) - player.hp
        player.hp += actual_gain
        print(f"{Color.GREEN}服下了【{item_name}】，实际恢复了 {actual_gain} 点气血！{Color.RESET}")
    if "mp" in eff:
        actual_gain = min(player.max_mp, player.mp + eff["mp"]) - player.mp
        player.mp += actual_gain
        print(f"{Color.BLUE}服下了【{item_name}】，实际恢复了 {actual_gain} 点内力！{Color.RESET}")
    if "status" in eff:
        st = eff["status"]
        st_name = st.get("name")
        if st_name:
            cn_name = STATUS_EFFECTS.get(st_name, {}).get("name", st_name)
            add_status(p_statuses_global, st_name, st.get("turns", 1), st.get("value", 0))
            print(f"{Color.CYAN}服下了【{item_name}】，凝聚起了【{cn_name}】效果！{Color.RESET}")
    return True


def handle_trading(player, cmd, args):
    room = ROOMS.get(player.location, {})
    npcs_in_room = room.get("npcs", [])

    trader_npc = None
    for n in npcs_in_room:
        if NPCS.get(n, {}).get("type") == "trader" or "shop" in NPCS.get(n, {}):
            trader_npc = n
            break

    if not trader_npc:
        print("此处没有可以交易的商贾或店家。")
        return

    shop_items = NPCS[trader_npc].get("shop", [])

    if cmd in ("shop", "list"):
        print(f"\n{Color.YELLOW}======== {trader_npc} 的店铺货架 ========{Color.RESET}")
        for idx, item in enumerate(shop_items, 1):
            info = ITEMS.get(item, {})
            print(f"  {idx}. {item} - {info.get('price', 0)} 两银子 ({info.get('desc', '')})")
        print(f"手头银两：{player.gold} 两")
    elif cmd == "buy":
        if not args:
            print("请指定要购买的物品名称（如 buy 金创药）。")
            return
        item_name = args[0]
        matching = [i for i in shop_items if item_name in i]
        if not matching:
            print(f"店家表示这里并不出售【{item_name}】。")
            return
        target = matching[0]
        price = ITEMS.get(target, {}).get("price", 0)
        if player.gold >= price:
            player.gold -= price
            player.inventory.append(target)
            print(f"{Color.GREEN}花费 {price} 两银子，购买了【{target}】！{Color.RESET}")
        else:
            print(f"{Color.RED}银两不足，无法购买！{Color.RESET}")
    elif cmd == "sell":
        if not args:
            print("请指定要出售的物品名称（如 sell 野猪肉）。")
            return
        item_name = args[0]
        matching = [i for i in player.inventory if item_name in i]
        if not matching:
            print(f"你的行囊中没有【{item_name}】。")
            return
        target = matching[0]
        price = max(1, int(ITEMS.get(target, {}).get("price", 10) * 0.5))
        player.inventory.remove(target)
        player.gold += price
        print(f"{Color.GREEN}将【{target}】卖给了商家，换得 {price} 两银子！{Color.RESET}")


def handle_equipment_and_items(player, cmd, args):
    if not args:
        print(f"请指定物品名称（如 {cmd} 精铁剑）。")
        return
    item_input = args[0]

    if cmd in ("wield", "wear"):
        matching = [i for i in player.inventory if item_input in i]
        if not matching:
            print(f"你的背包里没有【{item_input}】。")
            return
        item_name = matching[0]
        item_type = ITEMS.get(item_name, {}).get("type")

        if cmd == "wield" and item_type == "weapon":
            old = player.equipment.get("weapon")
            if old: player.inventory.append(old)
            player.equipment["weapon"] = item_name
            player.inventory.remove(item_name)
            player.equip_enhance["weapon"] = 0
            print(f"{Color.GREEN}装备了武器：【{item_name}】！{Color.RESET}")
        elif cmd == "wear" and item_type == "armor":
            old = player.equipment.get("armor")
            if old: player.inventory.append(old)
            player.equipment["armor"] = item_name
            player.inventory.remove(item_name)
            player.equip_enhance["armor"] = 0
            print(f"{Color.GREEN}穿上了防具：【{item_name}】！{Color.RESET}")
        else:
            print(f"{Color.RED}【{item_name}】无法进行此类装备！{Color.RESET}")

    elif cmd == "use":
        matching = [i for i in player.inventory if item_input in i]
        if not matching:
            print(f"行囊里没有【{item_input}】。")
            return
        apply_consumable(player, matching[0])


def handle_forge(player, args):
    if player.location != "blacksmith":
        print("只有在打铁铺才可以强化装备！")
        return

    print(f"\n{Color.BRIGHT_YELLOW}================ 铁匠打造炉 ================{Color.RESET}")
    w_name = player.equipment.get("weapon") or "无"
    a_name = player.equipment.get("armor") or "无"
    w_lv = player.equip_enhance.get("weapon", 0)
    a_lv = player.equip_enhance.get("armor", 0)
    ore_cnt = player.inventory.count("铁矿石")

    print(f"当前兵刃：{Color.GREEN}{w_name} (+{w_lv}){Color.RESET}")
    print(f"当前防具：{Color.GREEN}{a_name} (+{a_lv}){Color.RESET}")
    print(f"拥有铁矿石：{Color.YELLOW}{ore_cnt} 块{Color.RESET}  银两：{Color.YELLOW}{player.gold} 两{Color.RESET}")
    print("--------------------------------------------")
    print("1. 强化兵刃（消耗 1 块铁矿石 + 30 银两）")
    print("2. 强化防具（消耗 1 块铁矿石 + 30 银两）")
    print("0. 离开打造炉")

    choice = input("请选择打造项目 (0-2)：").strip()
    if choice == "1":
        slot_key, target_name = "weapon", w_name
    elif choice == "2":
        slot_key, target_name = "armor", a_name
    else:
        return

    if target_name == "无":
        print(f"{Color.RED}你身上并未装备对应的{'兵刃' if slot_key=='weapon' else '防具'}！{Color.RESET}")
        return

    if player.equip_enhance.get(slot_key, 0) >= 5:
        print(f"{Color.RED}该装备已经强化至最高等级 (+5)！{Color.RESET}")
        return

    if ore_cnt < 1 or player.gold < 30:
        print(f"{Color.RED}强化材料不足！需要 1 块铁矿石及 30 银两。{Color.RESET}")
        return

    player.inventory.remove("铁矿石")
    player.gold -= 30
    player.equip_enhance[slot_key] += 1
    new_lv = player.equip_enhance[slot_key]
    print(f"\n{Color.BRIGHT_GREEN}锤打叮当，火花四溅！你的【{target_name}】成功强化至 +{new_lv}！{Color.RESET}")
    player.save_to_file()