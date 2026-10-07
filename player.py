# -*- coding: utf-8 -*-
"""
player.py - 玩家类、属性计算、经验成长与存档持久化
"""

import os
import json
from engine import SAVE_PATH, SAVE_VERSION, LEGACY_LOCATION_MAP, ROOMS, ITEMS, QUESTS, Color, clear_statuses


class Player:
    def __init__(self, name="无名侠客", sect="散人"):
        self.name = name
        self.sect = sect
        self.level = 1
        self.exp = 0
        self.exp_to_level = 50
        self.hp = 100
        self.max_hp = 100
        self.mp = 50
        self.max_mp = 50
        self.atk = 10
        self.defense = 5
        self.gold = 50
        self.inventory = ["疗伤药", "铁矿石", "草药"]
        self.equipment = {"weapon": "木剑", "armor": "布衣"}
        self.equip_enhance = {"weapon": 0, "armor": 0}
        self.location = "village_gate"

        self.active_quests = {}
        self.completed_quests = []

        if sect == "少林":
            self.max_hp += 20; self.hp += 20; self.defense += 3
        elif sect == "武当":
            self.max_mp += 20; self.mp += 20; self.atk += 2
        elif sect == "华山":
            self.atk += 5

    def get_total_atk(self):
        w_name = self.equipment.get("weapon")
        base = ITEMS.get(w_name, {}).get("atk", 0) if w_name else 0
        enhance_bonus = self.equip_enhance.get("weapon", 0) * 3
        return self.atk + base + enhance_bonus

    def get_total_defense(self):
        a_name = self.equipment.get("armor")
        base = ITEMS.get(a_name, {}).get("defense", 0) if a_name else 0
        enhance_bonus = self.equip_enhance.get("armor", 0) * 2
        return self.defense + base + enhance_bonus

    def gain_exp(self, amount):
        self.exp += amount
        print(f"{Color.GREEN}获得了 {amount} 点经验。{Color.RESET}")
        while self.exp >= self.exp_to_level:
            self.exp -= self.exp_to_level
            self.level += 1
            self.max_hp += 15; self.hp = self.max_hp
            self.max_mp += 10; self.mp = self.max_mp
            self.atk += 3; self.defense += 2
            self.exp_to_level = int(self.exp_to_level * 1.5)
            print(f"\n{Color.BRIGHT_YELLOW}【功力大进！】等级提升到了 {self.level} 级！{Color.RESET}")

    def update_quest_progress(self, target_name):
        for q_name in list(self.active_quests.keys()):
            q_info = QUESTS.get(q_name, {})
            if q_info.get("target_name") == target_name:
                self.active_quests[q_name] += 1
                req = q_info.get("required_cnt", 1)
                curr = self.active_quests[q_name]
                print(f"{Color.BRIGHT_YELLOW}[任务更新] 【{q_name}】进度：({curr}/{req}){Color.RESET}")

    def save_to_file(self, filename=SAVE_PATH):
        save_data = {
            "version": SAVE_VERSION,
            "name": self.name,
            "sect": self.sect,
            "level": self.level,
            "exp": self.exp,
            "exp_to_level": self.exp_to_level,
            "hp": self.hp,
            "max_hp": self.max_hp,
            "mp": self.mp,
            "max_mp": self.max_mp,
            "atk": self.atk,
            "defense": self.defense,
            "gold": self.gold,
            "inventory": self.inventory,
            "equipment": self.equipment,
            "equip_enhance": self.equip_enhance,
            "location": self.location,
            "active_quests": self.active_quests,
            "completed_quests": self.completed_quests
        }
        try:
            os.makedirs(os.path.dirname(filename), exist_ok=True)
            with open(filename, "w", encoding="utf-8") as f:
                json.dump(save_data, f, ensure_ascii=False, indent=2)
            print(f"{Color.BRIGHT_GREEN}[存档成功] 游戏进度已保存到 {filename}{Color.RESET}")
            return True
        except Exception as e:
            print(f"{Color.RED}[存档失败] 保存失败: {e}{Color.RESET}")
            return False

    @classmethod
    def load_from_file(cls, filename=SAVE_PATH):
        if not os.path.exists(filename):
            print(f"{Color.YELLOW}未找到存档文件 {filename}。{Color.RESET}")
            return None
        try:
            with open(filename, "r", encoding="utf-8") as f:
                data = json.load(f)
            p = cls(data.get("name", "无名侠客"), data.get("sect", "散人"))
            p.level = data.get("level", 1)
            p.exp = data.get("exp", 0)
            p.exp_to_level = data.get("exp_to_level", 50)
            p.hp = data.get("hp", 100)
            p.max_hp = data.get("max_hp", 100)
            p.mp = data.get("mp", 50)
            p.max_mp = data.get("max_mp", 50)
            p.atk = data.get("atk", 10)
            p.defense = data.get("defense", 5)
            p.gold = data.get("gold", 50)
            p.inventory = data.get("inventory", [])
            p.equipment = data.get("equipment", {"weapon": None, "armor": None})
            p.equip_enhance = data.get("equip_enhance", {"weapon": 0, "armor": 0})

            raw_loc = data.get("location", "village_gate")
            mapped_loc = LEGACY_LOCATION_MAP.get(raw_loc, raw_loc)
            if mapped_loc not in ROOMS:
                mapped_loc = "village_gate"
            p.location = mapped_loc

            p.active_quests = data.get("active_quests", {})
            p.completed_quests = data.get("completed_quests", [])

            clear_statuses()
            print(f"{Color.BRIGHT_GREEN}[读档成功] 欢迎回来，{p.name}少侠！（存档版本 v{data.get('version', 1)}）{Color.RESET}")
            return p
        except Exception as e:
            print(f"{Color.RED}[读档失败] 文件损毁: {e}{Color.RESET}")
            return None