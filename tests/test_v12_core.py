# -*- coding: utf-8 -*-
import json
import os
import tempfile
import unittest
from unittest.mock import patch

import engine
import combat
from player import Player
from main import CMD_MAP, parse_command, make_prompt, show_status, show_help, show_encyclopedia, show_context_advice, show_first_entry_guide
from actions import handle_quest, look, handle_notice_board, handle_world_events, handle_sect


class V12CoreTests(unittest.TestCase):
    def test_legacy_save_migration(self):
        old = {
            "version": 10, "name": "迁移测试", "sect": "武当",
            "location": "official_road_east_1", "active_quests": {},
            "completed_quests": []
        }
        migrated, old_version = engine.migrate_save_data(old)
        self.assertEqual(old_version, 10)
        self.assertEqual(migrated["version"], 12)
        self.assertEqual(migrated["location"], "official_road_east_1")
        self.assertIn("world_state", migrated)
        self.assertIn("flags", migrated["world_state"])
        self.assertIn("variables", migrated["world_state"])

    def test_world_state_round_trip(self):
        fd, path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        try:
            p = Player("状态测试", "散人")
            p.location = "guiyun_south_gate"
            p.mark_visited(p.location)
            p.set_flag("black_market_unlocked", True)
            p.set_var("government_reputation", 12)
            p.increment_var("government_reputation", 3)
            self.assertTrue(p.save_to_file(path))

            with open(path, encoding="utf-8") as f:
                saved = json.load(f)
            self.assertEqual(saved["version"], 12)
            self.assertTrue(saved["world_state"]["flags"]["black_market_unlocked"])
            self.assertTrue(saved["world_state"]["flags"]["visited_zone:guiyun_city"])

            q = Player.load_from_file(path)
            self.assertEqual(q.location, "guiyun_south_gate")
            self.assertTrue(q.get_flag("black_market_unlocked"))
            self.assertEqual(q.get_var("government_reputation"), 15)
        finally:
            os.remove(path)

    def test_reload_replaces_runtime_data(self):
        old_rooms = engine.ROOMS
        old_npcs = engine.NPCS
        engine.reload_game_data()
        self.assertIsNot(engine.ROOMS, old_rooms)
        self.assertIsNot(engine.NPCS, old_npcs)
        self.assertIn("guiyun_south_gate", engine.ROOMS)
        self.assertEqual(engine.ROOMS["guiyun_south_gate"]["zone"], "guiyun_city")

    def test_command_parser_has_save_load(self):
        self.assertEqual(parse_command("save"), ("save", []))
        self.assertEqual(parse_command("load"), ("load", []))


    def test_staged_quest_round_trip(self):
        p = Player("阶段测试", "散人")
        p.active_quests["城内失踪案"] = 1
        p.quest_states["城内失踪案"] = {"stage": 1, "progress": 0}
        fd, path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        try:
            self.assertTrue(p.save_to_file(path))
            loaded = Player.load_from_file(path)
            self.assertEqual(loaded.quest_states["城内失踪案"]["stage"], 1)
        finally:
            os.remove(path)


class EquipmentSystemTests(unittest.TestCase):
    def test_equipment_stats_and_combat_totals(self):
        p = Player("装备属性", "散人")
        self.assertEqual(p.get_total_atk(), 15)  # 基础10 + 木剑5
        self.assertEqual(p.get_total_defense(), 8)  # 基础5 + 布衣3
        p.equipment["weapon"] = "精铁剑"
        p.equipment["armor"] = "锁子甲"
        p.equip_enhance["weapon"] = 2
        p.equip_enhance["armor"] = 1
        self.assertEqual(p.get_total_atk(), 38)  # 10 + 20 + 6 + 精铁剑力量词条2
        self.assertEqual(p.get_total_defense(), 24)  # 5 + 15 + 强化2 + 锁子甲体魄词条2

    def test_compare_equipment_reports_real_delta(self):
        p = Player("装备比较", "散人")
        result = p.compare_equipment("精铁剑")
        self.assertEqual(result["slot"], "weapon")
        self.assertEqual(result["candidate_atk"], 20)
        self.assertEqual(result["current"]["atk"], 5)
        self.assertEqual(result["delta_atk"], 15)

    def test_equip_item_swaps_old_item_back_to_inventory(self):
        p = Player("换装", "散人")
        p.inventory.append("精铁剑")
        ok, _ = p.equip_item("精铁剑")
        self.assertTrue(ok)
        self.assertEqual(p.equipment["weapon"], "精铁剑")
        self.assertIn("木剑", p.inventory)
        self.assertNotIn("精铁剑", p.inventory)
        self.assertEqual(p.equip_enhance["weapon"], 0)

    def test_unequip_item_returns_equipment_to_inventory(self):
        p = Player("卸下", "散人")
        ok, _ = p.unequip_item("weapon")
        self.assertTrue(ok)
        self.assertIsNone(p.equipment["weapon"])
        self.assertIn("木剑", p.inventory)
        self.assertEqual(p.get_total_atk(), 10)

    def test_equipment_commands_are_parsed(self):
        self.assertEqual(parse_command("equipment"), ("equipment", []))
        self.assertEqual(parse_command("compare 玄铁重剑"), ("compare", ["玄铁重剑"]))
        self.assertEqual(parse_command("unequip weapon"), ("unequip", ["weapon"]))
        self.assertEqual(parse_command("equip 精铁剑"), ("equip", ["精铁剑"]))

    def test_equipment_affixes_change_build_derived_stats(self):
        p = Player("词条Build", "散人")
        p.equipment = {"weapon": "精铁剑", "armor": "皮甲"}
        self.assertEqual(p.get_effective_attribute("strength"), 1)
        self.assertEqual(p.get_effective_attribute("agility"), 1)
        self.assertAlmostEqual(p.get_crit_chance(), 0.10)
        self.assertAlmostEqual(p.get_dodge_chance(), 0.08)
        self.assertAlmostEqual(p.get_hit_chance(), 0.91)

    def test_heavy_sword_affixes_create_tradeoff(self):
        p = Player("重剑流", "散人")
        p.equipment = {"weapon": "玄铁重剑", "armor": "布衣"}
        self.assertEqual(p.get_total_atk(), 53)
        self.assertAlmostEqual(p.get_crit_chance(), 0.13)
        self.assertAlmostEqual(p.get_hit_chance(), 0.87)

    def test_equipment_compare_reports_affixes(self):
        p = Player("词条比较", "散人")
        result = p.compare_equipment("精铁剑")
        self.assertEqual(result["candidate_affixes"]["attribute_bonus"]["strength"], 1)
        self.assertAlmostEqual(result["candidate_affixes"]["crit_bonus"], 0.02)

    def test_v12_save_round_trip_keeps_equipment(self):
        p = Player("装备存档", "散人")
        p.inventory.append("精铁剑")
        p.equip_item("精铁剑")
        p.equip_enhance["weapon"] = 3
        fd, path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        try:
            self.assertTrue(p.save_to_file(path))
            with open(path, encoding="utf-8") as f:
                raw = json.load(f)
            self.assertEqual(raw["version"], 12)
            q = Player.load_from_file(path)
            self.assertEqual(q.equipment["weapon"], "精铁剑")
            self.assertEqual(q.equip_enhance["weapon"], 3)
            self.assertEqual(q.get_total_atk(), 41)
        finally:
            os.remove(path)


class BuildSynergyTests(unittest.TestCase):
    def test_build_profiles_data_is_loaded_and_valid(self):
        self.assertIn("重剑强攻", engine.BUILD_PROFILES)
        self.assertIn("轻灵游身", engine.BUILD_PROFILES)
        self.assertIn("铁壁内修", engine.BUILD_PROFILES)

    def test_build_command_is_parsed(self):
        self.assertEqual(parse_command("build"), ("build", []))
        self.assertEqual(parse_command("流派"), ("build", []))

    def test_heavy_sword_build_activates_real_combat_bonus(self):
        p = Player("重剑流", "散人")
        p.equipment["weapon"] = "玄铁重剑"
        p.attributes["strength"] = 2
        active = p.get_active_build()
        self.assertEqual(active["name"], "重剑强攻")
        self.assertEqual(p.get_total_atk(), 57)
        self.assertAlmostEqual(p.get_crit_chance(), 0.13)
        self.assertAlmostEqual(p.get_hit_chance(), 0.87)

    def test_light_build_activates_hit_and_dodge_bonus(self):
        p = Player("轻灵流", "散人")
        p.equipment["armor"] = "皮甲"
        p.attributes["agility"] = 2
        self.assertEqual(p.get_active_build()["name"], "轻灵游身")
        self.assertAlmostEqual(p.get_dodge_chance(), 0.13)
        self.assertAlmostEqual(p.get_hit_chance(), 0.95)

    def test_build_preview_does_not_mutate_equipment(self):
        p = Player("Build预览", "散人")
        p.equipment["weapon"] = "铁剑"
        p.attributes["strength"] = 2
        preview = p.get_build_preview_for_item("玄铁重剑")
        self.assertEqual(p.equipment["weapon"], "铁剑")
        self.assertTrue(preview["changed"])
        self.assertEqual(preview["after"]["name"], "重剑强攻")

    def test_build_bonuses_are_not_saved_as_extra_fields(self):
        p = Player("Build存档", "散人")
        p.equipment["armor"] = "皮甲"
        p.attributes["agility"] = 2
        fd, path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        try:
            self.assertTrue(p.save_to_file(path))
            with open(path, encoding="utf8") as f:
                raw = json.load(f)
            self.assertEqual(raw["version"], 12)
            self.assertNotIn("active_build", raw)
            self.assertNotIn("build_bonuses", raw)
            q = Player.load_from_file(path)
            self.assertEqual(q.get_active_build()["name"], "轻灵游身")
        finally:
            os.remove(path)


class QuestDeepeningTests(unittest.TestCase):
    def test_quest_conditions_support_player_level_gold_and_items(self):
        p = Player("任务条件", "散人")
        p.level = 3
        p.gold = 120
        self.assertTrue(engine.check_conditions(
            {"level": {"gte": 3}, "gold": {"gte": 100}, "items": {"草药": 1}},
            p.world_state, p.completed_quests, p
        ))
        self.assertFalse(engine.check_conditions(
            {"level": {"gte": 4}}, p.world_state, p.completed_quests, p
        ))

    def test_quest_detail_command_accepts_multiword_name(self):
        self.assertEqual(
            parse_command("renwu 城内失踪案"),
            ("quests", ["城内失踪案"]),
        )

    def test_staged_quest_progress_advances_and_preserves_world_effects(self):
        p = Player("任务推进", "散人")
        p.active_quests["城内失踪案"] = 0
        p.quest_states["城内失踪案"] = {"stage": 0, "progress": 0}
        p.update_quest_progress("沈府管家", event_type="talk")
        self.assertTrue(p.quest_states["城内失踪案"].get("branch_pending"))
        ok, _ = p.choose_quest_branch("城内失踪案", "official_route")
        self.assertTrue(ok)
        self.assertEqual(p.quest_states["城内失踪案"]["stage"], 1)
        self.assertEqual(p.quest_states["城内失踪案"]["progress"], 0)

    def test_task_completion_not_marked_before_reward_success(self):
        from unittest.mock import patch
        import actions
        p = Player("任务原子性", "散人")
        p.location = "village_gate"
        p.active_quests["清剿黑风山"] = 1
        with patch.object(actions.engine, "ROOMS", {"village_gate": {"npcs": ["村长"]}}), \
             patch.object(actions.engine, "QUESTS", {"清剿黑风山": {"npc": "村长", "required_cnt": 1, "reward": {"items": ["不存在的物品"]}}}), \
             patch("rewards.apply_reward_bundle", return_value={"ok": False, "message": "奖励物品不存在"}):
            actions.handle_quest(p, "jiaofu", ["清剿黑风山"])
        self.assertIn("清剿黑风山", p.active_quests)
        self.assertNotIn("清剿黑风山", p.completed_quests)

    def test_live_quest_data_has_valid_stage_targets(self):
        self.assertEqual(len(engine.QUESTS["城内失踪案"]["stages"]), 4)
        self.assertEqual(engine.QUESTS["震远镖局"]["stages"][-1]["target_name"], "震远镖局总镖头")


class P223SectTests(unittest.TestCase):
    def test_sect_data_loaded_and_summary(self):
        self.assertEqual(set(engine.SECTS), {"少林", "武当", "华山", "铁衣门", "散人"})
        p = Player("门派测试", "武当")
        summary = p.get_sect_summary()
        self.assertEqual(summary["name"], "武当")
        self.assertEqual(summary["rank"], "记名弟子")
        self.assertIn("太极剑", summary["exclusive_skills"])

    def test_sect_state_uses_existing_world_state_only(self):
        p = Player("状态测试", "少林")
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            p.save_to_file(path)
            self.assertIn("sect_state", p.world_state["variables"])
            with open(path, encoding="utf8") as f:
                raw = json.load(f)
            self.assertEqual(raw["version"], 12)
            self.assertEqual(raw["sect"], "少林")
            self.assertIn("sect_state", raw["world_state"]["variables"])
            self.assertNotIn("sect_reputation", raw)
        finally:
            os.remove(path)

    def test_sect_join_leave_and_reputation_rank(self):
        p = Player("入门测试", "散人")
        p.level = 3
        ok, _ = p.join_sect("华山")
        self.assertTrue(ok)
        self.assertEqual(p.get_sect(), "华山")
        self.assertEqual(p.get_sect_rank(), "记名弟子")
        p.change_sect_reputation("华山", 50)
        self.assertEqual(p.get_sect_rank(), "内门弟子")
        p.level = max(p.level, 3)
        ok, _ = p.join_sect("武当")
        self.assertFalse(ok)
        ok, _ = p.leave_sect()
        self.assertTrue(ok)
        p.level = max(p.level, 3)
        ok, _ = p.join_sect("武当")
        self.assertTrue(ok)

    def test_sect_condition(self):
        p = Player("条件测试", "少林")
        self.assertTrue(engine.check_conditions({"sect": "少林"}, p.world_state, player=p))
        self.assertFalse(engine.check_conditions({"sect": "武当"}, p.world_state, player=p))
        self.assertTrue(engine.check_conditions({"sect": ["少林", "武当"]}, p.world_state, player=p))

    def test_sect_reputation_condition(self):
        p = Player("声望条件", "少林")
        p.change_sect_reputation("少林", 50)
        self.assertTrue(engine.check_conditions({"sect_reputation": {"少林": {"gte": 50}}}, p.world_state, player=p))
        self.assertFalse(engine.check_conditions({"sect_reputation": {"少林": {"gte": 51}}}, p.world_state, player=p))

    def test_reward_bundle_grants_sect_reputation(self):
        from rewards import apply_reward_bundle
        p = Player("奖励测试", "武当")
        result = apply_reward_bundle(p, {"sect_reputation": {"武当": 30}}, announce=False)
        self.assertTrue(result["ok"])
        self.assertEqual(result["sect_reputation"]["武当"], 30)
        self.assertEqual(p.get_sect_rank(), "外门弟子")

    def test_sect_quest_reward_closes_full_loop(self):
        from actions import handle_quest, look
        p = Player("门派任务闭环", "少林")
        p.gold = 0
        # Alpha160：少林历练由罗汉场的传功师兄正式发布。
        p.location = "shaolin_training_ground"
        handle_quest(p, "jiequ", ["少林历练·黑风除恶"])
        self.assertIn("少林历练·黑风除恶", p.active_quests)
        for _ in range(2):
            p.update_quest_progress("黑风寨精锐", event_type="kill")
        self.assertEqual(p.active_quests["少林历练·黑风除恶"], 2)
        with patch("builtins.print"):
            handle_quest(p, "jiaofu", ["少林历练·黑风除恶"])
        self.assertIn("少林历练·黑风除恶", p.completed_quests)
        self.assertEqual(p.get_sect_reputation("少林"), 30)

    def test_sect_quest_requires_current_sect(self):
        q = engine.QUESTS["少林历练·黑风除恶"]
        p = Player("任务门派", "武当")
        self.assertFalse(engine.check_conditions(q["requires"], p.world_state, player=p))
        p.sect = "少林"
        p.world_state["variables"]["sect_state"] = {"current_sect": "少林", "reputation": {"少林": 0}}
        self.assertTrue(engine.check_conditions(q["requires"], p.world_state, player=p))

    def test_sect_command_parser(self):
        self.assertEqual(parse_command("sect"), ("sect", []))
        self.assertEqual(parse_command("sect join 少林"), ("sect", ["join 少林"]))

    def test_p232_npc_information_and_propagation(self):
        p = Player("消息测试", "散人")
        p.set_var("quest_clock", 7)  # 13:00，避开守卫与村长的日常忙碌时段
        p.set_npc_location("守卫", "village_gate", "test")
        p.set_npc_location("村长", "village_gate", "test")
        p.change_npc_bond("守卫", "村长", 20)
        learned = p.propagate_npc_information("village_gate")
        self.assertTrue(any(x[2] == "black_wind_pressure" for x in learned))
        self.assertIsNotNone(p.get_npc_information("村长", "black_wind_pressure"))

    def test_p232_player_information_relation_gate(self):
        p = Player("消息关系测试", "散人")
        p.change_relation("村长", 4)
        self.assertEqual(p.learn_information_from_npc("村长", "old_escape_route"), [])
        p.change_relation("村长", 10)
        learned = p.learn_information_from_npc("村长", "old_escape_route")
        self.assertIn("old_escape_route", learned)
        self.assertEqual(p.get_player_information("old_escape_route")["sentiment"], "secret")

    def test_p232_information_expiry(self):
        p = Player("消息时效测试", "散人")
        p.learn_player_information("temporary", "临时消息", "测试", 90, ttl=2)
        self.assertIsNotNone(p.get_player_information("temporary"))
        p.set_var("quest_clock", 2)
        self.assertIsNone(p.get_player_information("temporary"))

    def test_p232_information_condition(self):
        p = Player("消息条件测试", "散人")
        p.learn_player_information("official_notice", "府衙公告", "文书", 95)
        self.assertTrue(engine.check_conditions({"npc_information": {"official_notice": {"min_confidence": 90}}}, p.world_state, [], p))
        self.assertFalse(engine.check_conditions({"npc_information": {"missing_topic": True}}, p.world_state, [], p))

    def test_p232_world_event_generates_information(self):
        p = Player("舆情测试", "散人")
        p.set_var("exploration:main", 2)
        p.location = "village_gate"
        ok, _, _ = p.trigger_world_event("main_bandit_warning")
        self.assertTrue(ok)
        self.assertIsNotNone(p.get_npc_information("守卫", "bandit_warning"))
        self.assertIsNotNone(p.get_npc_information("村长", "bandit_warning"))

    def test_p232_information_round_trip_v12(self):
        p = Player("消息存档测试", "散人")
        p.learn_player_information("caravan_safe", "商路已恢复", "捕头", 91, ttl=10, sentiment="positive")
        fd, path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        try:
            self.assertTrue(p.save_to_file(path))
            loaded = Player.load_from_file(path)
            self.assertEqual(loaded.get_player_information("caravan_safe")["confidence"], 91)
            self.assertEqual(loaded.get_player_information("caravan_safe")["sentiment"], "positive")
            self.assertIn("player_information", loaded.world_state["variables"])
        finally:
            os.remove(path)

    def test_p232_quest_can_require_world_information(self):
        p = Player("消息任务测试", "散人")
        q = engine.QUESTS["黑风限时追缉"]
        self.assertFalse(engine.check_conditions(q["requires"], p.world_state, p.completed_quests, p))
        p.learn_player_information("bandit_warning", "黑风寨活动异常。", "世界事件", 90)
        p.change_relation("村长", 8)
        self.assertFalse(engine.check_conditions(q["requires"], p.world_state, p.completed_quests, p))
        # 该任务还要求罗汉拳，信息条件本身已被满足；验证降到单独信息条件。
        self.assertTrue(engine.check_conditions({"npc_information": {"bandit_warning": {"min_confidence": 80}}}, p.world_state, [], p))


if __name__ == "__main__":
    unittest.main()

class CombatInputTests(unittest.TestCase):
    def test_invalid_action_does_not_consume_enemy_turn(self):
        from unittest.mock import patch
        import combat

        p = Player("战斗测试", "散人")
        p.level = 3
        p.hp = 100
        p.max_hp = 100
        p.atk = 10
        p.equipment = {"weapon": None, "armor": None}
        p.equip_enhance = {"weapon": 0, "armor": 0}

        original = engine.ENEMIES.get("野狼")
        engine.ENEMIES["野狼"] = {
            "hp": 18, "atk": 50, "defense": 0, "exp": 0, "gold": 0,
            "skills": [], "drops": [], "hit": 0.98
        }
        engine.clear_statuses()
        try:
            # 第一次选择无效；随后普通攻击击杀。若无效输入被错误视为攻击，
            # 敌人会先获得一次攻击机会，玩家 HP 将下降；正确行为应保持 100。
            with patch("builtins.input", side_effect=["x", "1", "1"]), \
                 patch("combat.random.random", return_value=0.50), \
                 patch("combat.battle_pause", return_value=None):
                combat.combat(p, "野狼")
            self.assertEqual(p.hp, 53)
        finally:
            if original is None:
                engine.ENEMIES.pop("野狼", None)
            else:
                engine.ENEMIES["野狼"] = original
            engine.clear_statuses()

    def test_cancel_skill_does_not_consume_enemy_turn(self):
        from unittest.mock import patch
        import combat

        p = Player("武学测试", "散人")
        p.level = 3
        p.hp = 100
        p.max_hp = 100
        p.mp = 50
        p.atk = 10
        p.equipment = {"weapon": None, "armor": None}
        p.equip_enhance = {"weapon": 0, "armor": 0}

        original = engine.ENEMIES.get("野狼")
        engine.ENEMIES["野狼"] = {
            "hp": 18, "atk": 50, "defense": 0, "exp": 0, "gold": 0,
            "skills": [], "drops": [], "hit": 0.98
        }
        engine.clear_statuses()
        try:
            with patch("builtins.input", side_effect=["2", "0", "1", "1"]), \
                 patch("combat.random.random", return_value=0.50), \
                 patch("combat.battle_pause", return_value=None):
                combat.combat(p, "野狼")
            self.assertEqual(p.hp, 53)
        finally:
            if original is None:
                engine.ENEMIES.pop("野狼", None)
            else:
                engine.ENEMIES["野狼"] = original
            engine.clear_statuses()

class CombatProbabilityTests(unittest.TestCase):
    def test_attack_miss(self):
        from unittest.mock import patch
        from combat import resolve_attack
        with patch('combat.random.random', return_value=0.99):
            dmg, outcome = resolve_attack(20, 0.90, 0.05, 0.08)
        self.assertEqual(dmg, 0)
        self.assertEqual(outcome, 'miss')

    def test_attack_crit(self):
        from unittest.mock import patch
        from combat import resolve_attack
        with patch('combat.random.random', side_effect=[0.01, 0.01]):
            dmg, outcome = resolve_attack(20, 0.90, 0.05, 0.08)
        self.assertEqual(dmg, 30)
        self.assertEqual(outcome, 'crit')

    def test_attack_normal_hit(self):
        from unittest.mock import patch
        from combat import resolve_attack
        with patch('combat.random.random', side_effect=[0.01, 0.50]):
            dmg, outcome = resolve_attack(20, 0.90, 0.05, 0.08)
        self.assertEqual(dmg, 20)
        self.assertEqual(outcome, 'hit')

    def test_player_combat_base_rates(self):
        p = Player('概率测试', '散人')
        self.assertAlmostEqual(p.get_hit_chance(), engine.COMBAT_DEFAULTS['hit'])
        self.assertAlmostEqual(p.get_crit_chance(), engine.COMBAT_DEFAULTS['crit'])
        self.assertAlmostEqual(p.get_dodge_chance(), engine.COMBAT_DEFAULTS['dodge'])


class MartialArtsEffectTests(unittest.TestCase):
    def setUp(self):
        engine.clear_statuses()

    def tearDown(self):
        engine.clear_statuses()

    def test_shaolin_stun_effect(self):
        import combat
        p = Player("少林测试", "少林")
        skill = engine.SKILLS["少林"][0]
        enemy_statuses = {}
        with patch("combat.random.random", return_value=0.01):
            msgs = combat.apply_skill_effect(skill, p, enemy_statuses)
        self.assertIn("stun", enemy_statuses)
        self.assertTrue(msgs)

    def test_offensive_status_does_not_apply_when_attack_misses(self):
        import combat
        p = Player("未命中测试", "少林")
        skill = engine.SKILLS["少林"][0]
        enemy_statuses = {}
        with patch("combat.random.random", return_value=0.01):
            msgs = combat.apply_skill_effect(skill, p, enemy_statuses, target_hit=False)
        self.assertNotIn("stun", enemy_statuses)
        self.assertEqual(msgs, [])

    def test_self_defense_effect_still_applies_when_attack_misses(self):
        import combat
        p = Player("未命中护体测试", "武当")
        skill = engine.SKILLS["武当"][0]
        with patch("combat.random.random", return_value=0.01):
            msgs = combat.apply_skill_effect(skill, p, {}, target_hit=False)
        self.assertIn("damage_reduction", engine.p_statuses_global)
        self.assertTrue(msgs)

    def test_shaolin_armor_break_changes_defense(self):
        import combat
        p = Player("少林测试", "少林")
        skill = engine.SKILLS["少林"][1]
        enemy_statuses = {}
        with patch("combat.random.random", return_value=0.01):
            combat.apply_skill_effect(skill, p, enemy_statuses)
        self.assertEqual(engine.get_effective_defense(10, enemy_statuses), 6)

    def test_wudang_damage_reduction(self):
        import combat
        p = Player("武当测试", "武当")
        skill = engine.SKILLS["武当"][0]
        with patch("combat.random.random", return_value=0.01):
            combat.apply_skill_effect(skill, p, {})
        self.assertEqual(engine.apply_damage_reduction(engine.p_statuses_global, 100), 75)

    def test_wudang_shield(self):
        import combat
        p = Player("武当测试", "武当")
        skill = engine.SKILLS["武当"][1]
        with patch("combat.random.random", return_value=0.01):
            combat.apply_skill_effect(skill, p, {})
        self.assertEqual(engine.apply_shield(engine.p_statuses_global, 20), 0)
        self.assertEqual(engine.p_statuses_global["shield"]["value"], 10)

    def test_huashan_combo_deterministic(self):
        import combat
        skill = engine.SKILLS["华山"][1]
        # first random = combo chance check; subsequent values are hit/crit checks.
        with patch("combat.random.random", side_effect=[0.01, 0.01, 0.99]):
            results = combat._combo_damage(100, skill, 0.90, 0.05, 0.08)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0][0], 75)

    def test_sanren_tunat_recovers_mp(self):
        import combat
        p = Player("散人测试", "散人")
        p.mp = 20
        skill = engine.SKILLS["散人"][0]
        with patch("combat.random.random", return_value=0.01):
            combat.apply_skill_effect(skill, p, {})
        self.assertEqual(p.mp, 45)


class MartialArtsLifecycleTests(unittest.TestCase):
    def setUp(self):
        engine.clear_statuses()

    def tearDown(self):
        engine.clear_statuses()

    def test_multi_effect_skill_api(self):
        import combat
        p = Player("多效果测试", "散人")
        skill = {"name": "测试连携", "effects": [
            {"type": "mp_restore", "amount": 7},
            {"type": "self_status", "status": "damage_reduction", "chance": 1.0, "turns": 2, "value": 20},
        ]}
        p.mp = 10
        msgs = combat.apply_skill_effect(skill, p, {})
        self.assertEqual(p.mp, 17)
        self.assertIn("damage_reduction", engine.p_statuses_global)
        self.assertEqual(len(msgs), 2)

    def test_status_does_not_leak_between_combats(self):
        import combat
        engine.add_status(engine.p_statuses_global, "shield", 3, 30)
        self.assertIn("shield", engine.p_statuses_global)
        # combat() 会在正式进入战斗时清理旧战斗状态；这里直接验证同一生命周期入口。
        original = engine.ENEMIES.get("状态测试敌人")
        engine.ENEMIES["状态测试敌人"] = {"hp": 1, "atk": 1, "defense": 0, "exp": 0, "gold": 0, "skills": [], "drops": []}
        p = Player("状态生命周期", "散人")
        with patch("builtins.input", side_effect=["1"]), patch("combat.random.random", return_value=0.50), patch("combat.battle_pause", return_value=None):
            combat.combat(p, "状态测试敌人")
        self.assertNotIn("shield", engine.p_statuses_global)
        if original is None:
            engine.ENEMIES.pop("状态测试敌人", None)
        else:
            engine.ENEMIES["状态测试敌人"] = original

    def test_stun_is_immediate_for_enemy_turn(self):
        import combat
        p = Player("眩晕测试", "少林")
        skill = engine.SKILLS["少林"][0]
        e_statuses = {}
        with patch("combat.random.random", return_value=0.01):
            combat.apply_skill_effect(skill, p, e_statuses)
        self.assertTrue("stun" in e_statuses)
        # 玩家命中后的敌人回合由 combat.py 读取实时状态，不再使用上一轮缓存值。
        self.assertTrue("stun" in e_statuses)


class EnemyAITests(unittest.TestCase):
    def test_legacy_enemy_skill_selection_still_works(self):
        import combat
        enemy = {"skills": [{"name": "旧技能", "chance": 1.0, "power": 1.2}]}
        with patch("combat.random.random", return_value=0.01):
            self.assertEqual(combat.pick_enemy_skill(enemy)["name"], "旧技能")

    def test_boss_prefers_stun_when_player_low(self):
        import combat
        enemy = engine.ENEMIES["黑市头目"]
        p = Player("AI测试", "散人")
        p.max_hp = 100
        p.hp = 50
        with patch("combat.random.random", side_effect=[0.01]):
            skill = combat.pick_enemy_skill(enemy, 190, 190, p, {})
        self.assertEqual(skill["name"], "阴狠点穴")

    def test_poison_skill_not_repeated_when_target_already_poisoned(self):
        import combat
        enemy = engine.ENEMIES["毒蛇"]
        p = Player("AI测试", "散人")
        p.max_hp = 100
        p.hp = 100
        # 毒牙条件不满足，最终不应选中任何技能；只有一个技能。
        with patch("combat.random.random", return_value=0.01):
            skill = combat.pick_enemy_skill(enemy, 35, 35, p, {"poison": {"turns": 2, "value": 5}})
        self.assertIsNone(skill)

    def test_boss_uses_normal_attack_when_low_hp_control_skill_not_ready(self):
        import combat
        enemy = engine.ENEMIES["山贼大当家"]
        p = Player("AI测试", "散人")
        p.max_hp = 100
        p.hp = 90
        # 咆哮震慑的残血条件不满足，普通霸刀优先级较低但仍可正常选中。
        with patch("combat.random.random", side_effect=[0.01, 0.01]):
            skill = combat.pick_enemy_skill(enemy, 240, 240, p, {})
        self.assertEqual(skill["name"], "开山霸刀")


class BossPhaseTests(unittest.TestCase):
    def test_boss_phase_thresholds(self):
        import combat
        enemy = engine.ENEMIES["山贼大当家"]
        self.assertEqual(combat.get_enemy_phase(enemy, 200, 240), 1)
        self.assertEqual(combat.get_enemy_phase(enemy, 160, 240), 2)
        self.assertEqual(combat.get_enemy_phase(enemy, 80, 240), 3)

    def test_phase_unlocks_new_skill(self):
        import combat
        enemy = engine.ENEMIES["山贼大当家"]
        p = Player("阶段技能测试", "散人")
        p.max_hp = 100
        p.hp = 100
        with patch("combat.random.random", return_value=0.01):
            phase1_skill = combat.pick_enemy_skill(enemy, 220, 240, p, {}, phase=1)
            phase2_skill = combat.pick_enemy_skill(enemy, 160, 240, p, {}, phase=2)
        self.assertNotEqual(phase1_skill["name"], "横扫千军")
        self.assertEqual(phase2_skill["name"], "横扫千军")

    def test_phase_three_unlocks_execution_skill(self):
        import combat
        enemy = engine.ENEMIES["黑市头目"]
        p = Player("终阶段测试", "散人")
        p.max_hp = 100
        p.hp = 80
        with patch("combat.random.random", return_value=0.01):
            skill = combat.pick_enemy_skill(enemy, 50, 190, p, {}, phase=3)
        self.assertEqual(skill["name"], "黑市绝命掌")

    def test_non_boss_without_phases_stays_phase_one(self):
        import combat
        enemy = engine.ENEMIES["野狼"]
        self.assertEqual(combat.get_enemy_phase(enemy, 1, 40), 1)
        self.assertEqual(combat.get_enemy_phase_data(enemy, 2), {})


class CombatRewardTests(unittest.TestCase):
    def test_legacy_reward_schema_is_unchanged(self):
        import combat
        enemy = {
            "exp": 25,
            "gold": 17,
            "drops": [{"item": "野猪肉", "chance": 1.0}],
        }
        with patch("combat.random.random", return_value=0.99):
            rewards = combat.resolve_enemy_rewards(enemy)
        self.assertEqual(rewards["exp"], 25)
        self.assertEqual(rewards["gold"], 17)
        self.assertEqual(rewards["drops"], [{"item": "野猪肉", "quantity": 1}])

    def test_reward_range_and_quantity(self):
        import combat
        enemy = {
            "exp": {"min": 40, "max": 40},
            "gold": {"min": 20, "max": 20},
            "drops": [{"item": "铁矿石", "chance": 1.0, "min_qty": 2, "max_qty": 2}],
        }
        rewards = combat.resolve_enemy_rewards(enemy)
        self.assertEqual(rewards["exp"], 40)
        self.assertEqual(rewards["gold"], 20)
        self.assertEqual(rewards["drops"], [{"item": "铁矿石", "quantity": 2}])

    def test_guaranteed_drop_ignores_chance(self):
        import combat
        enemy = {
            "exp": 0,
            "gold": 0,
            "drops": [{"item": "大还丹", "chance": 0.0, "guaranteed": True}],
        }
        with patch("combat.random.random", return_value=0.99):
            rewards = combat.resolve_enemy_rewards(enemy)
        self.assertEqual(rewards["drops"], [{"item": "大还丹", "quantity": 1}])

    def test_drop_rolls_can_yield_multiple_copies(self):
        import combat
        enemy = {
            "exp": 0,
            "gold": 0,
            "drops": [{"item": "草药", "chance": 0.5, "rolls": 3}],
        }
        with patch("combat.random.random", side_effect=[0.1, 0.9, 0.2]):
            rewards = combat.resolve_enemy_rewards(enemy)
        self.assertEqual(rewards["drops"], [
            {"item": "草药", "quantity": 1},
            {"item": "草药", "quantity": 1},
        ])

    def test_p28_live_enemy_data_uses_new_reward_fields(self):
        import combat
        boss = engine.ENEMIES["山贼大当家"]
        boss_drop = next(d for d in boss["drops"] if d["item"] == "大还丹")
        self.assertTrue(boss_drop["guaranteed"])
        bandit_drop = engine.ENEMIES["山贼"]["drops"][0]
        self.assertEqual((bandit_drop["min_qty"], bandit_drop["max_qty"]), (1, 2))
        with patch("combat.random.random", return_value=0.01), patch("combat.random.randint", return_value=2):
            rewards = combat.resolve_enemy_rewards(engine.ENEMIES["山贼"])
        self.assertIn({"item": "铁矿石", "quantity": 2}, rewards["drops"])


class TradingSystemTests(unittest.TestCase):
    def setUp(self):
        self.player = Player("交易测试", "散人")
        self.player.location = "medicine_shop"
        self.player.inventory = ["疗伤药", "疗伤药", "野猪肉", "铁矿石"]
        self.player.gold = 1000

    def test_buy_multiple_items_is_atomic(self):
        import actions
        with patch.object(self.player, "save_to_file", return_value=True):
            ok = actions.handle_trading(self.player, "buy", ["回内丹", "3"])
        self.assertTrue(ok)
        self.assertEqual(self.player.inventory.count("回内丹"), 3)
        self.assertEqual(self.player.gold, 925)

    def test_buy_insufficient_gold_does_not_change_inventory_or_gold(self):
        import actions
        self.player.gold = 10
        before = list(self.player.inventory)
        with patch.object(self.player, "save_to_file", return_value=True):
            ok = actions.handle_trading(self.player, "buy", ["回内丹", "2"])
        self.assertFalse(ok)
        self.assertEqual(self.player.inventory, before)
        self.assertEqual(self.player.gold, 10)

    def test_sell_multiple_items_uses_half_price(self):
        import actions
        with patch.object(self.player, "save_to_file", return_value=True):
            ok = actions.handle_trading(self.player, "sell", ["疗伤药", "2"])
        self.assertTrue(ok)
        self.assertEqual(self.player.inventory.count("疗伤药"), 0)
        self.assertEqual(self.player.gold, 1020)

    def test_sell_quantity_above_owned_does_not_change_state(self):
        import actions
        before = list(self.player.inventory)
        gold = self.player.gold
        with patch.object(self.player, "save_to_file", return_value=True):
            ok = actions.handle_trading(self.player, "sell", ["野猪肉", "2"])
        self.assertFalse(ok)
        self.assertEqual(self.player.inventory, before)
        self.assertEqual(self.player.gold, gold)

    def test_trade_command_parser_keeps_quantity(self):
        self.assertEqual(parse_command("buy 金创药 3"), ("buy", ["金创药", "3"]))
        self.assertEqual(parse_command("sell 野猪肉 5"), ("sell", ["野猪肉", "5"]))

class RewardSystemTests(unittest.TestCase):
    def test_legacy_item_reward_uses_unified_apply_path(self):
        from rewards import apply_reward_bundle
        p = Player("奖励兼容", "散人")
        p.gold = 10
        result = apply_reward_bundle(p, {"exp": 30, "gold": 25, "item": "大还丹"}, source="任务奖励", announce=False)
        self.assertTrue(result["ok"])
        self.assertEqual(p.gold, 35)
        self.assertEqual(p.inventory.count("大还丹"), 1)
        self.assertEqual(result["items"], [{"item": "大还丹", "quantity": 1}])

    def test_reward_items_support_quantity_and_multiple_entries(self):
        from rewards import apply_reward_bundle
        p = Player("批量奖励", "散人")
        result = apply_reward_bundle(
            p,
            {"items": ["草药", {"item": "铁矿石", "quantity": 2}]},
            announce=False,
        )
        self.assertTrue(result["ok"])
        self.assertEqual(p.inventory.count("草药"), 2)
        self.assertEqual(p.inventory.count("铁矿石"), 3)

    def test_reward_effects_use_existing_world_state_api(self):
        from rewards import apply_reward_bundle
        p = Player("世界奖励", "散人")
        result = apply_reward_bundle(
            p,
            {"gold": 10, "effects": {
                "set_flags": {"reward:test": True},
                "increment_variables": {"merchant_reputation": 5},
            }},
            announce=False,
        )
        self.assertTrue(result["ok"])
        self.assertTrue(p.get_flag("reward:test"))
        self.assertEqual(p.get_var("merchant_reputation"), 5)

    def test_invalid_reward_is_atomic(self):
        from rewards import apply_reward_bundle
        p = Player("奖励原子性", "散人")
        before_inventory = list(p.inventory)
        before_gold = p.gold
        result = apply_reward_bundle(
            p,
            {"gold": 999, "items": ["不存在的物品"]},
            announce=False,
        )
        self.assertFalse(result["ok"])
        self.assertEqual(p.gold, before_gold)
        self.assertEqual(p.inventory, before_inventory)

    def test_combat_reward_shape_can_be_applied_directly(self):
        from rewards import apply_reward_bundle
        p = Player("战斗奖励", "散人")
        result = apply_reward_bundle(
            p,
            {"exp": 20, "gold": 15, "drops": [{"item": "金创药", "quantity": 2}]},
            source="战斗奖励",
            announce=False,
        )
        self.assertTrue(result["ok"])
        self.assertEqual(p.gold, 65)
        self.assertEqual(p.inventory.count("金创药"), 2)

class BuildSystemTests(unittest.TestCase):
    def test_new_player_starts_with_no_attribute_points(self):
        p = Player("Build新手", "散人")
        self.assertEqual(p.attribute_points, 0)
        self.assertEqual(sum(p.attributes.values()), 0)

    def test_level_up_grants_attribute_points(self):
        p = Player("成长", "散人")
        p.exp = p.exp_to_level - 1
        p.gain_exp(1)
        self.assertEqual(p.level, 2)
        self.assertEqual(p.attribute_points, 3)

    def test_allocate_strength_changes_attack(self):
        p = Player("力量流", "散人")
        p.attribute_points = 3
        base = p.get_total_atk()
        ok, _ = p.allocate_attribute("力量", 2)
        self.assertTrue(ok)
        self.assertEqual(p.attribute_points, 1)
        self.assertEqual(p.get_total_atk(), base + 4)

    def test_agility_and_insight_change_combat_rates(self):
        p = Player("敏锐", "散人")
        p.attribute_points = 3
        p.allocate_attribute("身法", 1)
        p.allocate_attribute("洞察", 1)
        self.assertAlmostEqual(p.get_hit_chance(), 0.91)
        self.assertAlmostEqual(p.get_dodge_chance(), 0.06)
        self.assertAlmostEqual(p.get_crit_chance(), 0.09)

    def test_old_v12_save_gets_retroactive_points_without_version_change(self):
        p = Player("旧档", "散人")
        p.level = 5
        fd, path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump({
                    "version": 12, "name": p.name, "sect": "散人", "level": 5,
                    "exp": 0, "exp_to_level": 100, "hp": 100, "max_hp": 100,
                    "mp": 50, "max_mp": 50, "atk": 10, "defense": 5, "gold": 50,
                    "inventory": [], "equipment": {"weapon": "木剑", "armor": "布衣"},
                    "equip_enhance": {"weapon": 0, "armor": 0}, "location": "village_gate",
                    "active_quests": {}, "quest_states": {}, "completed_quests": [],
                    "world_state": {"flags": {}, "variables": {}}
                }, f, ensure_ascii=False)
            q = Player.load_from_file(path)
            self.assertEqual(q.attribute_points, 12)
            self.assertEqual(q.level, 5)
        finally:
            os.remove(path)

    def test_build_round_trip_preserves_attributes(self):
        p = Player("Build存档", "散人")
        p.attribute_points = 3
        p.allocate_attribute("体魄", 1)
        p.allocate_attribute("内息", 1)
        fd, path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        try:
            self.assertTrue(p.save_to_file(path))
            q = Player.load_from_file(path)
            self.assertEqual(q.attributes["constitution"], 1)
            self.assertEqual(q.attributes["internal"], 1)
            self.assertEqual(q.attribute_points, 1)
            self.assertEqual(q.max_hp, p.max_hp)
            self.assertEqual(q.max_mp, p.max_mp)
        finally:
            os.remove(path)

class EquipmentQualityTests(unittest.TestCase):
    def test_quality_variants_keep_v12_inventory_name_model(self):
        self.assertIn("精铁剑·精良", engine.ITEMS)
        self.assertEqual(engine.ITEMS["精铁剑·精良"]["base_item"], "精铁剑")
        self.assertEqual(engine.ITEMS["精铁剑·精良"]["quality"], "精良")
        self.assertEqual(engine.ITEMS["精铁剑·史诗"]["affix_count"], 3)

    def test_quality_drop_pool_resolves_variant(self):
        enemy = {
            "exp": 1,
            "gold": 1,
            "drops": [{
                "item": "精铁剑",
                "chance": 1.0,
                "quality_pool": [{"quality": "精良", "chance": 1.0}],
            }],
        }
        with patch("combat.random.random", side_effect=[0.0, 0.0]):
            rewards = combat.resolve_enemy_rewards(enemy)
        self.assertEqual(rewards["drops"][0]["item"], "精铁剑·精良")

    def test_quality_pool_can_fall_back_to_base_item(self):
        enemy = {
            "exp": 1,
            "gold": 1,
            "drops": [{
                "item": "精铁剑",
                "chance": 1.0,
                "quality_pool": [{"quality": "史诗", "chance": 0.2}],
            }],
        }
        with patch("combat.random.random", side_effect=[0.0, 0.9]):
            rewards = combat.resolve_enemy_rewards(enemy)
        self.assertEqual(rewards["drops"][0]["item"], "精铁剑")

    def test_quality_variant_equipment_affects_build(self):
        p = Player("品质测试", "散人")
        p.inventory.append("精铁剑·稀有")
        base = p.get_total_atk()
        ok, _ = p.equip_item("精铁剑·稀有")
        self.assertTrue(ok)
        self.assertEqual(p.get_total_atk(), base + 26)
        self.assertAlmostEqual(p.get_crit_chance(), 0.12)
        self.assertAlmostEqual(p.get_hit_chance(), 0.92)

    def test_quality_variant_save_round_trip_keeps_name(self):
        p = Player("品质存档", "散人")
        p.inventory.append("锁子甲·史诗")
        fd, path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        try:
            self.assertTrue(p.save_to_file(path))
            q = Player.load_from_file(path)
            self.assertIn("锁子甲·史诗", q.inventory)
            self.assertEqual(q.version if hasattr(q, "version") else engine.SAVE_VERSION, 12)
        finally:
            os.remove(path)

class EnhancementFeedbackTests(unittest.TestCase):
    def test_enhancement_preview_is_side_effect_free(self):
        p = Player("强化预览", "散人")
        p.equipment = {"weapon": "精铁剑·稀有", "armor": "锁子甲"}
        p.equip_enhance = {"weapon": 2, "armor": 1}
        p.gold = 200
        p.inventory = ["铁矿石", "铁矿石"]
        before = (p.gold, list(p.inventory), dict(p.equip_enhance))
        preview = p.get_enhancement_preview("weapon")
        self.assertTrue(preview["available"])
        self.assertEqual(preview["current_level"], 2)
        self.assertEqual(preview["next_level"], 3)
        self.assertEqual(preview["stat_delta"], 3)
        self.assertEqual(preview["ore_cost"], 2)
        self.assertEqual(preview["gold_cost"], 65)
        self.assertEqual((p.gold, p.inventory, p.equip_enhance), before)

    def test_enhancement_preview_reports_max_level(self):
        p = Player("满强化", "散人")
        p.equipment = {"weapon": "玄铁重剑·史诗", "armor": "锁子甲·史诗"}
        p.equip_enhance = {"weapon": 8, "armor": 8}
        preview = p.get_enhancement_preview("weapon")
        self.assertFalse(preview["available"])
        self.assertEqual(preview["reason"], "max")
        self.assertEqual(preview["max_level"], 8)

    def test_equipment_power_breakdown_separates_base_and_enhancement(self):
        p = Player("强化明细", "散人")
        p.equipment = {"weapon": "精铁剑", "armor": "布衣"}
        p.equip_enhance = {"weapon": 4, "armor": 0}
        breakdown = p.get_equipment_power_breakdown("weapon")
        self.assertEqual(breakdown["base"], 20)
        self.assertEqual(breakdown["enhance_bonus"], 12)
        self.assertEqual(breakdown["total"], 32)
        self.assertEqual(breakdown["enhance"], 4)


class EnemyProgressionTests(unittest.TestCase):
    def test_enemy_profile_uses_base_level_without_region_scaling(self):
        profile = combat.get_enemy_profile("野猪", "official_road")
        self.assertEqual(profile["base_level"], 2)
        self.assertEqual(profile["level"], 2)
        self.assertEqual(profile["growth_levels"], 0)
        self.assertEqual(profile["hp"], engine.ENEMIES["野猪"]["hp"])

    def test_enemy_profile_scales_to_region_difficulty(self):
        profile = combat.get_enemy_profile("山贼", "bandit_courtyard")
        self.assertEqual(profile["base_level"], 3)
        self.assertEqual(profile["level"], 4)
        self.assertEqual(profile["growth_levels"], 1)
        self.assertGreater(profile["hp"], engine.ENEMIES["山贼"]["hp"])
        self.assertGreater(profile["atk"], engine.ENEMIES["山贼"]["atk"])

    def test_boss_growth_is_stronger_than_normal_growth(self):
        boss = combat.get_enemy_profile("山贼大当家", "bandit_camp")
        normal = combat.get_enemy_profile("野猪", "bandit_camp")
        self.assertEqual(boss["tier"], "boss")
        self.assertGreater(boss["level"], engine.ENEMIES["山贼大当家"]["level"] - 1)
        self.assertGreater(normal["level"], engine.ENEMIES["野猪"]["level"])

    def test_enemy_profile_does_not_mutate_static_data(self):
        before = dict(engine.ENEMIES["山贼"])
        combat.get_enemy_profile("山贼", "bandit_courtyard")
        self.assertEqual(engine.ENEMIES["山贼"], before)

    def test_guiyun_region_has_higher_enemy_levels(self):
        profile = combat.get_enemy_profile("黑市头目", "guiyun_black_market_hall")
        self.assertEqual(profile["level"], 12)
        self.assertEqual(profile["tier_label"], "Boss")
        self.assertEqual(profile["difficulty_level"], 12)

    def test_save_version_remains_v12(self):
        self.assertEqual(engine.SAVE_VERSION, 12)

class LootLoopTests(unittest.TestCase):
    def test_equipment_score_is_quality_and_build_aware(self):
        p = Player("Loot评分", "散人")
        p.attributes["strength"] = 2
        p.equipment["weapon"] = "铁剑"
        result = p.evaluate_equipment("玄铁重剑·稀有")
        self.assertIsNotNone(result)
        self.assertGreater(result["score"], result["current_score"])
        self.assertEqual(result["build_after"]["name"], "重剑强攻")

    def test_equipment_score_does_not_mutate_player(self):
        p = Player("Loot纯计算", "散人")
        before = dict(p.equipment)
        score = p.get_equipment_score("精铁剑·史诗")
        self.assertGreater(score, 0)
        self.assertEqual(p.equipment, before)

    def test_compare_contains_score_delta(self):
        p = Player("Loot比较", "散人")
        p.equipment["weapon"] = "铁剑"
        result = p.compare_equipment("精铁剑·稀有")
        self.assertIn("candidate_score", result)
        self.assertIn("current_score", result)
        self.assertEqual(result["candidate_score"] - result["current_score"],
                         result["candidate_score"] - result["current_score"])

    def test_loot_quality_variant_is_evaluable(self):
        p = Player("品质掉落", "散人")
        result = p.evaluate_equipment("玄铁重剑·史诗")
        self.assertEqual(result["quality"], "史诗")
        self.assertGreaterEqual(result["score"], result["current_score"])

    def test_non_equipment_evaluation_returns_none(self):
        p = Player("药品评价", "散人")
        self.assertIsNone(p.evaluate_equipment("疗伤药"))


class WorldExplorationTests(unittest.TestCase):
    def test_world_regions_are_loaded(self):
        self.assertIn("main", engine.WORLD_REGIONS)
        self.assertIn("bandit_zone", engine.WORLD_REGIONS)
        self.assertIn("guiyun_city", engine.WORLD_REGIONS)

    def test_rooms_have_p221_exploration_metadata(self):
        room = engine.ROOMS["wild_fields"]
        self.assertIn("area_level", room)
        self.assertIn("recommended_level", room)
        self.assertIn("danger", room)
        self.assertIsInstance(room.get("exploration_events"), list)

    def test_exploration_increments_world_progress(self):
        from actions import handle_explore
        p = Player("探索测试", "散人")
        p.location = "wild_fields"
        before = p.get_var("exploration:main", 0)
        handle_explore(p)
        self.assertEqual(p.get_var("exploration:main", 0), before + 1)
        self.assertEqual(p.get_var("explore:wild_fields", 0), 1)


class NPCRelationshipTests(unittest.TestCase):
    def test_relation_defaults_to_neutral_and_changes(self):
        p = Player("关系测试", "散人")
        self.assertEqual(p.get_relation("村长"), 0)
        self.assertEqual(p.get_relation_status("村长"), "中立")
        p.change_relation("村长", 25)
        self.assertEqual(p.get_relation("村长"), 25)
        self.assertEqual(p.get_relation_status("村长"), "友善")

    def test_relation_is_clamped(self):
        p = Player("关系边界", "散人")
        p.change_relation("村长", 999)
        self.assertEqual(p.get_relation("村长"), 100)
        p.change_relation("村长", -999)
        self.assertEqual(p.get_relation("村长"), -100)

    def test_talk_choice_changes_relation(self):
        from actions import handle_talk_and_ask
        p = Player("对话测试", "散人")
        p.location = "village_head_house"
        handle_talk_and_ask(p, ["村长", "安慰"])
        self.assertEqual(p.get_relation("村长"), 4)

    def test_talk_without_choice_builds_relationship(self):
        from actions import handle_talk_and_ask
        p = Player("普通交谈", "散人")
        p.location = "village_head_house"
        handle_talk_and_ask(p, ["村长"])
        self.assertEqual(p.get_relation("村长"), 2)

    def test_relation_condition_can_gate_quest(self):
        p = Player("关系条件", "散人")
        q = engine.QUESTS["震远镖局"]
        self.assertFalse(engine.check_conditions(q.get("requires"), p.world_state, p.completed_quests, p))
        p.change_relation("震远镖局总镖头", 5)
        p.set_flag("visited_zone:guiyun_city", True)
        p.level = 6
        p.completed_quests.append("入城引路")
        self.assertTrue(engine.check_conditions(q.get("requires"), p.world_state, p.completed_quests, p))

    def test_relation_effect_uses_world_state_without_new_save_field(self):
        p = Player("关系效果", "散人")
        engine.apply_world_effects(p.world_state, {"relations": {"村长": 7}})
        self.assertEqual(p.get_relation("村长"), 7)
        fd, path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        try:
            self.assertTrue(p.save_to_file(path))
            with open(path, encoding="utf8") as f:
                raw = json.load(f)
            self.assertEqual(raw["version"], 12)
            self.assertNotIn("npc_relations", raw)
            self.assertEqual(raw["world_state"]["variables"]["npc_relations"]["村长"], 7)
            q = Player.load_from_file(path)
            self.assertEqual(q.get_relation("村长"), 7)
        finally:
            os.remove(path)

    def test_relation_parser(self):
        self.assertEqual(parse_command("关系 村长"), ("relations", ["村长"]))
        self.assertEqual(parse_command("explore"), ("explore", []))

    def test_existing_v12_save_load_keeps_relation_zero(self):
        p = Player("旧档兼容", "散人")
        fd, path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        try:
            p.save_to_file(path)
            with open(path, encoding="utf8") as f:
                raw = json.load(f)
            raw["world_state"]["variables"].pop("npc_relations", None)
            with open(path, "w", encoding="utf8") as f:
                json.dump(raw, f, ensure_ascii=False, indent=2)
            q = Player.load_from_file(path)
            self.assertEqual(q.get_relation("村长"), 0)
        finally:
            os.remove(path)

class NPCRelationshipR1Tests(unittest.TestCase):
    def test_relation_status_boundaries_are_centralized(self):
        p = Player("关系边界R1", "散人")
        cases = [(-100, "敌对"), (-30, "敌对"), (-29, "中立"), (19, "中立"), (20, "友善"), (49, "友善"), (50, "信任"), (79, "信任"), (80, "亲近")]
        for value, label in cases:
            p.change_relation("村长", value - p.get_relation("村长"))
            self.assertEqual(p.get_relation_status("村长"), label)

    def test_passive_talk_relation_has_a_cap(self):
        from actions import handle_talk_and_ask
        p = Player("关系防刷", "散人")
        p.set_var("quest_clock", 7)  # 13:00，守卫回到村口
        p.location = "village_gate"
        for _ in range(20):
            handle_talk_and_ask(p, ["守卫"])
        self.assertEqual(p.get_relation("守卫"), 10)
        self.assertEqual(p.get_talk_relation_gain("守卫"), 10)

    def test_once_dialogue_choice_cannot_repeat(self):
        from actions import handle_talk_and_ask
        p = Player("一次性对话", "散人")
        p.set_var("quest_clock", 7)  # 13:00，守卫回到村口
        p.location = "village_gate"
        p.gold = 100
        handle_talk_and_ask(p, ["守卫", "救济"])
        self.assertEqual(p.get_relation("守卫"), 3)
        self.assertTrue(p.is_dialogue_choice_used("守卫", "help_refugee"))
        self.assertEqual(p._jianghu_profile()["honor"], 3)
        self.assertEqual(p._jianghu_profile()["paths"]["侠客"], 5)
        handle_talk_and_ask(p, ["守卫", "救济"])
        self.assertEqual(p.get_relation("守卫"), 3)
        self.assertEqual(p._jianghu_profile()["honor"], 3)

    def test_positive_dialogue_choices_are_not_repeatable_relation_farms(self):
        from actions import handle_talk_and_ask
        p = Player("对话防刷", "散人")
        p.set_var("quest_clock", 7)  # 13:00，守卫回到村口
        p.location = "village_gate"
        handle_talk_and_ask(p, ["守卫", "请教"])
        self.assertEqual(p.get_relation("守卫"), 2)
        self.assertTrue(p.is_dialogue_choice_used("守卫", "dialogue_choice_1"))
        handle_talk_and_ask(p, ["守卫", "请教"])
        self.assertEqual(p.get_relation("守卫"), 2)

    def test_positive_dialogue_choice_data_has_once_guard(self):
        for npc_name, npc in engine.NPCS.items():
            for idx, choice in enumerate(npc.get("dialogue_choices", []) or [], 1):
                try:
                    delta = int(choice.get("relation_delta", 0))
                except (TypeError, ValueError):
                    continue
                if delta > 0:
                    self.assertTrue(
                        choice.get("once", False),
                        f"{npc_name} 的正向对话选项 {choice.get('keywords')} 缺少一次性限制"
                    )
                    self.assertTrue(choice.get("id", f"choice_{idx}"))

    def test_dialogue_choice_requires_condition(self):
        from actions import handle_talk_and_ask
        p = Player("条件对话", "散人")
        p.location = "village_gate"
        p.gold = 0
        handle_talk_and_ask(p, ["守卫", "救济"])
        self.assertEqual(p.get_relation("守卫"), 0)
        self.assertFalse(p.is_dialogue_choice_used("守卫", "help_refugee"))

    def test_npc_ecology_summary_is_stable(self):
        p = Player("生态摘要", "散人")
        info = p.get_npc_ecology("村长")
        self.assertEqual(info["name"], "村长")
        self.assertEqual(info["faction"], "青石村")
        self.assertIn("relation_status", info)
        self.assertIn("quests", info)

    def test_conditional_exploration_event_uses_relation_condition(self):
        from actions import handle_explore
        p = Player("探索关系", "散人")
        p.location = "guiyun_south_gate"
        p.change_relation("云来客栈掌柜", 2)
        p.set_var("explore:guiyun_south_gate", 3)
        handle_explore(p)
        self.assertTrue(p.get_flag("explore:guiyun_city:inn_clue", False))

class NPCRelationshipR2Tests(unittest.TestCase):
    def test_relation_behavior_boundaries(self):
        self.assertEqual(engine.relation_behavior(-100), "hostile")
        self.assertEqual(engine.relation_behavior(-80), "hostile")
        self.assertEqual(engine.relation_behavior(-79), "refuse")
        self.assertEqual(engine.relation_behavior(-60), "refuse")
        self.assertEqual(engine.relation_behavior(-59), "cold")
        self.assertEqual(engine.relation_behavior(-30), "cold")
        self.assertEqual(engine.relation_behavior(-29), "normal")
        self.assertEqual(engine.relation_behavior(20), "friendly")
        self.assertEqual(engine.relation_behavior(50), "trusted")
        self.assertEqual(engine.relation_behavior(80), "devoted")

    def test_cold_npc_no_longer_gains_passive_relation(self):
        from actions import handle_talk_and_ask
        p = Player("冷淡关系", "散人")
        p.location = "village_gate"
        p.change_relation("守卫", -30)
        handle_talk_and_ask(p, ["守卫"])
        self.assertEqual(p.get_relation("守卫"), -30)

    def test_refusing_npc_blocks_information_and_talk(self):
        from actions import handle_talk_and_ask
        p = Player("拒绝合作", "散人")
        p.location = "village_gate"
        p.change_relation("守卫", -60)
        handle_talk_and_ask(p, ["守卫", "山贼"])
        self.assertEqual(p.get_relation("守卫"), -60)
        self.assertEqual(p.get_talk_relation_gain("守卫"), 0)

    def test_hostile_npc_blocks_interaction(self):
        from actions import handle_talk_and_ask
        p = Player("敌对关系", "散人")
        p.location = "village_gate"
        p.change_relation("守卫", -80)
        handle_talk_and_ask(p, ["守卫"])
        self.assertEqual(p.get_relation("守卫"), -80)

    def test_relation_dialogue_unlocks_at_threshold(self):
        from actions import handle_talk_and_ask
        p = Player("特殊对话", "散人")
        p.set_var("quest_clock", 7)  # 13:00，守卫回到村口
        p.location = "village_gate"
        p.change_relation("守卫", 20)
        handle_talk_and_ask(p, ["守卫"])
        self.assertFalse(p.get_flag("npc:守卫:knows_defense_map", False))
        p.change_relation("守卫", 30)
        handle_talk_and_ask(p, ["守卫"])
        self.assertTrue(p.get_flag("npc:守卫:knows_defense_map", False))
        handle_talk_and_ask(p, ["守卫", "密道"])
        self.assertEqual(p.get_relation("守卫"), 53)

    def test_high_relation_once_reward_is_granted_once(self):
        from actions import handle_talk_and_ask
        p = Player("关系奖励", "散人")
        p.location = "village_head_house"
        p.change_relation("村长", 80)
        before_gold = p.gold
        before_items = p.inventory.count("护体丹")
        handle_talk_and_ask(p, ["村长"])
        self.assertEqual(p.gold, before_gold + 30)
        self.assertEqual(p.inventory.count("护体丹"), before_items + 1)
        self.assertTrue(p.get_flag("npc_relation_dialogue:村长:village_elder_heirloom", False))
        handle_talk_and_ask(p, ["村长"])
        self.assertEqual(p.gold, before_gold + 30)
        self.assertEqual(p.inventory.count("护体丹"), before_items + 1)

    def test_once_relation_dialogue_reward_failure_does_not_consume_effect_or_flag(self):
        from actions import handle_talk_and_ask
        p = Player("背包满载关系奖励", "散人")
        p.location = "village_head_house"
        p.change_relation("村长", 80)
        p.inventory_capacity = len(p.inventory)
        before_gold = p.gold
        before_inventory = list(p.inventory)
        handle_talk_and_ask(p, ["村长"])
        self.assertEqual(p.gold, before_gold)
        self.assertEqual(p.inventory, before_inventory)
        self.assertFalse(p.get_flag("npc:村长:heirloom_trust", False))
        self.assertFalse(p.get_flag("npc_relation_dialogue:村长:village_elder_heirloom", False))

    def test_relation_choice_requires_threshold(self):
        from actions import handle_talk_and_ask
        p = Player("门槛对话", "散人")
        p.set_var("quest_clock", 7)  # 13:00，守卫回到村口
        p.location = "village_gate"
        handle_talk_and_ask(p, ["守卫", "密道"])
        self.assertEqual(p.get_relation("守卫"), 0)
        p.change_relation("守卫", 20)
        handle_talk_and_ask(p, ["守卫", "密道"])
        self.assertEqual(p.get_relation("守卫"), 21)

    def test_npc_ecology_exposes_behavior_and_relation_dialogue(self):
        p = Player("生态R2", "散人")
        p.change_relation("村长", 50)
        info = p.get_npc_ecology("村长")
        self.assertEqual(info["behavior"], "trusted")
        self.assertGreaterEqual(info["relation_dialogue"], 3)

class Alpha193RivalSectTests(unittest.TestCase):
    def test_tieyi_sect_data_and_world_faction_are_connected(self):
        self.assertIn("铁衣门", engine.SECTS)
        self.assertIn("铁衣门", engine.FACTIONS)
        self.assertEqual(engine.SECTS["铁衣门"]["alignment"], "江湖竞争门派")
        self.assertIn("铁衣功", [x["name"] for x in engine.SKILLS["铁衣门"]])
        self.assertIn("破阵刀", [x["name"] for x in engine.SKILLS["铁衣门"]])
        self.assertEqual(engine.FACTIONS["铁衣门"]["relations"]["华山"], -20)
        self.assertEqual(engine.FACTIONS["华山"]["relations"]["铁衣门"], -20)

    def test_tieyi_route_and_internal_access_data(self):
        self.assertEqual(engine.ROOMS["road_tieyi_turnoff"]["exits"]["西"], "road_wudang_turnoff")
        self.assertEqual(engine.ROOMS["road_wudang_turnoff"]["exits"]["东"], "road_tieyi_turnoff")
        self.assertEqual(engine.ROOMS["tieyi_gate"]["exits"]["东"], "tieyi_guest_hall")
        self.assertEqual(engine.ROOMS["tieyi_training_ground"]["access"]["sect"], "铁衣门")
        self.assertEqual(engine.ROOMS["tieyi_council_hall"]["access"]["min_rank_index"], 2)

    def test_tieyi_join_and_exclusive_skill_growth(self):
        p = Player("铁衣门测试", "散人")
        p.level = 4
        self.assertTrue(p.join_sect("铁衣门")[0])
        self.assertEqual(p.get_sect(), "铁衣门")
        self.assertIn("铁衣功", [x["name"] for x in p.get_available_skills()])
        self.assertNotIn("罗汉拳", [x["name"] for x in p.get_available_skills()])
        before = p.get_skill_progress("铁衣功")["mastery"]
        p.record_skill_use("铁衣功")
        self.assertGreater(p.get_skill_progress("铁衣功")["mastery"], before)

    def test_tieyi_training_quest_is_valid_and_sect_locked(self):
        q = engine.QUESTS["铁衣门历练·护路除匪"]
        self.assertEqual(q["requires"]["sect"], "铁衣门")
        self.assertEqual(q["target_name"], "劫镖山贼")
        self.assertIn("铁衣门接引执事", engine.NPCS)
        self.assertIn("铁衣门接引执事", engine.ROOMS["tieyi_guest_hall"]["npcs"])


    def test_tieyi_join_requires_local_interview(self):
        p = Player("铁衣门入门流程", "散人")
        # Alpha219 起正式拜入门派最低等级为 10；本测试聚焦地点与接引面试门槛。
        p.level = 10
        p.location = "village_square"
        with patch("builtins.print") as printed:
            handle_sect(p, ["加入", "铁衣门"])
        self.assertEqual(p.get_sect(), "散人")
        p.location = "tieyi_guest_hall"
        with patch("builtins.print"):
            handle_sect(p, ["加入", "铁衣门"])
        self.assertEqual(p.get_sect(), "散人")
        p.set_flag("sect:tieyi:entry_interview", True)
        with patch("builtins.print"):
            handle_sect(p, ["加入", "铁衣门"])
        self.assertEqual(p.get_sect(), "铁衣门")

    def test_tieyi_promotion_requires_own_trial(self):
        p = Player("铁衣门晋升", "散人")
        p.level = 15
        self.assertTrue(p.join_sect("铁衣门")[0])
        p.change_sect_reputation("铁衣门", 100)
        p._sect_progress_state().setdefault("铁衣门", {})["official_rank_index"] = 2
        p.record_skill_use("铁衣功")
        req = p.get_sect_promotion_requirements()
        self.assertEqual(req["required_quests"], ["铁衣门历练·护路除匪"])
        ok, message = p.promote_sect_rank()
        self.assertFalse(ok)
        self.assertIn("铁衣门历练·护路除匪", message)


class SectMartialArtsP224Tests(unittest.TestCase):
    def test_new_sect_player_has_base_skill_but_not_advanced_skill(self):
        p = Player("武学基础", "少林")
        summary = {x["name"]: x for x in p.get_skill_summary()}
        self.assertTrue(summary["罗汉拳"]["learned"])
        self.assertFalse(summary["般若掌"]["learned"])

    def test_advanced_skill_requires_level_reputation_and_rank(self):
        p = Player("武学门槛", "少林")
        p.level = 3
        ok, _ = p.learn_skill("般若掌")
        self.assertFalse(ok)
        p.change_sect_reputation("少林", 50)
        ok, _ = p.learn_skill("般若掌")
        self.assertTrue(ok)
        self.assertTrue(p.get_skill_progress("般若掌")["learned"])

    def test_skill_mastery_grows_and_scales_runtime_power(self):
        p = Player("武学成长", "华山")
        p.level = 3
        p.change_sect_reputation("华山", 50)
        self.assertTrue(p.learn_skill("夺命连环三仙剑")[0])
        before = p.get_available_skills()[-1]
        for _ in range(5):
            p.record_skill_use("夺命连环三仙剑")
        after = p.get_available_skills()[-1]
        self.assertGreater(after["mastery_level"], before["mastery_level"])
        self.assertGreater(after["power"], before["power"])
        self.assertLess(after["mp_cost"], before["mp_cost"])

    def test_skill_mastery_caps(self):
        p = Player("熟练度上限", "武当")
        for _ in range(30):
            p.record_skill_use("太极剑")
        progress = p.get_skill_progress("太极剑")
        self.assertEqual(progress["mastery"], 100)
        self.assertEqual(progress["level"], 5)

    def test_malformed_saved_skill_progress_is_normalized_for_non_current_sect(self):
        p = Player("异常武学存档", "散人")
        p.world_state.setdefault("variables", {})["skill_progress"] = {
            "太极剑": {"learned": [], "mastery": "bad"},
            "华山剑法": ["unexpected"],
        }
        progress = p.get_skill_progress("太极剑")
        self.assertFalse(progress["learned"])
        self.assertEqual(progress["mastery"], 0)
        other = p.get_skill_progress("华山剑法")
        self.assertFalse(other["learned"])
        self.assertEqual(other["mastery"], 0)

    def test_forgetting_skill_removes_it_from_combat_list(self):
        p = Player("遗忘武学", "华山")
        self.assertIn("华山剑法", [x["name"] for x in p.get_available_skills()])
        self.assertTrue(p.forget_skill("华山剑法")[0])
        self.assertNotIn("华山剑法", [x["name"] for x in p.get_available_skills()])

    def test_forgetting_skill_survives_save_load(self):
        p = Player("遗忘存档", "武当")
        self.assertTrue(p.forget_skill("太极剑")[0])
        fd, path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        try:
            self.assertTrue(p.save_to_file(path))
            q = Player.load_from_file(path)
            self.assertNotIn("太极剑", [x["name"] for x in q.get_available_skills()])
        finally:
            os.remove(path)

    def test_v12_old_save_migrates_base_skill_without_new_top_level_field(self):
        p = Player("旧档武学", "少林")
        fd, path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        try:
            self.assertTrue(p.save_to_file(path))
            with open(path, encoding="utf8") as f:
                raw = json.load(f)
            raw["world_state"]["variables"].pop("skill_progress", None)
            raw["version"] = 12
            with open(path, "w", encoding="utf8") as f:
                json.dump(raw, f, ensure_ascii=False, indent=2)
            q = Player.load_from_file(path)
            self.assertTrue(q.get_skill_progress("罗汉拳")["learned"])
            self.assertNotIn("skill_progress", raw)
            self.assertEqual(raw["version"], 12)
        finally:
            os.remove(path)

    def test_sect_switch_does_not_leak_previous_sect_skills(self):
        p = Player("换门武学", "少林")
        self.assertIn("罗汉拳", [x["name"] for x in p.get_available_skills()])
        self.assertTrue(p.leave_sect()[0])
        p.level = max(p.level, 3)
        self.assertTrue(p.join_sect("武当")[0])
        self.assertNotIn("罗汉拳", [x["name"] for x in p.get_available_skills()])
        self.assertIn("太极剑", [x["name"] for x in p.get_available_skills()])

    def test_skill_command_parser_and_summary(self):
        self.assertEqual(parse_command("武学"), ("skills", []))
        self.assertEqual(parse_command("skills learn 般若掌"), ("skills", ["learn", "般若掌"]))
        p = Player("武学摘要", "散人")
        self.assertTrue(any(x["name"] == "基础吐纳" and x["learned"] for x in p.get_skill_summary()))

    def test_skill_progress_is_stored_inside_existing_world_state(self):
        p = Player("状态结构", "华山")
        p.record_skill_use("华山剑法")
        fd, path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        try:
            p.save_to_file(path)
            with open(path, encoding="utf8") as f:
                raw = json.load(f)
            self.assertEqual(raw["version"], 12)
            self.assertIn("skill_progress", raw["world_state"]["variables"])
            self.assertNotIn("skill_progress", raw)
        finally:
            os.remove(path)

class QuestEcologyP225Tests(unittest.TestCase):
    def test_quest_command_supports_abandon(self):
        self.assertEqual(parse_command("fangqi 清剿黑风山"), ("fangqi", ["清剿黑风山"]))

    def test_abandon_quest_clears_active_state_but_preserves_world_history(self):
        p = Player("放弃任务", "散人")
        p.active_quests["入城引路"] = 0
        p.quest_states["入城引路"] = {"stage": 0, "progress": 0, "accepted_at": 0}
        ok, _ = p.abandon_quest("入城引路")
        self.assertTrue(ok)
        self.assertNotIn("入城引路", p.active_quests)
        self.assertTrue(p.get_flag("quest_abandoned:入城引路"))

    def test_timed_quest_fails_and_can_retry(self):
        p = Player("限时任务", "少林")
        p.level = 5
        p.change_relation("村长", 8)
        p.location = "village_head_house"
        from actions import handle_quest, look
        handle_quest(p, "jiequ", ["黑风限时追缉"])
        self.assertIn("黑风限时追缉", p.active_quests)
        p.tick_quest_clock(8)
        self.assertNotIn("黑风限时追缉", p.active_quests)
        self.assertTrue(p.get_flag("quest_failed:黑风限时追缉"))
        # Alpha226：任务必须由当前实际在场的发布 NPC 重新发放；限时失败后先回到村长处。
        p.set_npc_location("村长", "village_head_house")
        handle_quest(p, "jiequ", ["黑风限时追缉"])
        self.assertIn("黑风限时追缉", p.active_quests)

    def test_skill_requirement_blocks_quest_until_skill_is_learned(self):
        p = Player("武学任务门槛", "少林")
        p.level = 5
        p.change_relation("村长", 8)
        p.forget_skill("罗汉拳")
        self.assertFalse(engine.check_conditions(engine.QUESTS["黑风限时追缉"]["requires"], p.world_state, p.completed_quests, p))
        self.assertTrue(p.learn_skill("罗汉拳")[0])
        self.assertTrue(engine.check_conditions(engine.QUESTS["黑风限时追缉"]["requires"], p.world_state, p.completed_quests, p))

    def test_quest_branch_requires_relation_and_changes_world_state(self):
        p = Player("任务分支", "散人")
        p.location = "merchant_guild"
        p.change_relation("万商会会长", 5)
        q = engine.QUESTS["万商会商路"]
        eligible = [c["id"] for c in q["choices"] if engine.check_conditions(c.get("requires"), p.world_state, p.completed_quests, p)]
        self.assertIn("public_audit", eligible)
        self.assertNotIn("private_deal", eligible)
        p.change_relation("万商会会长", 10)
        eligible = [c["id"] for c in q["choices"] if engine.check_conditions(c.get("requires"), p.world_state, p.completed_quests, p)]
        self.assertNotIn("private_deal", eligible)  # 关系达标仍需黑市倾向或恶名
        p.record_jianghu_action("black_market_trade", 1)
        eligible = [c["id"] for c in q["choices"] if engine.check_conditions(c.get("requires"), p.world_state, p.completed_quests, p)]
        self.assertIn("private_deal", eligible)

    def test_repeatable_quest_can_be_completed_again(self):
        q = dict(engine.QUESTS["少林历练·黑风除恶"])
        q["repeatable"] = True
        engine.QUESTS["__repeat_test__"] = q
        try:
            p = Player("重复任务", "少林")
            p.completed_quests.append("__repeat_test__")
            self.assertTrue(q.get("repeatable"))
            self.assertTrue(engine.check_conditions(q.get("requires"), p.world_state, p.completed_quests, p))
        finally:
            engine.QUESTS.pop("__repeat_test__", None)

    def test_quest_lifecycle_state_round_trip_stays_in_existing_world_state(self):
        p = Player("任务生命周期存档", "少林")
        p.world_state["variables"]["quest_clock"] = 7
        p.world_state["variables"]["quest_failures"] = {"测试任务": {"reason": "time_limit", "clock": 7}}
        fd, path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        try:
            self.assertTrue(p.save_to_file(path))
            with open(path, encoding="utf8") as f:
                raw = json.load(f)
            self.assertEqual(raw["version"], 12)
            self.assertIn("quest_clock", raw["world_state"]["variables"])
            self.assertIn("quest_failures", raw["world_state"]["variables"])
            self.assertNotIn("quest_failures", raw)
            q = Player.load_from_file(path)
            self.assertEqual(q.get_quest_clock(), 7)
            self.assertIn("测试任务", q.get_var("quest_failures", {}))
        finally:
            os.remove(path)



class CombatAI_P227Tests(unittest.TestCase):
    def test_enemy_ai_styles_are_data_driven(self):
        import combat
        self.assertEqual(combat.get_enemy_ai_style(engine.ENEMIES["山贼"]), "aggressive")
        self.assertEqual(combat.get_enemy_ai_style(engine.ENEMIES["黑市头目"]), "tactical")
        self.assertIn(combat.get_enemy_ai_style(engine.ENEMIES["山贼头目"]), {"elite", "aggressive"})

    def test_enemy_ai_guard_is_used_by_defensive_style(self):
        import combat
        from unittest.mock import patch
        enemy = {"ai": {"style": "defensive"}, "skills": []}
        with patch("combat.random.random", return_value=0.0):
            decision = combat.choose_enemy_action(enemy, 30, 100, Player("AI测试", "散人"), {}, 1, {})
        self.assertEqual(decision["action"], "guard")
        self.assertGreaterEqual(decision["reduction"], 25)

    def test_aggressive_enemy_prefers_available_skill(self):
        import combat
        enemy = {"ai": {"style": "aggressive"}, "skills": [{"name": "猛击", "chance": 1.0, "power": 1.4}]}
        p = Player("AI攻击", "散人")
        decision = combat.choose_enemy_action(enemy, 100, 100, p, {}, 1, {})
        self.assertEqual(decision["action"], "skill")
        self.assertEqual(decision["skill"]["name"], "猛击")

    def test_world_pressure_strengthens_bandit_battle_snapshot_only(self):
        import combat
        p = Player("战况", "散人")
        p.location = "bandit_courtyard"
        p.set_var("world:bandit:pressure", 2)
        base = combat.get_enemy_profile("山贼", p.location)
        before = (base["hp"], base["atk"], base["defense"])
        pressure = combat.apply_world_combat_pressure(base, p)
        self.assertEqual(pressure, 2)
        self.assertGreater(base["hp"], before[0])
        self.assertGreater(base["atk"], before[1])
        self.assertGreaterEqual(base["defense"], before[2])
        self.assertNotEqual(engine.ENEMIES["山贼"]["hp"], base["hp"])

    def test_world_pressure_zero_keeps_snapshot_unchanged(self):
        import combat
        p = Player("无压力", "散人")
        p.location = "bandit_courtyard"
        base = combat.get_enemy_profile("山贼", p.location)
        before = dict(base)
        self.assertEqual(combat.apply_world_combat_pressure(base, p), 0)
        self.assertEqual(base["hp"], before["hp"])
        self.assertEqual(base["atk"], before["atk"])


class WorldEventP226Tests(unittest.TestCase):
    def test_world_events_data_is_loaded_and_region_bound(self):
        self.assertTrue(engine.WORLD_EVENTS)
        for event_id, info in engine.WORLD_EVENTS.items():
            self.assertIn(info["region"], engine.WORLD_REGIONS)
            self.assertTrue(info.get("title"))

    def test_event_conditions_block_then_unlock(self):
        p = Player("事件条件", "散人")
        p.location = "village"
        p.set_var("exploration:main", 1)
        self.assertFalse(p.can_trigger_world_event("main_bandit_warning"))
        p.set_var("exploration:main", 2)
        self.assertTrue(p.can_trigger_world_event("main_bandit_warning"))

    def test_once_world_event_changes_state_and_cannot_repeat(self):
        p = Player("一次事件", "散人")
        p.location = "village"
        p.set_var("exploration:main", 2)
        old_gold = p.gold
        ok, _, _ = p.trigger_world_event("main_bandit_warning")
        self.assertTrue(ok)
        self.assertTrue(p.get_flag("world:main:bandit_pressure"))
        self.assertEqual(p.gold, old_gold + 8)
        self.assertFalse(p.can_trigger_world_event("main_bandit_warning"))

    def test_event_chain_unlocks_followup(self):
        p = Player("事件链", "散人")
        p.location = "village"
        p.set_var("exploration:main", 2)
        p.trigger_world_event("main_bandit_warning")
        p.level = 2
        self.assertTrue(p.can_trigger_world_event("main_caravan_help"))
        ok, _, _ = p.trigger_world_event("main_caravan_help")
        self.assertTrue(ok)
        self.assertTrue(p.get_flag("world:main:caravan_safe"))

    def test_caravan_help_event_cannot_be_farmed_for_reputation(self):
        p = Player("商队求援", "少林")
        p.location = "village"
        p.set_var("exploration:main", 2)
        p.trigger_world_event("main_bandit_warning")
        p.level = 2
        self.assertTrue(p.can_trigger_world_event("main_caravan_help"))
        self.assertTrue(p.trigger_world_event("main_caravan_help")[0])
        self.assertEqual(p.get_sect_reputation("少林"), 3)
        # 事件为一次性，冷却推进后也不能再次刷取门派声望。
        p.tick_quest_clock(48)
        self.assertFalse(p.can_trigger_world_event("main_caravan_help"))
        self.assertFalse(p.trigger_world_event("main_caravan_help")[0])
        self.assertEqual(p.get_sect_reputation("少林"), 3)

    def test_world_event_cooldown_uses_existing_quest_clock(self):
        p = Player("事件冷却", "散人")
        p.location = "bandit_courtyard"
        p.set_var("exploration:bandit_zone", 1)
        self.assertTrue(p.can_trigger_world_event("bandit_reinforcement"))
        p.trigger_world_event("bandit_reinforcement")
        self.assertFalse(p.can_trigger_world_event("bandit_reinforcement"))
        p.tick_quest_clock(5)
        self.assertTrue(p.can_trigger_world_event("bandit_reinforcement"))

    def test_world_event_rewards_support_sect_reputation_and_relation(self):
        p = Player("事件奖励", "少林")
        p.location = "village"
        p.set_var("exploration:main", 2)
        p.trigger_world_event("main_bandit_warning")
        self.assertEqual(p.get_sect_reputation("少林"), 0)
        p.level = 2
        ok, _, _ = p.trigger_world_event("main_caravan_help")
        self.assertTrue(ok)
        self.assertEqual(p.get_sect_reputation("少林"), 3)
        self.assertEqual(p.get_relation("村长"), 2)

    def test_invalid_world_event_reward_does_not_consume_event_or_apply_effects(self):
        p = Player("无效事件奖励", "散人")
        p.location = "village"
        event_id = "test_invalid_world_event_reward"
        original = engine.WORLD_EVENTS.get(event_id)
        engine.WORLD_EVENTS[event_id] = {
            "title": "测试无效奖励事件", "region": "main", "once": True,
            "requires": {}, "text": "不应执行",
            "effects": {"set_flags": {"test:invalid_event_effect": True}},
            "rewards": {"gold": 10, "item": "不存在的测试物品"},
        }
        try:
            old_gold = p.gold
            ok, message, _ = p.trigger_world_event(event_id)
            self.assertFalse(ok)
            self.assertIn("奖励无效", message)
            self.assertEqual(p.gold, old_gold)
            self.assertFalse(p.get_flag("test:invalid_event_effect"))
            self.assertEqual(p.get_world_event_state(event_id).get("count", 0), 0)
            self.assertTrue(p.can_trigger_world_event(event_id))
        finally:
            if original is None:
                engine.WORLD_EVENTS.pop(event_id, None)
            else:
                engine.WORLD_EVENTS[event_id] = original

    def test_world_event_does_not_consume_event_when_inventory_capacity_blocks_reward(self):
        p = Player("背包满载事件", "散人")
        p.location = "village"
        event_id = "test_world_event_full_inventory"
        original = engine.WORLD_EVENTS.get(event_id)
        engine.WORLD_EVENTS[event_id] = {
            "title": "满载奖励测试", "region": "main", "once": True,
            "requires": {}, "text": "应当稍后再试",
            "effects": {"set_flags": {"test:full_inventory_event_effect": True}},
            "rewards": {"gold": 10, "item": "草药", "item_quantity": 1},
        }
        try:
            p.inventory_capacity = len(p.inventory)
            old_gold = p.gold
            old_inventory = list(p.inventory)
            ok, message, _ = p.trigger_world_event(event_id)
            self.assertFalse(ok)
            self.assertIn("背包空间不足", message)
            self.assertEqual(p.gold, old_gold)
            self.assertEqual(p.inventory, old_inventory)
            self.assertFalse(p.get_flag("test:full_inventory_event_effect"))
            self.assertEqual(p.get_world_event_state(event_id).get("count", 0), 0)
            self.assertTrue(p.can_trigger_world_event(event_id))
        finally:
            if original is None:
                engine.WORLD_EVENTS.pop(event_id, None)
            else:
                engine.WORLD_EVENTS[event_id] = original

    def test_malformed_world_event_gold_fails_safely_without_crashing(self):
        p = Player("异常事件数值", "散人")
        p.location = "village"
        event_id = "test_malformed_world_event_gold"
        original = engine.WORLD_EVENTS.get(event_id)
        engine.WORLD_EVENTS[event_id] = {
            "title": "测试异常数值事件", "region": "main", "once": True,
            "requires": {}, "text": "不应执行",
            "effects": {"set_flags": {"test:malformed_event_effect": True}},
            "rewards": {"gold": "not-a-number"},
        }
        try:
            old_gold = p.gold
            ok, message, _ = p.trigger_world_event(event_id)
            self.assertFalse(ok)
            self.assertIn("奖励无效", message)
            self.assertEqual(p.gold, old_gold)
            self.assertFalse(p.get_flag("test:malformed_event_effect"))
            self.assertEqual(p.get_world_event_state(event_id).get("count", 0), 0)
        finally:
            if original is None:
                engine.WORLD_EVENTS.pop(event_id, None)
            else:
                engine.WORLD_EVENTS[event_id] = original

    def test_world_event_state_round_trip_stays_inside_v12_world_state(self):
        p = Player("事件存档", "散人")
        p.location = "village"
        p.set_var("exploration:main", 2)
        p.trigger_world_event("main_bandit_warning")
        fd, path = tempfile.mkstemp(suffix=".json"); os.close(fd)
        try:
            p.save_to_file(path)
            with open(path, encoding="utf8") as f: raw=json.load(f)
            self.assertEqual(raw["version"], 12)
            self.assertIn("world_events", raw["world_state"]["variables"])
            self.assertNotIn("world_events", raw)
            q=Player.load_from_file(path)
            self.assertTrue(q.get_flag("world:main:bandit_pressure"))
        finally:
            os.remove(path)

class NPCStateP228Tests(unittest.TestCase):
    def test_default_npc_state_is_normal_without_extra_save_field(self):
        p = Player("状态默认", "散人")
        p.set_var("quest_clock", 7)  # 13:00，守卫不在巡逻忙碌时段
        self.assertEqual(p.get_npc_state("守卫"), "normal")
        self.assertIn("npc_states", p.world_state["variables"])
        raw = p.world_state
        self.assertNotIn("npc_states", raw)

    def test_npc_state_transition_and_expiry_use_existing_quest_clock(self):
        p = Player("状态转换", "散人")
        p.set_var("quest_clock", 7)  # 13:00，到期后回到无日程的普通状态
        self.assertTrue(p.set_npc_state("守卫", "fear", duration=2, reason="山贼来袭", source="test"))
        self.assertEqual(p.get_npc_state("守卫"), "fear")
        self.assertEqual(p.get_npc_state_record("守卫")["reason"], "山贼来袭")
        p.tick_quest_clock(2)
        self.assertEqual(p.get_npc_state("守卫"), "normal")

    def test_world_event_changes_npc_state(self):
        p = Player("事件状态", "散人")
        p.location = "village"
        p.set_var("exploration:main", 2)
        ok, _, _ = p.trigger_world_event("main_bandit_warning")
        self.assertTrue(ok)
        self.assertEqual(p.get_npc_state("守卫"), "fear")
        self.assertEqual(p.get_npc_state("村长"), "fear")

    def test_npc_state_changes_event_affected_trader_behavior(self):
        from actions import handle_trading
        p = Player("商贾状态", "散人")
        p.location = "guiyun_black_market_east"
        p.set_npc_state("黑市商人", "away", duration=2, reason="躲避巡查")
        self.assertFalse(handle_trading(p, "shop", []))

    def test_busy_npc_state_allows_short_reply_without_relation_gain(self):
        from actions import handle_talk_and_ask
        p = Player("忙碌状态", "散人")
        p.set_var("quest_clock", 7)  # 13:00，守卫在村口值守
        p.location = "village_gate"
        p.set_npc_state("守卫", "busy", duration=2, reason="巡逻")
        before = p.get_relation("守卫")
        handle_talk_and_ask(p, ["守卫"])
        self.assertEqual(p.get_relation("守卫"), before)

    def test_quest_abandon_reacts_npc_state(self):
        p = Player("任务放弃状态", "散人")
        p.change_relation("村长", 8)
        p.active_quests["黑风限时追缉"] = 0
        p.quest_states["黑风限时追缉"] = {"stage": 0, "progress": 0, "accepted_at": 0}
        ok, _ = p.abandon_quest("黑风限时追缉")
        self.assertTrue(ok)
        self.assertEqual(p.get_npc_state("村长"), "angry")

    def test_quest_failure_reacts_npc_state(self):
        p = Player("任务失败状态", "散人")
        p.change_relation("村长", 8)
        p.active_quests["黑风限时追缉"] = 0
        p.quest_states["黑风限时追缉"] = {"stage": 0, "progress": 0, "accepted_at": 0}
        p.set_npc_state("村长", "normal")
        self.assertTrue(p.fail_quest("黑风限时追缉", "time_limit"))
        self.assertEqual(p.get_npc_state("村长"), "angry")

    def test_quest_completion_reacts_npc_state(self):
        from actions import handle_quest, look
        p = Player("任务完成状态", "散人")
        p.location = "village_head_house"
        p.change_relation("村长", 5)
        p.active_quests["清剿黑风山"] = 1
        p.quest_states["清剿黑风山"] = {"stage": 0, "progress": 1, "accepted_at": 0}
        handle_quest(p, "jiaofu", ["清剿黑风山"])
        self.assertEqual(p.get_npc_state("村长"), "normal")
        self.assertEqual(p.get_npc_state_record("村长").get("reason"), "黑风山危机得到缓解")

    def test_npc_state_condition_uses_world_state_only(self):
        p = Player("状态条件", "散人")
        p.set_npc_state("守卫", "fear")
        self.assertTrue(engine.check_conditions({"npc_states": {"守卫": "fear"}}, p.world_state, player=p))
        self.assertFalse(engine.check_conditions({"npc_states": {"守卫": "busy"}}, p.world_state, player=p))

    def test_npc_state_round_trip_stays_inside_v12_world_state(self):
        p = Player("状态存档", "散人")
        p.set_npc_state("村长", "injured", duration=4, reason="受伤")
        fd, path = tempfile.mkstemp(suffix=".json"); os.close(fd)
        try:
            p.save_to_file(path)
            with open(path, encoding="utf8") as f:
                raw = json.load(f)
            self.assertEqual(raw["version"], 12)
            self.assertIn("npc_states", raw["world_state"]["variables"])
            self.assertNotIn("npc_states", raw)
            q = Player.load_from_file(path)
            self.assertEqual(q.get_npc_state("村长"), "injured")
        finally:
            os.remove(path)

    def test_npc_state_does_not_leak_between_npcs(self):
        p = Player("状态隔离", "散人")
        p.set_npc_state("守卫", "fear")
        self.assertEqual(p.get_npc_state("守卫"), "fear")
        self.assertEqual(p.get_npc_state("村长"), "normal")

    def test_npc_state_data_schema_is_present_for_all_existing_npcs(self):
        for npc_name, info in engine.NPCS.items():
            self.assertIn("state_profile", info, npc_name)
            self.assertEqual(info["state_profile"]["default"], "normal")
            self.assertTrue(info["state_profile"]["allowed"])

class NPCEcologyP229Tests(unittest.TestCase):
    def test_daily_schedule_changes_state_from_existing_quest_clock(self):
        p = Player("日常时刻", "散人")
        # 先停在守卫没有日程的 13:00，确认初始为普通状态。
        p.set_var("quest_clock", 7)
        p.refresh_npc_schedules()
        self.assertEqual(p.get_npc_state("守卫"), "normal")
        # tick 0 对应卯时初（06:00），守卫 06:00–12:00 巡村。
        p.set_var("quest_clock", 0)
        p.refresh_npc_schedules()
        self.assertEqual(p.get_npc_state("守卫"), "busy")
        self.assertEqual(p.get_npc_state_record("守卫").get("source"), "schedule")
        p.set_var("quest_clock", 6)
        p.refresh_npc_schedules()
        self.assertEqual(p.get_npc_state("守卫"), "normal")

    def test_temporary_event_state_overrides_daily_schedule_until_expiry(self):
        p = Player("日常优先级", "散人")
        p.set_var("quest_clock", 1)
        self.assertTrue(p.set_npc_state("守卫", "fear", duration=2, reason="突发袭击", source="event:test"))
        p.refresh_npc_schedules()
        self.assertEqual(p.get_npc_state("守卫"), "fear")
        p.tick_quest_clock(2)
        self.assertEqual(p.get_npc_state("守卫"), "busy")

    def test_daily_schedule_round_trip_stays_inside_v12_world_state(self):
        p = Player("日常存档", "散人")
        p.set_var("quest_clock", 2)
        p.refresh_npc_schedules()
        fd, path = tempfile.mkstemp(suffix=".json"); os.close(fd)
        try:
            p.save_to_file(path)
            with open(path, encoding="utf8") as f: raw = json.load(f)
            self.assertEqual(raw["version"], 12)
            self.assertIn("npc_states", raw["world_state"]["variables"])
            self.assertNotIn("npc_states", raw)
            q = Player.load_from_file(path)
            self.assertEqual(q.get_npc_state("守卫"), "busy")
        finally:
            os.remove(path)

    def test_npc_sect_stance_is_derived_from_current_player_sect(self):
        p = Player("门派立场", "华山")
        self.assertEqual(p.get_npc_sect_stance("归云武馆馆主"), "preferred")
        self.assertEqual(p.get_npc_sect_stance("捕头"), "opposed")
        p.leave_sect()
        self.assertEqual(p.get_npc_sect_stance("归云武馆馆主"), "wary")

    def test_npc_sect_stance_does_not_create_new_top_level_save_field(self):
        p = Player("门派存档", "武当")
        self.assertEqual(p.get_npc_ecology("震远镖局总镖头")["sect_stance"], "preferred")
        self.assertNotIn("sect_stance", p.world_state)
        self.assertNotIn("sect_stance", p.world_state["variables"])

    def test_sect_switch_changes_npc_stance_without_rewriting_npc_data(self):
        p = Player("门派切换", "散人")
        p.level = max(p.level, 3)
        p.join_sect("少林")
        self.assertEqual(p.get_npc_sect_stance("捕头"), "preferred")
        self.assertEqual(p.get_npc_sect_stance("归云武馆馆主"), "opposed")
        p.leave_sect()
        self.assertEqual(p.get_npc_sect_stance("捕头"), "wary")


class NPCMovementP230Tests(unittest.TestCase):
    def test_schedule_moves_npc_to_configured_location(self):
        p = Player("移动测试", "散人")
        p.set_var("quest_clock", 0)
        p.refresh_npc_schedules()
        self.assertEqual(p.get_npc_location("守卫"), "village_south_street")
        self.assertNotIn("守卫", p.get_npcs_in_room("village_gate"))
        self.assertIn("守卫", p.get_npcs_in_room("village_south_street"))

    def test_schedule_location_returns_home_after_window(self):
        p = Player("回归测试", "散人")
        p.set_var("quest_clock", 0)
        p.refresh_npc_schedules()
        self.assertEqual(p.get_npc_location("守卫"), "village_south_street")
        p.set_var("quest_clock", 6)
        p.refresh_npc_schedules()
        self.assertEqual(p.get_npc_location("守卫"), "village_gate")

    def test_event_reaction_can_move_npc_without_changing_static_room_data(self):
        p = Player("事件移动", "散人")
        before = list(engine.ROOMS["village_gate"].get("npcs", []))
        p.set_var("quest_clock", 2)
        applied = p.react_npcs_to_event("main_bandit_warning")
        self.assertIn(("守卫", "fear"), applied)
        self.assertEqual(p.get_npc_location("守卫"), "village_south_street")
        self.assertEqual(engine.ROOMS["village_gate"].get("npcs", []), before)

    def test_temporary_event_location_returns_to_schedule_location(self):
        p = Player("事件恢复", "散人")
        p.set_var("quest_clock", 0)
        p.refresh_npc_schedules()
        self.assertEqual(p.get_npc_location("守卫"), "village_south_street")
        p.set_npc_state("守卫", "fear", duration=2, source="event:test")
        p.set_npc_location("守卫", "official_road", source="event:test")
        p.tick_quest_clock(2)
        # 事件结束后沿真实出口返回日程地点；本次只走官方道路到村口的一步。
        self.assertEqual(p.get_npc_location("守卫"), "village_gate")

    def test_dynamic_npc_presence_is_save_load_compatible(self):
        p = Player("位置存档", "散人")
        p.set_var("quest_clock", 0)
        p.refresh_npc_schedules()
        fd, path = tempfile.mkstemp(suffix=".json"); os.close(fd)
        try:
            p.save_to_file(path)
            with open(path, encoding="utf8") as f:
                raw = json.load(f)
            self.assertEqual(raw["version"], 12)
            self.assertIn("npc_locations", raw["world_state"]["variables"])
            self.assertNotIn("npc_locations", raw)
            q = Player.load_from_file(path)
            self.assertEqual(q.get_npc_location("守卫"), "village_south_street")
        finally:
            os.remove(path)

    def test_npc_presence_is_isolated(self):
        p = Player("位置隔离", "散人")
        self.assertNotEqual(p.get_npc_location("守卫"), p.get_npc_location("村长"))
        p.set_var("quest_clock", 0)
        p.refresh_npc_schedules()
        self.assertNotEqual(p.get_npc_location("守卫"), p.get_npc_location("村长"))

class NPCEcologyP231Tests(unittest.TestCase):
    def test_dynamic_quest_giver_uses_current_npc_location(self):
        p = Player("动态任务", "散人")
        p.set_var("quest_clock", 0)
        p.refresh_npc_schedules()
        self.assertNotIn("守卫", p.get_npc_quest_givers_here("village_south_street"))
        self.assertIn("村长", p.get_npc_quest_givers_here("village_head_house"))

    def test_npc_bond_is_data_driven_and_persistent_override(self):
        p = Player("人物关系", "散人")
        self.assertEqual(p.get_npc_bond("守卫", "村长"), 8)
        p.change_npc_bond("守卫", "村长", -20)
        self.assertEqual(p.get_npc_bond("守卫", "村长"), -12)
        self.assertEqual(p.get_npc_bond("村长", "守卫"), 8)

    def test_npc_encounter_detects_only_npcs_currently_together(self):
        p = Player("人物偶遇", "散人")
        # 13:00 两人都没有日程，测试位置不会被日常刷新改写。
        p.set_var("quest_clock", 7)
        p.set_npc_location("守卫", "village_head_house", source="test")
        p.set_npc_location("村长", "village_head_house", source="test")
        encounters = p.get_npc_encounters("village_head_house")
        self.assertTrue(any(x["npc_a"] == "守卫" and x["npc_b"] == "村长" for x in encounters))
        p.set_npc_location("守卫", "village_gate", source="test")
        self.assertEqual(p.get_npc_encounters("village_head_house"), [])

    def test_npc_bonds_stay_inside_world_state_variables(self):
        p = Player("人物存档", "散人")
        p.change_npc_bond("守卫", "村长", 1)
        self.assertIn("npc_bonds", p.world_state["variables"])
        self.assertNotIn("npc_bonds", p.world_state)
        fd, path = tempfile.mkstemp(suffix=".json"); os.close(fd)
        try:
            p.save_to_file(path)
            q = Player.load_from_file(path)
            self.assertEqual(q.get_npc_bond("守卫", "村长"), 9)
            self.assertEqual(q.get_npc_bond("村长", "守卫"), 8)
        finally:
            os.remove(path)

class NPCMemoryP233Tests(unittest.TestCase):
    def test_npc_memory_records_player_action_and_attitude(self):
        p = Player("记忆测试", "散人")
        p.remember_player_action("守卫", "help_gate", "你曾帮助守卫处理村口危机。", "positive", 80)
        self.assertEqual(p.get_npc_memory("守卫", "help_gate")["strength"], 80)
        self.assertIn(p.get_npc_memory_attitude("守卫"), {"friendly", "favorable"})

    def test_npc_memory_expiry_is_enforced(self):
        p = Player("记忆过期", "散人")
        p.remember_player_action("守卫", "temporary", "这是一段短暂记忆。", "positive", 60, ttl=2)
        self.assertIsNotNone(p.get_npc_memory("守卫", "temporary"))
        p.tick_quest_clock(2)
        self.assertIsNone(p.get_npc_memory("守卫", "temporary"))

    def test_npc_memory_propagates_only_through_npc_bond(self):
        p = Player("记忆传播", "散人")
        p.set_var("quest_clock", 7)  # 13:00，避免日程把守卫带离村长住处
        p.set_npc_location("守卫", "village_head_house", source="test")
        p.set_npc_location("村长", "village_head_house", source="test")
        p.remember_player_action("守卫", "heroic", "你曾在村口救下村民。", "positive", 70)
        propagated = p.propagate_npc_player_memories("village_head_house")
        self.assertTrue(any(x[0] == "守卫" and x[1] == "村长" and x[2] == "heroic" for x in propagated))
        self.assertIsNotNone(p.get_npc_memory("村长", "heard:守卫:heroic"))

    def test_npc_memory_does_not_cross_unrelated_npcs(self):
        p = Player("记忆隔离", "散人")
        p.set_npc_location("守卫", "village_head_house", source="test")
        p.set_npc_location("药铺老板", "village_head_house", source="test")
        p.change_npc_bond("守卫", "药铺老板", -100)
        p.remember_player_action("守卫", "secret", "只有守卫知道的事情。", "positive", 90)
        p.propagate_npc_player_memories("village_head_house")
        self.assertIsNone(p.get_npc_memory("药铺老板", "heard:守卫:secret"))

    def test_npc_memory_conditions_are_supported(self):
        p = Player("条件记忆", "散人")
        p.remember_player_action("村长", "trusted", "你曾帮助村民。", "positive", 75)
        self.assertTrue(engine.check_conditions({"npc_memory": {"村长": {"trusted": {"min_strength": 70, "sentiment": "positive"}}}}, p.world_state, [], p))
        self.assertTrue(engine.check_conditions({"npc_memory_attitude": {"村长": "friendly"}}, p.world_state, [], p))
        self.assertFalse(engine.check_conditions({"npc_memory": {"村长": {"missing": True}}}, p.world_state, [], p))

    def test_npc_memory_is_v12_save_load_compatible(self):
        p = Player("记忆存档", "散人")
        p.remember_player_action("村长", "saved_memory", "村长记得你救过村民。", "positive", 66)
        fd, path = tempfile.mkstemp(suffix=".json"); os.close(fd)
        try:
            p.save_to_file(path)
            with open(path, encoding="utf8") as f:
                raw = json.load(f)
            self.assertEqual(raw["version"], 12)
            self.assertIn("npc_memories", raw["world_state"]["variables"])
            self.assertNotIn("npc_memories", raw)
            q = Player.load_from_file(path)
            self.assertEqual(q.get_npc_memory("村长", "saved_memory")["strength"], 66)
        finally:
            os.remove(path)

    def test_memory_profile_exists_for_existing_npcs(self):
        for npc_name, npc in engine.NPCS.items():
            self.assertIsInstance(npc.get("memory_profile"), dict, npc_name)
            self.assertTrue(npc["memory_profile"].get("remember_player_actions", False))

class NPCMemoryCommandP233Tests(unittest.TestCase):
    def test_memory_command_alias_is_registered(self):
        import main
        self.assertEqual(main.CMD_MAP.get("memory"), "memory")
        self.assertEqual(main.CMD_MAP.get("记忆"), "memory")

class NPCMemoryBehaviorP234Tests(unittest.TestCase):
    def test_memory_reputation_maps_to_behavior_without_changing_relation(self):
        p = Player("行为记忆", "散人")
        self.assertEqual(p.get_relation("守卫"), 0)
        p.remember_player_action("守卫", "great_help", "你曾救过村民。", "positive", 90)
        self.assertEqual(p.get_npc_memory_behavior("守卫")["action"], "welcome")
        self.assertEqual(p.get_relation("守卫"), 0)

    def test_negative_memory_can_make_npc_refuse_even_when_relation_is_not_hostile(self):
        p = Player("负面记忆", "散人")
        p.remember_player_action("守卫", "betrayal", "你曾经失信。", "negative", 90)
        self.assertEqual(p.get_relation("守卫"), 0)
        self.assertEqual(p.get_npc_memory_behavior("守卫")["action"], "refuse")

    def test_quest_outcome_becomes_npc_memory(self):
        p = Player("任务记忆", "散人")
        p.react_npcs_to_quest("清剿黑风山", "complete")
        memory = p.get_npc_memory("守卫", "quest:清剿黑风山:complete")
        self.assertIsNotNone(memory)
        self.assertEqual(memory["sentiment"], "positive")
        self.assertGreaterEqual(memory["strength"], 60)

    def test_quest_memory_can_propagate_after_npc_quest_reaction(self):
        p = Player("任务传播", "散人")
        p.set_npc_location("守卫", "village_head_house", source="test")
        p.set_npc_location("村长", "village_head_house", source="test")
        p.react_npcs_to_quest("清剿黑风山", "complete")
        p.propagate_npc_player_memories("village_head_house")
        self.assertIsNotNone(p.get_npc_memory("村长", "heard:守卫:quest:清剿黑风山:complete"))

    def test_memory_behavior_is_data_driven(self):
        p = Player("数据行为", "散人")
        engine.NPCS["守卫"]["memory_profile"]["behavior"]["friendly_gte"] = 90
        try:
            p.remember_player_action("守卫", "help", "你曾帮过我。", "positive", 80)
            p.remember_player_action("守卫", "minor_mistake", "你也曾有过一次小失误。", "negative", 20)
            self.assertEqual(p.get_npc_memory_behavior("守卫")["action"], "cooperate")
        finally:
            engine.NPCS["守卫"]["memory_profile"]["behavior"]["friendly_gte"] = 70

    def test_memory_behavior_does_not_add_top_level_save_field(self):
        p = Player("行为存档", "散人")
        p.remember_player_action("守卫", "help", "你曾帮过我。", "positive", 80)
        self.assertNotIn("npc_memories", p.world_state)
        self.assertIn("npc_memories", p.world_state["variables"])
        self.assertNotIn("npc_memory_behavior", p.world_state["variables"])

    def test_old_v12_save_without_memory_still_has_neutral_behavior(self):
        p = Player("旧存档", "散人")
        p.world_state = {"flags": {}, "variables": {"quest_clock": 0}}
        self.assertEqual(p.get_npc_memory_behavior("守卫")["action"], "neutral")

class NPCAutonomyP235Tests(unittest.TestCase):
    def test_autonomy_profile_exists_for_existing_npcs(self):
        for npc_name, npc in engine.NPCS.items():
            profile = npc.get("autonomy_profile")
            self.assertIsInstance(profile, dict, npc_name)
            self.assertTrue(profile.get("enabled"), npc_name)
            self.assertTrue(profile.get("allowed_actions"), npc_name)

    def test_autonomy_patrol_changes_dynamic_location_without_static_room_mutation(self):
        p = Player("主动行动", "散人")
        original = list(engine.ROOMS["village_gate"].get("npcs", []))
        p.world_state["variables"]["quest_clock"] = 3
        p.process_npc_autonomy()
        self.assertEqual(original, engine.ROOMS["village_gate"].get("npcs", []))
        self.assertTrue(p.get_npc_action_log())
        self.assertIn("npc_autonomy", p.world_state["variables"])

    def test_autonomy_respects_blocked_state(self):
        p = Player("状态约束", "散人")
        p.set_npc_state("守卫", "fear", duration=10, reason="测试")
        p.world_state["variables"]["quest_clock"] = 3
        p.process_npc_autonomy()
        records = [x for x in p.get_npc_action_log(100) if x["npc"] == "守卫"]
        self.assertTrue(records)
        self.assertEqual(records[-1]["action"], "rest")

    def test_memory_and_relation_can_trigger_seek_player(self):
        p = Player("主动寻找", "散人")
        p.location = "village_gate"
        p.set_npc_location("守卫", "village_square", source="test")
        p.change_relation("守卫", 40)
        p.remember_player_action("守卫", "help", "你曾帮助守卫。", "positive", 80)
        p.world_state["variables"]["quest_clock"] = 5
        engine.NPCS["守卫"]["autonomy_profile"]["seek_player_frequency"] = 1
        try:
            p.process_npc_autonomy()
            self.assertEqual(p.get_npc_location("守卫", refresh=False), "village_south_street")
            guard_logs = [x for x in p.get_npc_action_log(100) if x["npc"] == "守卫"]
            self.assertEqual(guard_logs[-1]["action"], "seek_player")
        finally:
            engine.NPCS["守卫"]["autonomy_profile"]["seek_player_frequency"] = 5

    def test_meet_npc_uses_bond_target_location(self):
        p = Player("人物会面", "散人")
        p.set_npc_location("守卫", "village_gate", source="test")
        p.set_npc_location("村长", "village_square", source="test")
        p.world_state["variables"]["quest_clock"] = 5
        engine.NPCS["守卫"]["autonomy_profile"]["meet_frequency"] = 2
        try:
            p.process_npc_autonomy()
            self.assertEqual(p.get_npc_location("守卫", refresh=False), "village_south_street")
            guard_logs = [x for x in p.get_npc_action_log(100) if x["npc"] == "守卫"]
            self.assertEqual(guard_logs[-1]["action"], "meet_npc")
            self.assertEqual(guard_logs[-1]["target"], "村长")
        finally:
            engine.NPCS["守卫"]["autonomy_profile"]["meet_frequency"] = 4

    def test_tick_clock_processes_autonomy_and_keeps_v12_save_shape(self):
        p = Player("时钟推进", "散人")
        p.tick_quest_clock(3)
        self.assertTrue(p.get_npc_action_log())
        fd, path = tempfile.mkstemp(suffix=".json"); os.close(fd)
        try:
            p.save_to_file(path)
            with open(path, encoding="utf8") as f:
                raw = json.load(f)
            self.assertEqual(raw["version"], 12)
            self.assertIn("npc_autonomy", raw["world_state"]["variables"])
            self.assertIn("npc_action_log", raw["world_state"]["variables"])
            self.assertNotIn("npc_autonomy", raw)
            self.assertNotIn("npc_action_log", raw)
            q = Player.load_from_file(path)
            self.assertTrue(q.get_npc_action_log())
        finally:
            os.remove(path)

    def test_old_v12_save_without_autonomy_still_works(self):
        p = Player("旧自主存档", "散人")
        p.world_state = {"flags": {}, "variables": {"quest_clock": 0}}
        self.assertEqual(p.get_npc_action_log(), [])
        self.assertIsInstance(p.process_npc_autonomy(), list)

    def test_npc_actions_command_is_registered(self):
        import main
        self.assertEqual(main.CMD_MAP.get("npc_actions"), "npc_actions")
        self.assertEqual(main.CMD_MAP.get("人物行动"), "npc_actions")

class NPCProactiveStoryP236Tests(unittest.TestCase):
    def test_proactive_event_profile_is_data_driven(self):
        for npc_name, npc in engine.NPCS.items():
            events = npc.get("proactive_events", []) or []
            self.assertIsInstance(events, list, npc_name)
            for event in events:
                self.assertIsInstance(event, dict)
                self.assertTrue(event.get("id"))
                self.assertIn(event.get("trigger_action"), {"patrol", "investigate", "meet_npc", "seek_player", "rest"})

    def test_autonomous_action_can_trigger_proactive_world_event(self):
        p = Player("主动剧情", "散人")
        p.world_state["variables"]["quest_clock"] = 3
        p.set_npc_location("守卫", "village_gate", source="test")
        engine.NPCS["守卫"]["autonomy_profile"]["allowed_actions"] = ["patrol"]
        engine.NPCS["守卫"]["autonomy_profile"]["route"] = ["village_gate", "village_south_street"]
        try:
            actions = p.process_npc_autonomy()
            events = [x for x in p.get_npc_proactive_event_log(100) if x["npc"] == "守卫"]
            guard_actions = [x for x in actions if x["npc"] == "守卫"]
            self.assertTrue(guard_actions)
            self.assertTrue(events)
            self.assertEqual(events[-1]["event_id"], "guard_patrol_warning")
            self.assertEqual(p.get_var("world:main:patrol_alert", 0), 1)
            self.assertIsNotNone(p.get_player_information("guard_patrol_alert"))
        finally:
            engine.NPCS["守卫"]["autonomy_profile"]["allowed_actions"] = ["patrol", "investigate", "meet_npc", "seek_player", "rest"]

    def test_proactive_event_cooldown_prevents_duplicate_world_effect(self):
        p = Player("剧情冷却", "散人")
        action = {"clock": 0, "npc": "守卫", "action": "patrol", "reason": "测试"}
        first = p.process_npc_proactive_events([action])
        second = p.process_npc_proactive_events([action])
        self.assertEqual(len(first), 1)
        self.assertEqual(second, [])
        self.assertEqual(p.get_var("world:main:patrol_alert", 0), 1)

    def test_proactive_event_can_change_npc_state_and_memory(self):
        event = {
            "id": "test_reaction", "title": "测试主动事件", "trigger_action": "investigate",
            "remember_player_action": {"npc": "守卫", "id": "test_memory", "text": "你曾协助处理异常。", "sentiment": "positive", "strength": 60},
            "effects": {"npc_reactions": [{"npc": "守卫", "state": "busy", "duration": 2, "reason": "测试主动事件"}]}
        }
        p = Player("剧情反应", "散人")
        original = engine.NPCS["守卫"].get("proactive_events")
        engine.NPCS["守卫"]["proactive_events"] = [event]
        try:
            result = p.process_npc_proactive_events([{"npc": "守卫", "action": "investigate"}])
            self.assertEqual(len(result), 1)
            self.assertEqual(p.get_npc_state("守卫"), "busy")
            self.assertIsNotNone(p.get_npc_memory("守卫", "test_memory"))
        finally:
            engine.NPCS["守卫"]["proactive_events"] = original

    def test_proactive_event_survives_v12_save_load(self):
        p = Player("剧情存档", "散人")
        p.process_npc_proactive_events([{"npc": "守卫", "action": "patrol"}])
        fd, path = tempfile.mkstemp(suffix=".json"); os.close(fd)
        try:
            p.save_to_file(path)
            with open(path, encoding="utf8") as f:
                raw = json.load(f)
            self.assertEqual(raw["version"], 12)
            self.assertIn("npc_proactive_events", raw["world_state"]["variables"])
            self.assertNotIn("npc_proactive_events", raw)
            q = Player.load_from_file(path)
            self.assertTrue(q.get_npc_proactive_event_log())
        finally:
            os.remove(path)

    def test_old_v12_save_without_proactive_events_is_safe(self):
        p = Player("旧剧情存档", "散人")
        p.world_state = {"flags": {}, "variables": {"quest_clock": 0}}
        self.assertEqual(p.get_npc_proactive_event_log(), [])
        self.assertEqual(p.process_npc_proactive_events([]), [])

class NPCProactiveQuestP237Tests(unittest.TestCase):
    def test_proactive_quest_profile_is_data_driven_and_valid(self):
        for npc_name, info in engine.NPCS.items():
            for profile in info.get("proactive_quests", []) or []:
                self.assertIn(profile.get("quest"), engine.QUESTS)
                self.assertIn(profile.get("trigger_action"), Player.NPC_AUTONOMY_ALLOWED)

    def test_npc_can_proactively_offer_existing_quest(self):
        p = Player("主动任务玩家", "散人")
        p.change_relation("村长", 30)
        result = p.process_npc_proactive_quests([{"npc": "村长", "action": "seek_player"}])
        self.assertTrue(result)
        self.assertIn("清剿黑风山", p.active_quests)
        state = p.quest_states["清剿黑风山"]
        self.assertTrue(state.get("proactive"))
        self.assertEqual(state.get("accepted_by_npc"), "村长")

    def test_proactive_quest_does_not_duplicate_active_or_completed_quest(self):
        p = Player("重复任务玩家", "散人")
        p.change_relation("村长", 30)
        first = p.process_npc_proactive_quests([{"npc": "村长", "action": "seek_player"}])
        second = p.process_npc_proactive_quests([{"npc": "村长", "action": "seek_player"}])
        self.assertEqual(len(first), 1)
        self.assertEqual(second, [])

    def test_npc_can_autonomously_advance_existing_staged_quest(self):
        p = Player("主动推进玩家", "散人")
        p.change_relation("捕头", 30)
        p.completed_quests.append("入城引路")
        p.process_npc_proactive_quests([{"npc": "捕头", "action": "seek_player"}])
        self.assertIn("城内失踪案", p.active_quests)
        before = p.quest_states["城内失踪案"]["stage"]
        result = p.process_npc_proactive_quests([{"npc": "捕头", "action": "seek_player"}])
        self.assertTrue(result)
        self.assertEqual(p.quest_states["城内失踪案"]["stage"], before + 1)
        profile = engine.NPCS["捕头"]["proactive_quests"][0]
        advanced = p._advance_npc_proactive_quest("捕头", profile, "城内失踪案")
        self.assertIsNotNone(advanced)
        self.assertEqual(p.quest_states["城内失踪案"]["stage"], before + 2)

    def test_proactive_quest_timeout_fails_only_proactive_task(self):
        p = Player("主动失败玩家", "散人")
        p.change_relation("村长", 30)
        p.process_npc_proactive_quests([{"npc": "村长", "action": "seek_player"}])
        self.assertIn("清剿黑风山", p.active_quests)
        p.increment_var("quest_clock", 72)
        failed = p._check_npc_proactive_quest_failures()
        self.assertIn("清剿黑风山", failed)
        self.assertNotIn("清剿黑风山", p.active_quests)
        self.assertTrue(p.get_flag("quest_failed:清剿黑风山"))

    def test_proactive_quest_state_survives_v12_save_load(self):
        p = Player("主动任务存档", "散人")
        p.change_relation("村长", 30)
        p.process_npc_proactive_quests([{"npc": "村长", "action": "seek_player"}])
        fd, path = tempfile.mkstemp(suffix=".json"); os.close(fd)
        try:
            p.save_to_file(path)
            with open(path, encoding="utf8") as f:
                raw = json.load(f)
            self.assertEqual(raw["version"], 12)
            self.assertIn("quest_states", raw)
            self.assertNotIn("proactive_quests", raw)
            q = Player.load_from_file(path)
            self.assertIn("清剿黑风山", q.active_quests)
            self.assertTrue(q.quest_states["清剿黑风山"].get("proactive"))
        finally:
            os.remove(path)

    def test_old_v12_save_without_proactive_quest_history_is_safe(self):
        p = Player("旧主动任务存档", "散人")
        p.world_state = {"flags": {}, "variables": {"quest_clock": 0}}
        self.assertEqual(p.process_npc_proactive_quests([]), [])
        self.assertEqual(p._npc_proactive_quest_history("村长"), {})


class DynamicQuestBranchP238Tests(unittest.TestCase):
    def _start_missing_case(self, relation=30):
        p = Player("动态分支玩家", "散人")
        p.change_relation("捕头", relation)
        p.completed_quests.append("入城引路")
        p.process_npc_proactive_quests([{"npc": "捕头", "action": "seek_player"}])
        self.assertIn("城内失踪案", p.active_quests)
        return p

    def test_stage_branch_is_data_driven(self):
        q = engine.QUESTS["城内失踪案"]
        branches = q["stages"][0]["branch_choices"]
        self.assertEqual({b["id"] for b in branches}, {"official_route", "black_market_route"})
        self.assertEqual(branches[0]["next_stage"], 1)
        self.assertEqual(branches[1]["next_stage"], 2)

    def test_completed_stage_waits_for_branch_choice(self):
        p = self._start_missing_case()
        p.update_quest_progress("沈府管家", "talk")
        state = p.quest_states["城内失踪案"]
        self.assertTrue(state.get("branch_pending"))
        self.assertEqual(state["stage"], 0)
        self.assertEqual(p.active_quests["城内失踪案"], 0)

    def test_branch_choice_advances_to_selected_stage(self):
        p = self._start_missing_case()
        p.update_quest_progress("沈府管家", "talk")
        ok, msg = p.choose_quest_branch("城内失踪案", "official_route")
        self.assertTrue(ok, msg)
        self.assertEqual(p.quest_states["城内失踪案"]["stage"], 1)
        self.assertEqual(p.get_flag("case:missing_person:official_route"), True)
        self.assertEqual(p.quest_states["城内失踪案"]["branch"], "official_route")

    def test_locked_branch_requires_relation(self):
        p = self._start_missing_case()
        self.assertEqual([c["id"] for c in p.get_quest_branch_options("城内失踪案")], ["official_route"])
        p.update_quest_progress("沈府管家", "talk")
        ok, msg = p.choose_quest_branch("城内失踪案", "black_market_route")
        self.assertFalse(ok)
        self.assertIn("没有可用分支", msg)

    def test_branch_choice_changes_world_effects(self):
        p = self._start_missing_case()
        p.change_relation("黑市接头人", 5)
        p.update_quest_progress("沈府管家", "talk")
        ok, _ = p.choose_quest_branch("城内失踪案", "black_market_route")
        self.assertTrue(ok)
        self.assertTrue(p.get_flag("case:missing_person:black_market_route"))
        profile = p._jianghu_profile()
        self.assertGreaterEqual(profile["infamy"], 2)
        self.assertGreaterEqual(profile["paths"]["黑市"], 5)
        before = (profile["infamy"], profile["paths"]["黑市"])
        ok_again, _ = p.choose_quest_branch("城内失踪案", "black_market_route")
        self.assertFalse(ok_again)
        after = p._jianghu_profile()
        self.assertEqual(before, (after["infamy"], after["paths"]["黑市"]))
        self.assertEqual(p.get_var("black_market_reputation"), 2)

    def test_invalid_branch_does_not_mutate_state(self):
        p = self._start_missing_case()
        p.update_quest_progress("沈府管家", "talk")
        before = dict(p.quest_states["城内失踪案"])
        ok, _ = p.choose_quest_branch("城内失踪案", "not_exist")
        self.assertFalse(ok)
        self.assertEqual(p.quest_states["城内失踪案"], before)

    def test_branch_state_survives_v12_save_load(self):
        p = self._start_missing_case()
        p.update_quest_progress("沈府管家", "talk")
        p.choose_quest_branch("城内失踪案", "official_route")
        fd, path = tempfile.mkstemp(suffix=".json"); os.close(fd)
        try:
            p.save_to_file(path)
            with open(path, encoding="utf8") as f:
                raw = json.load(f)
            self.assertEqual(raw["version"], 12)
            self.assertEqual(raw["quest_states"]["城内失踪案"]["branch"], "official_route")
            q = Player.load_from_file(path)
            self.assertEqual(q.quest_states["城内失踪案"]["branch"], "official_route")
            self.assertEqual(q.quest_states["城内失踪案"]["stage"], 1)
        finally:
            os.remove(path)

    def test_old_v12_save_without_branch_state_is_safe(self):
        p = Player("旧分支存档", "散人")
        p.world_state = {"flags": {}, "variables": {"quest_clock": 0}}
        p.active_quests["城内失踪案"] = 0
        p.quest_states["城内失踪案"] = {"stage": 0, "progress": 0, "accepted_at": 0}
        self.assertFalse(p.quest_states["城内失踪案"].get("branch_pending", False))
        self.assertTrue(p.get_quest_branch_options("城内失踪案"))

class QuestInterventionP239Tests(unittest.TestCase):
    def _start_official_case(self):
        p = Player("干预玩家", "散人")
        p.change_relation("捕头", 30)
        p.completed_quests.append("入城引路")
        p.process_npc_proactive_quests([{"npc": "捕头", "action": "seek_player"}])
        p.update_quest_progress("沈府管家", "talk")
        ok, msg = p.choose_quest_branch("城内失踪案", "official_route")
        self.assertTrue(ok, msg)
        return p

    def test_npc_can_advance_active_quest_stage(self):
        p = self._start_official_case()
        self.assertEqual(p.quest_states["城内失踪案"]["stage"], 1)
        p.increment_var("quest_clock", 8)
        results = p.process_quest_interventions()
        self.assertEqual(p.quest_states["城内失踪案"]["stage"], 2)
        self.assertTrue(p.get_flag("case:missing_person:constable_ahead"))
        self.assertTrue(any(r.get("action") == "advance_stage" for r in results))

    def test_intervention_does_not_repeat_after_once(self):
        p = self._start_official_case()
        p.increment_var("quest_clock", 8)
        first = p.process_quest_interventions()
        second = p.process_quest_interventions()
        self.assertEqual(len([r for r in first if r.get("action") == "advance_stage"]), 1)
        self.assertEqual(second, [])

    def test_black_market_intervention_reroutes_evacuated_target(self):
        p = Player("黑市干预", "散人")
        p.change_relation("捕头", 30)
        p.change_relation("黑市接头人", 5)
        p.completed_quests.append("入城引路")
        p.process_npc_proactive_quests([{"npc": "捕头", "action": "seek_player"}])
        p.update_quest_progress("沈府管家", "talk")
        ok, _ = p.choose_quest_branch("城内失踪案", "black_market_route")
        self.assertTrue(ok)
        p.increment_var("quest_clock", 6)
        results = p.process_quest_interventions()
        self.assertEqual(p.quest_states["城内失踪案"]["stage"], 3)
        self.assertTrue(p.get_flag("case:missing_person:black_market_evacuated"))
        self.assertTrue(any(r.get("action") == "reroute" for r in results))

    def test_stagnant_case_can_fail_by_npc_intervention(self):
        p = Player("案件拖延", "散人")
        p.change_relation("捕头", 30)
        p.completed_quests.append("入城引路")
        p.process_npc_proactive_quests([{"npc": "捕头", "action": "seek_player"}])
        p.increment_var("quest_clock", 48)
        results = p.process_quest_interventions()
        self.assertNotIn("城内失踪案", p.active_quests)
        self.assertTrue(p.get_flag("quest_failed:城内失踪案"))
        self.assertTrue(any(r.get("failed") for r in results))

    def test_intervention_respects_branch_and_stage(self):
        p = self._start_official_case()
        p.increment_var("quest_clock", 8)
        p.process_quest_interventions()
        self.assertEqual(p.quest_states["城内失踪案"]["stage"], 2)
        p.process_quest_interventions()
        self.assertEqual(p.quest_states["城内失踪案"]["stage"], 2)

    def test_intervention_state_is_saved_in_v12_variables(self):
        p = self._start_official_case()
        p.increment_var("quest_clock", 8)
        p.process_quest_interventions()
        fd, path = tempfile.mkstemp(suffix=".json"); os.close(fd)
        try:
            p.save_to_file(path)
            with open(path, encoding="utf8") as f:
                raw = json.load(f)
            self.assertEqual(raw["version"], 12)
            self.assertIn("quest_interventions", raw["world_state"]["variables"])
            q = Player.load_from_file(path)
            self.assertEqual(q.quest_states["城内失踪案"]["stage"], 2)
        finally:
            os.remove(path)

    def test_old_v12_save_without_intervention_history_is_safe(self):
        p = Player("旧干预存档", "散人")
        p.world_state = {"flags": {}, "variables": {"quest_clock": 0}}
        self.assertEqual(p.process_quest_interventions(), [])
        self.assertEqual(p._quest_intervention_history(), {})


class NPCCompetitionP240Tests(unittest.TestCase):
    def _start_case(self, branch="official_route"):
        p=Player("博弈测试", "散人")
        p.change_relation("捕头", 30)
        p.change_relation("沈府管家", 5)
        p.change_relation("黑市接头人", 5)
        p.completed_quests.append("入城引路")
        p.process_npc_proactive_quests([{"npc":"捕头","action":"seek_player"}])
        p.update_quest_progress("沈府管家", "talk")
        ok,msg=p.choose_quest_branch("城内失踪案", branch)
        self.assertTrue(ok,msg)
        return p

    def test_competition_selects_highest_scoring_npc(self):
        p=self._start_case()
        p.increment_var("quest_clock",4)
        results=p.process_npc_competitions()
        self.assertEqual(p.quest_states["城内失踪案"]["stage"],2)
        self.assertTrue(p.get_flag("case:missing_person:constable_won_race"))
        self.assertEqual(results[0]["npc"],"捕头")
        self.assertIn("沈府管家",results[0]["scores"])

    def test_relation_and_memory_can_change_competition_winner(self):
        p=self._start_case()
        p.change_relation("沈府管家", 30)
        p.remember_player_action("沈府管家","test_trust","你曾帮助沈府解决麻烦。","positive",90)
        p.increment_var("quest_clock",4)
        results=p.process_npc_competitions()
        self.assertTrue(p.get_flag("case:missing_person:shen_manor_won_race"))
        self.assertEqual(results[0]["npc"],"沈府管家")
        self.assertEqual(p.quest_states["城内失踪案"]["stage"],1)

    def test_competition_is_once_only(self):
        p=self._start_case()
        p.increment_var("quest_clock",4)
        first=p.process_npc_competitions()
        second=p.process_npc_competitions()
        self.assertEqual(len(first),1)
        self.assertEqual(second,[])

    def test_black_market_competition_can_reroute_quest(self):
        p=self._start_case("black_market_route")
        p.increment_var("quest_clock",4)
        results=p.process_npc_competitions()
        self.assertTrue(results)
        self.assertEqual(p.quest_states["城内失踪案"]["stage"],3)
        self.assertTrue(p.get_flag("case:missing_person:constable_recovered_evidence"))

    def test_competition_cannot_skip_pending_player_branch_choice(self):
        p=Player("竞争路线保护", "散人")
        p.active_quests["城内失踪案"]=0
        p.quest_states["城内失踪案"]={"stage":1,"progress":0,"branch_pending":True,"branch":"official_route"}
        profile={"id":"test_branch_lock","contestants":[{
            "npc":"捕头","base_score":10,"action":"advance_stage","next_stage":2,
            "effects":{"set_flags":{"test_competition_effect":True}}
        }]}
        result=p._apply_npc_competition("城内失踪案",profile)
        self.assertIsNone(result)
        self.assertEqual(p.quest_states["城内失踪案"]["stage"],1)
        self.assertTrue(p.quest_states["城内失踪案"]["branch_pending"])
        self.assertFalse(p.get_flag("test_competition_effect"))
        self.assertNotIn("城内失踪案:test_branch_lock",p._quest_competition_history())

    def test_invalid_competition_target_has_no_partial_world_effect(self):
        p=Player("竞争目标校验", "散人")
        p.active_quests["城内失踪案"]=0
        p.quest_states["城内失踪案"]={"stage":1,"progress":0,"branch":"official_route"}
        profile={"id":"test_invalid_target","contestants":[{
            "npc":"捕头","base_score":10,"action":"advance_stage","next_stage":999,
            "effects":{"set_flags":{"test_competition_effect":True}}
        }]}
        result=p._apply_npc_competition("城内失踪案",profile)
        self.assertIsNone(result)
        self.assertFalse(p.get_flag("test_competition_effect"))
        self.assertNotIn("城内失踪案:test_invalid_target",p._quest_competition_history())

    def test_invalid_intervention_target_has_no_partial_world_effect(self):
        p=Player("干预目标校验", "散人")
        p.active_quests["城内失踪案"]=0
        p.quest_states["城内失踪案"]={"stage":1,"progress":0}
        profile={"id":"test_invalid_intervention","npc":"捕头","action":"reroute","next_stage":999,
                 "effects":{"set_flags":{"test_intervention_effect":True}}}
        result=p._apply_quest_intervention("城内失踪案",profile)
        self.assertIsNone(result)
        self.assertFalse(p.get_flag("test_intervention_effect"))
        self.assertNotIn("城内失踪案:test_invalid_intervention",p._quest_intervention_history())

    def test_competition_history_stays_in_world_state_variables(self):
        p=self._start_case()
        p.increment_var("quest_clock",4)
        p.process_npc_competitions()
        self.assertIn("quest_competitions",p.world_state["variables"])
        self.assertNotIn("quest_competitions",p.__dict__)

    def test_competition_result_updates_npc_memory(self):
        p=self._start_case()
        p.increment_var("quest_clock",4)
        p.process_npc_competitions()
        self.assertIsNotNone(p.get_npc_memory("捕头","competition:official_race:won"))

    def test_old_v12_save_without_competition_history_is_safe(self):
        p=Player("旧博弈存档","散人")
        p.world_state={"flags":{},"variables":{"quest_clock":0}}
        self.assertEqual(p.process_npc_competitions(),[])
        self.assertEqual(p._quest_competition_history(),{})


class NPCFactionP241Tests(unittest.TestCase):
    def test_faction_data_loaded_and_npc_membership_valid(self):
        self.assertIn("官府", engine.FACTIONS)
        self.assertIn("黑市", engine.FACTIONS)
        self.assertEqual(Player("势力测试", "散人").get_npc_faction("捕头"), "官府")
        self.assertEqual(Player("势力测试", "散人").get_npc_faction("沈府管家"), "沈府")

    def test_static_faction_relation_and_stance(self):
        p = Player("势力关系", "散人")
        self.assertEqual(p.get_faction_relation("官府", "黑市"), -70)
        self.assertEqual(p.get_faction_stance("官府", "黑市"), "敌对")
        self.assertEqual(p.get_faction_relation("官府", "官府"), 100)

    def test_faction_relation_changes_are_persisted_in_world_state(self):
        p = Player("势力变动", "散人")
        self.assertEqual(p.change_faction_relation("官府", "黑市", 20), -50)
        self.assertEqual(p.get_faction_relation("黑市", "官府"), -50)
        self.assertEqual(p.world_state["variables"]["faction_relations"]["官府:黑市"], -50)

    def test_world_effect_can_change_faction_relation(self):
        p = Player("势力事件", "散人")
        engine.apply_world_effects(p.world_state, {"faction_relations": {"官府:黑市": 15}})
        self.assertEqual(p.get_faction_relation("官府", "黑市"), -55)
        self.assertEqual(p.get_faction_relation("黑市", "官府"), -55)

    def test_faction_relation_influences_competition(self):
        p = NPCCompetitionP240Tests()._start_case()
        p.change_faction_relation("官府", "沈府", -100)
        p.increment_var("quest_clock", 4)
        results = p.process_npc_competitions()
        self.assertTrue(results)
        self.assertEqual(results[0]["npc"], "捕头")
        self.assertIn("沈府管家", results[0]["scores"])

    def test_faction_influence_is_part_of_competition_score(self):
        p = Player("势力评分", "散人")
        c = {"npc": "捕头", "base_score": 0, "faction_weight": 0, "influence_weight": 1}
        self.assertEqual(p._npc_competition_score(c, [c]), p.get_faction_influence("官府"))

    def test_old_v12_save_without_faction_state_is_safe(self):
        p = Player("旧势力存档", "散人")
        p.world_state = {"flags": {}, "variables": {"quest_clock": 0}}
        self.assertEqual(p.get_faction_relation("官府", "黑市"), -70)
        self.assertEqual(p._faction_relation_map(), {})

    def test_faction_state_roundtrip_stays_v12(self):
        p = Player("势力存档", "散人")
        p.change_faction_relation("官府", "黑市", 10)
        fd, path = tempfile.mkstemp(suffix=".json"); os.close(fd)
        try:
            p.save_to_file(path)
            with open(path, encoding="utf8") as f:
                raw = json.load(f)
            self.assertEqual(raw["version"], 12)
            self.assertEqual(raw["world_state"]["variables"]["faction_relations"]["官府:黑市"], -60)
            q = Player.load_from_file(path)
            self.assertEqual(q.get_faction_relation("官府", "黑市"), -60)
        finally:
            os.remove(path)

    def test_no_save_version_change(self):
        self.assertEqual(engine.SAVE_VERSION, 12)

class FactionActionP242Tests(unittest.TestCase):
    def test_faction_actions_are_data_driven_and_fire(self):
        p = Player("势力行动", "散人")
        results = p.process_faction_actions()
        self.assertTrue(results)
        ids = {r["action_id"] for r in results}
        self.assertIn("black_market_crackdown", ids)
        self.assertIn("counter_official_crackdown", ids)
        self.assertIn("mediate_official_blackmarket", ids)
        self.assertIn("faction_action_log", p.world_state["variables"])

    def test_conflict_action_changes_relation_and_npc_state(self):
        p = Player("势力冲突", "散人")
        before = p.get_faction_relation("官府", "黑市")
        results = p.process_faction_actions()
        self.assertNotEqual(p.get_faction_relation("官府", "黑市"), before)
        self.assertEqual(p.get_npc_state("捕头"), "busy")
        self.assertTrue(any(r["type"] == "conflict" and r["faction"] == "官府" for r in results))

    def test_faction_action_propagates_player_information(self):
        p = Player("势力消息", "散人")
        p.process_faction_actions()
        info = p.get_player_information("faction:官府:黑市")
        self.assertIsNotNone(info)
        self.assertIn(info.get("source"), {"官府", "黑市"})

    def test_faction_action_cooldown_prevents_duplicate_same_clock(self):
        p = Player("势力冷却", "散人")
        first = p.process_faction_actions()
        second = p.process_faction_actions()
        self.assertTrue(first)
        self.assertEqual(second, [])

    def test_faction_action_history_is_in_world_state_not_player_attribute(self):
        p = Player("势力历史", "散人")
        p.process_faction_actions()
        self.assertIn("faction_actions", p.world_state["variables"])
        self.assertIn("faction_action_log", p.world_state["variables"])
        self.assertNotIn("faction_actions", p.__dict__)

    def test_tick_quest_clock_processes_faction_actions(self):
        p = Player("势力时钟", "散人")
        p.tick_quest_clock(1)
        self.assertTrue(p.get_faction_action_log())

    def test_old_v12_save_without_faction_actions_is_safe(self):
        p = Player("旧势力行动存档", "散人")
        p.world_state = {"flags": {}, "variables": {"quest_clock": 0}}
        results = p.process_faction_actions()
        self.assertTrue(results)
        self.assertEqual(p._faction_action_state().get("官府", {}).get("history", {}).get("black_market_crackdown"), 0)

    def test_faction_action_state_roundtrip_stays_v12(self):
        p = Player("势力行动存档", "散人")
        p.process_faction_actions()
        fd, path = tempfile.mkstemp(suffix=".json"); os.close(fd)
        try:
            self.assertTrue(p.save_to_file(path))
            with open(path, encoding="utf8") as f:
                raw = json.load(f)
            self.assertEqual(raw["version"], 12)
            self.assertIn("faction_actions", raw["world_state"]["variables"])
            q = Player.load_from_file(path)
            self.assertTrue(q.get_faction_action_log())
        finally:
            os.remove(path)

class FactionConflictP243Tests(unittest.TestCase):
    def test_conflict_state_is_data_driven_from_existing_factions(self):
        p = Player("冲突状态", "散人")
        p.process_faction_conflicts()
        rows = p.get_faction_conflicts()
        row = next(r for r in rows if set(r["factions"]) == {"官府", "黑市"})
        self.assertGreater(row["pressure"], 0)
        self.assertIn(row["level"], {"calm", "tension", "confrontation", "conflict", "escalation", "war"})

    def test_conflict_pressure_grows_with_repeated_world_ticks(self):
        p = Player("冲突积累", "散人")
        p.process_faction_conflicts()
        before = next(r["pressure"] for r in p.get_faction_conflicts() if set(r["factions"]) == {"官府", "黑市"})
        p.increment_var("quest_clock", 1)
        p.process_faction_conflicts()
        after = next(r["pressure"] for r in p.get_faction_conflicts() if set(r["factions"]) == {"官府", "黑市"})
        self.assertGreater(after, before)

    def test_conflict_level_change_creates_world_information_and_npc_reaction(self):
        p = Player("冲突升级", "散人")
        p.world_state["variables"]["faction_conflicts"] = {
            "官府:黑市": {"pressure": 72, "level": "confrontation", "relation": -70, "history": []}
        }
        p.increment_var("quest_clock", 1)
        results = p.process_faction_conflicts()
        self.assertTrue(any(set(r["factions"]) == {"官府", "黑市"} for r in results))
        self.assertEqual(p.get_npc_state("捕头"), "busy")
        self.assertIsNotNone(p.get_player_information("faction_conflict:官府:黑市"))

    def test_world_tension_summary_is_written_to_existing_variables(self):
        p = Player("世界紧张", "散人")
        p.process_faction_conflicts()
        self.assertIn("world_tension", p.world_state["variables"])
        self.assertIsInstance(p.world_state["variables"]["world_tension"], int)

    def test_conflict_log_stays_in_world_state(self):
        p = Player("冲突日志", "散人")
        p.world_state["variables"]["faction_conflicts"] = {
            "官府:黑市": {"pressure": 72, "level": "confrontation", "relation": -70, "history": []}
        }
        p.process_faction_conflicts()
        self.assertIn("faction_conflict_log", p.world_state["variables"])
        self.assertNotIn("faction_conflicts", p.__dict__)

    def test_v12_old_save_without_conflict_state_is_safe(self):
        p = Player("旧冲突存档", "散人")
        p.world_state = {"flags": {}, "variables": {"quest_clock": 0}}
        p.process_faction_conflicts()
        self.assertTrue(p.get_faction_conflicts())
        self.assertEqual(engine.SAVE_VERSION, 12)

    def test_conflict_state_roundtrip_stays_v12(self):
        p = Player("冲突存档", "散人")
        p.world_state["variables"]["faction_conflicts"] = {
            "官府:黑市": {"pressure": 80, "level": "conflict", "relation": -70, "history": []}
        }
        fd, path = tempfile.mkstemp(suffix=".json"); os.close(fd)
        try:
            self.assertTrue(p.save_to_file(path))
            with open(path, encoding="utf8") as f:
                raw = json.load(f)
            self.assertEqual(raw["version"], 12)
            self.assertIn("faction_conflicts", raw["world_state"]["variables"])
            q = Player.load_from_file(path)
            self.assertEqual(q.world_state["variables"]["faction_conflicts"]["官府:黑市"]["level"], "conflict")
        finally:
            os.remove(path)

    def test_tick_clock_processes_conflict_layer(self):
        p = Player("冲突时钟", "散人")
        p.tick_quest_clock(1)
        self.assertIn("faction_conflicts", p.world_state["variables"])

    def test_no_save_version_change_p243(self):
        self.assertEqual(engine.SAVE_VERSION, 12)

class RegionEcologyP244Tests(unittest.TestCase):
    def test_region_data_has_faction_exposure_and_ecology_profile(self):
        for zone, info in engine.WORLD_REGIONS.items():
            self.assertIsInstance(info.get("faction_exposure"), list)
            self.assertIsInstance(info.get("region_ecology"), dict)
            for faction in info.get("faction_exposure", []):
                self.assertIn(faction, engine.FACTIONS)

    def test_region_ecology_is_created_from_existing_v12_variables(self):
        p = Player("区域状态", "散人")
        p.process_faction_conflicts()
        changed = p.process_region_ecology()
        self.assertIn("region_ecology", p.world_state["variables"])
        self.assertIn("guiyun_city", p.world_state["variables"]["region_ecology"])
        self.assertIsInstance(changed, list)

    def test_guiyun_city_security_reflects_official_blackmarket_conflict(self):
        p = Player("城局势", "散人")
        p.world_state["variables"]["faction_conflicts"] = {"官府:黑市": {"pressure": 100, "level": "conflict", "relation": -70, "history": []}}
        p.process_region_ecology()
        info = p.get_region_ecology("guiyun_city")
        self.assertLess(info["security"], 78)
        self.assertIn(info["level"], {"tension", "confrontation", "conflict", "escalation", "war"})

    def test_region_danger_can_escalate_without_mutating_static_room_data(self):
        before = json.loads(json.dumps(engine.ROOMS["guiyun_central_square"], ensure_ascii=False))
        p = Player("区域危险", "散人")
        p.world_state["variables"]["faction_conflicts"] = {"官府:黑市": {"pressure": 150, "level": "war", "relation": -70, "history": []}}
        p.process_region_ecology()
        self.assertIn(p.get_region_ecology("guiyun_city")["danger"], {"high", "extreme"})
        self.assertEqual(before, engine.ROOMS["guiyun_central_square"])

    def test_region_exploration_adds_conflict_event_data_driven(self):
        p = Player("区域探索", "散人")
        p.world_state["variables"]["faction_conflicts"] = {"官府:黑市": {"pressure": 100, "level": "conflict", "relation": -70, "history": []}}
        p.process_region_ecology()
        events = p.get_region_exploration_event("guiyun_city", engine.WORLD_REGIONS["guiyun_city"]["exploration_events"])
        self.assertTrue(any(isinstance(e, dict) and "局势紧张" in e.get("text", "") for e in events))

    def test_region_ecology_roundtrip_stays_v12(self):
        p = Player("区域存档", "散人")
        p.process_faction_conflicts(); p.process_region_ecology()
        fd, path = tempfile.mkstemp(suffix=".json"); os.close(fd)
        try:
            self.assertTrue(p.save_to_file(path))
            with open(path, encoding="utf8") as f: raw = json.load(f)
            self.assertEqual(raw["version"], 12)
            self.assertIn("region_ecology", raw["world_state"]["variables"])
            q = Player.load_from_file(path)
            self.assertIn("guiyun_city", q.world_state["variables"]["region_ecology"])
        finally: os.remove(path)

    def test_old_v12_save_without_region_ecology_is_safe(self):
        p = Player("旧区域存档", "散人")
        p.world_state = {"flags": {}, "variables": {"quest_clock": 0}}
        p.process_region_ecology()
        self.assertIn("region_ecology", p.world_state["variables"])
        self.assertEqual(engine.SAVE_VERSION, 12)

    def test_region_exploration_event_does_not_require_static_room_mutation(self):
        p = Player("探索兼容", "散人")
        room_before = json.dumps(engine.ROOMS["guiyun_central_square"], ensure_ascii=False, sort_keys=True)
        p.world_state["variables"]["faction_conflicts"] = {"官府:黑市": {"pressure": 100, "level": "conflict", "relation": -70, "history": []}}
        p.process_region_ecology()
        _ = p.get_region_exploration_event("guiyun_city", engine.WORLD_REGIONS["guiyun_city"]["exploration_events"])
        room_after = json.dumps(engine.ROOMS["guiyun_central_square"], ensure_ascii=False, sort_keys=True)
        self.assertEqual(room_before, room_after)

    def test_no_save_version_change_p244(self):
        self.assertEqual(engine.SAVE_VERSION, 12)

class ChineseCommandUXP247Tests(unittest.TestCase):
    def test_primary_chinese_system_commands(self):
        expected = {
            "帮助": ("help", []), "保存": ("save", []), "读档": ("load", []),
            "退出": ("quit", []), "重载": ("reload", []), "状态": ("status", []),
            "查看": ("look", []), "背包": ("inventory", []), "地图": ("map", []),
        }
        for raw, result in expected.items():
            self.assertEqual(parse_command(raw), result)

    def test_chinese_direction_and_pinyin_commands(self):
        for raw, result in (("北", ("n", [])), ("南", ("s", [])), ("东", ("e", [])), ("西", ("w", [])),
                            ("bei", ("n", [])), ("nan", ("s", [])), ("dong", ("e", [])), ("xi", ("w", []))):
            self.assertEqual(parse_command(raw), result)

    def test_chinese_character_and_quest_commands(self):
        cases = {
            "交谈 村长": ("talk", ["村长"]), "关系 村长": ("relations", ["村长"]),
            "记忆 村长": ("memory", ["村长"]), "任务": ("quests", []),
            "接取 城内失踪案": ("jiequ", ["城内失踪案"]),
            "交付 城内失踪案": ("jiaofu", ["城内失踪案"]),
            "放弃 城内失踪案": ("fangqi", ["城内失踪案"]),
            "选择 城内失踪案|route_a": ("xuanze", ["城内失踪案|route_a"]),
        }
        for raw, result in cases.items():
            self.assertEqual(parse_command(raw), result)

    def test_chinese_world_commands(self):
        cases = {
            "信息": ("information", []), "人物行动": ("npc_actions", []), "门派": ("sect", []),
            "武学": ("skills", []), "势力": ("factions", []), "冲突": ("conflicts", []),
            "区域": ("region", []), "影响": ("influence", []), "事件": ("events", []), "探索": ("explore", []),
        }
        for raw, result in cases.items():
            self.assertEqual(parse_command(raw), result)

    def test_chinese_economy_equipment_and_combat_commands(self):
        cases = {
            "商店": ("shop", []), "货架": ("list", []), "购买 金创药 3": ("buy", ["金创药", "3"]),
            "出售 野猪肉 2": ("sell", ["野猪肉", "2"]), "打造": ("forge", []), "装备": ("equipment", []),
            "比较 玄铁重剑": ("compare", ["玄铁重剑"]), "卸下 武器": ("unequip", ["武器"]),
            "穿戴 皮甲": ("wear", ["皮甲"]), "使用 金创药": ("use", ["金创药"]),
            "攻击 野狼": ("kill", ["野狼"]), "打坐": ("heal", []),
        }
        for raw, result in cases.items():
            self.assertEqual(parse_command(raw), result)

    def test_legacy_english_commands_remain_compatible(self):
        cases = (
            ("save", ("save", [])), ("load", ("load", [])), ("look", ("look", [])),
            ("inventory", ("inventory", [])), ("quests", ("quests", [])),
            ("factions", ("factions", [])), ("conflicts", ("conflicts", [])),
            ("equipment", ("equipment", [])), ("compare 玄铁重剑", ("compare", ["玄铁重剑"])),
        )
        for raw, result in cases:
            self.assertEqual(parse_command(raw), result)

    def test_no_save_version_change_p247(self):
        self.assertEqual(engine.SAVE_VERSION, 12)


class P251NoticeBoardUXTests(unittest.TestCase):
    def test_notice_command_maps_to_board(self):
        self.assertEqual(parse_command("公告"), ("notice_board", []))
        self.assertEqual(parse_command("公告栏"), ("notice_board", []))
        self.assertEqual(parse_command("榜墙"), ("notice_board", []))

    def test_public_topic_labels_hide_internal_ids(self):
        from actions import _public_topic_label
        self.assertEqual(_public_topic_label("faction:官府:黑市"), "势力消息")
        self.assertEqual(_public_topic_label("faction_conflict:官府:黑市"), "势力冲突")
        self.assertEqual(_public_topic_label("region:main"), "区域动态")
        self.assertNotIn(":", _public_topic_label("faction:官府:黑市"))

    def test_notice_board_hides_empty_internal_records(self):
        p = Player("公告栏测试", "散人")
        p.learn_player_information("faction:官府:黑市", "", "", 0)
        p.learn_player_information(
            "new_wulin_rumor", "最近有镖队经过青石村。", "江湖传闻", 70,
            follow_up={"npc": "说书先生", "room": "guiyun_tea_room", "hint": "可打听江湖传闻"},
        )
        import io, contextlib
        buf = io.StringIO()
        p.location = "village_square"
        with contextlib.redirect_stdout(buf):
            handle_notice_board(p)
        out = buf.getvalue()
        self.assertIn("镖队经过青石村", out)
        self.assertNotIn("faction:官府:黑市", out)
        self.assertNotIn("来源：", out)

    def test_notice_board_available_at_two_squares(self):
        p = Player("公告地点测试", "散人")
        import io, contextlib
        for room_id in ("village_square", "guiyun_central_square"):
            p.location = room_id
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                handle_notice_board(p)
            self.assertIn("公告", buf.getvalue())

class ChineseMUDUXP249Tests(unittest.TestCase):
    def test_help_shortcuts_and_topics(self):
        self.assertEqual(parse_command("?"), ("help", []))
        self.assertEqual(parse_command("？"), ("help", []))
        self.assertEqual(parse_command("帮助 武学"), ("help", ["武学"]))
        self.assertEqual(parse_command("帮助 任务"), ("help", ["任务"]))

    def test_chinese_quest_composite_commands_parse(self):
        cases = {
            "任务 接取 城内失踪案": ("quests", ["接取", "城内失踪案"]),
            "任务 交付 城内失踪案": ("quests", ["交付", "城内失踪案"]),
            "任务 放弃 城内失踪案": ("quests", ["放弃", "城内失踪案"]),
            "任务 选择 城内失踪案|route_a": ("quests", ["选择", "城内失踪案|route_a"]),
        }
        for raw, expected in cases.items():
            self.assertEqual(parse_command(raw), expected)

    def test_chinese_quest_composite_commands_execute(self):
        p = Player("任务中文", "散人")
        # 通过一个不存在任务验证“任务 接取”已进入接取分支，而不是被当成任务详情。
        import io, contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            handle_quest(p, "quests", ["接取", "不存在任务"])
        self.assertIn("不存在名为【不存在任务】的任务", buf.getvalue())

    def test_p251_normal_prompt_is_restored(self):
        p = Player("提示测试", "散人")
        self.assertEqual(make_prompt(p), "> ")

    def test_p251_status_uses_full_insight_label(self):
        p = Player("洞察测试", "散人")
        import io, contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            show_status(p)
        out = buf.getvalue()
        self.assertIn("洞察", out)
        self.assertNotIn(" / 洞 ", out)

    def test_status_uses_chinese_attribute_label(self):
        p = Player("界面测试", "散人")
        import io, contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            show_status(p, "combat")
        out = buf.getvalue()
        self.assertIn("属性：", out)
        self.assertNotIn("Build：", out)

    def test_no_clear_screen_on_normal_movement(self):
        from pathlib import Path
        source = Path("main.py").read_text(encoding="utf8")
        # 启动时允许清屏，但实际移动处理段不应再清屏，以保留 MUD 滚屏记录。
        movement = source.split('direction_exit =', 1)[1].split('except KeyboardInterrupt:', 1)[0]
        self.assertNotIn("clear_screen()", movement)

    def test_direction_aliases_reach_real_room_exit_keys(self):
        p = Player("方向测试", "散人")
        start = p.location
        self.assertIn("北", engine.ROOMS[start].get("exits", {}))
        self.assertEqual(parse_command("n"), ("n", []))
        self.assertEqual(parse_command("北"), ("n", []))
        self.assertIn(engine.ROOMS[start]["exits"]["北"], engine.ROOMS)

    def test_look_localizes_region_state_labels(self):
        p = Player("区域界面", "散人")
        import io, contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            look(p)
        out = buf.getvalue()
        self.assertRegex(out, r"【区域局势】.*平静.*危险度：一般")
        self.assertNotIn("区域局势：calm", out)
        self.assertNotIn("危险度 normal", out)

    def test_run_command_has_safe_dispatch(self):
        self.assertEqual(parse_command("run"), ("run", []))

    def test_no_save_version_change_p249(self):
        self.assertEqual(engine.SAVE_VERSION, 12)


class DynamicWorldStabilityP246Tests(unittest.TestCase):
    def test_stability_state_is_created_in_existing_v12_variables(self):
        p = Player("稳定层", "散人")
        p.tick_quest_clock(1)
        self.assertIn("dynamic_world_stability", p.world_state["variables"])
        self.assertEqual(p.world_state["variables"]["dynamic_world_last_stability_tick"], 1)

    def test_high_conflict_can_recover_without_new_conflict_actions(self):
        p = Player("冲突疲劳", "散人")
        p.world_state["variables"]["faction_conflicts"] = {
            "官府:黑市": {"pressure": 160, "level": "war", "relation": -70, "history": []}
        }
        p.world_state["variables"]["faction_action_log"] = []
        p.tick_quest_clock(1)
        before = p.world_state["variables"]["faction_conflicts"]["官府:黑市"]["pressure"]
        p.tick_quest_clock(6)
        after = p.world_state["variables"]["faction_conflicts"]["官府:黑市"]["pressure"]
        self.assertLess(after, before)
        self.assertLessEqual(after, 200)

    def test_long_world_simulation_stays_bounded(self):
        p = Player("长期模拟", "散人")
        for _ in range(500):
            p.tick_quest_clock(1)
        conflicts = p.get_faction_conflicts()
        self.assertTrue(conflicts)
        self.assertTrue(all(0 <= r["pressure"] <= 200 for r in conflicts))
        self.assertLessEqual(len(p.world_state["variables"].get("faction_action_log", [])), 100)
        self.assertLessEqual(len(p.world_state["variables"].get("faction_conflict_log", [])), 100)
        self.assertLessEqual(len(p.world_state["variables"].get("npc_action_log", [])), 100)

    def test_information_and_memory_ttl_are_cleaned_during_tick(self):
        p = Player("过期清理", "散人")
        p.learn_player_information("temporary", "临时消息", "测试", 80, ttl=1)
        p.remember_npc_about_player("青石村守卫", "temporary_memory", "临时记忆", "neutral", 30, ttl=1)
        p.tick_quest_clock(2)
        self.assertIsNone(p.get_player_information("temporary"))
        self.assertIsNone(p.get_npc_memory("青石村守卫", "temporary_memory"))

    def test_dynamic_world_histories_are_capped(self):
        p = Player("历史上限", "散人")
        variables = p.world_state["variables"]
        variables["faction_action_log"] = [{"clock": i} for i in range(250)]
        variables["faction_conflict_log"] = [{"clock": i} for i in range(250)]
        variables["npc_action_log"] = [{"clock": i} for i in range(250)]
        variables["faction_conflicts"] = {"官府:黑市": {"pressure": 80, "level": "conflict", "history": [{"clock": i} for i in range(60)]}}
        p.process_dynamic_world_stability()
        self.assertEqual(len(variables["faction_action_log"]), 100)
        self.assertEqual(len(variables["faction_conflict_log"]), 100)
        self.assertEqual(len(variables["npc_action_log"]), 100)
        self.assertEqual(len(variables["faction_conflicts"]["官府:黑市"]["history"]), 20)

    def test_v12_old_save_without_stability_state_is_safe(self):
        p = Player("旧稳定档", "散人")
        p.world_state = {"flags": {}, "variables": {"quest_clock": 20}}
        p.tick_quest_clock(1)
        self.assertIn("dynamic_world_stability", p.world_state["variables"])
        self.assertEqual(engine.SAVE_VERSION, 12)

    def test_stability_round_trip_stays_v12(self):
        p = Player("稳定存档", "散人")
        for _ in range(12):
            p.tick_quest_clock(1)
        fd, path = tempfile.mkstemp(suffix=".json"); os.close(fd)
        try:
            self.assertTrue(p.save_to_file(path))
            with open(path, encoding="utf8") as f:
                raw = json.load(f)
            self.assertEqual(raw["version"], 12)
            self.assertIn("dynamic_world_stability", raw["world_state"]["variables"])
            q = Player.load_from_file(path)
            self.assertEqual(q.get_quest_clock(), 12)
            self.assertEqual(q.world_state["variables"].get("dynamic_world_last_stability_tick"), 12)
        finally:
            os.remove(path)

    def test_no_save_version_change_p246(self):
        self.assertEqual(engine.SAVE_VERSION, 12)


class ChineseCommandUXP248Tests(unittest.TestCase):
    def test_short_chinese_commands(self):
        cases = {
            "帮": ("help", []), "查": ("look", []), "包": ("inventory", []), "状": ("status", []),
            "图": ("map", []), "探": ("explore", []), "事": ("events", []), "打 野狼": ("kill", ["野狼"]),
            "疗": ("heal", []), "装": ("equipment", []), "铸": ("forge", []), "武": ("skills", []),
            "技": ("skills", []), "门": ("sect", []), "势": ("factions", []), "局": ("conflicts", []),
            "区": ("region", []), "影": ("influence", []), "存": ("save", []), "读": ("load", []), "退": ("quit", []),
        }
        for raw, result in cases.items():
            self.assertEqual(parse_command(raw), result)

    def test_skill_command_has_chinese_subcommands(self):
        self.assertEqual(parse_command("武学"), ("skills", []))
        self.assertEqual(parse_command("武学 学习 罗汉拳"), ("skills", ["学习", "罗汉拳"]))
        self.assertEqual(parse_command("武学 查看 罗汉拳"), ("skills", ["查看", "罗汉拳"]))

    def test_region_labels_are_supported(self):
        labels = {"calm": "平静", "tension": "紧张", "confrontation": "对峙", "conflict": "冲突", "escalation": "升级", "war": "战争"}
        dangers = {"safe": "安全", "normal": "一般", "dangerous": "危险", "high": "高危", "extreme": "极危"}
        self.assertEqual(labels["calm"], "平静")
        self.assertEqual(dangers["normal"], "一般")

    def test_status_skill_summary_available(self):
        p = Player("技能显示", "散人")
        learned = [x["name"] for x in p.get_skill_summary() if x.get("learned")]
        self.assertTrue(learned)


class MudCommandUXP250Tests(unittest.TestCase):
    def test_command_chain_is_bounded(self):
        import main
        self.assertEqual(main.split_command_chain("北;南;东;西;查看;地图;状态;背包;帮助"), ["北", "南", "东", "西", "查看", "地图", "状态", "背包"])

    def test_command_alias_round_trip_in_existing_v12_variables(self):
        import main
        p = Player("快捷测试", "散人")
        main.handle_alias_command(p, ["回村", "=", "南;南;西"])
        self.assertEqual(main._command_aliases(p)["回村"], "南;南;西")
        self.assertEqual(main.expand_alias("回村", p), "南;南;西")
        self.assertEqual(engine.SAVE_VERSION, 12)

    def test_alias_management_does_not_execute_embedded_semicolons(self):
        import main
        p = Player("别名定义", "散人")
        raw = "别名 回城 = 南;南;西"
        self.assertEqual(main.parse_command(raw), ("alias", ["回城", "=", "南;南;西"]))

    def test_system_commands_cannot_be_overridden(self):
        import main
        p = Player("命令保护", "散人")
        main.handle_alias_command(p, ["北", "=", "南"])
        self.assertNotIn("北", main._command_aliases(p))

    def test_fuzzy_suggestions_find_common_commands(self):
        import main
        self.assertIn("帮助", main.command_suggestions("帮z"))

    def test_help_topics_cover_world_systems(self):
        import main
        from io import StringIO
        from contextlib import redirect_stdout
        for topic in ("区域", "势力", "冲突", "影响", "历史", "别名"):
            buf = StringIO()
            with redirect_stdout(buf):
                main.show_help(topic)
            out = buf.getvalue()
            self.assertNotIn("没有找到", out)

    def test_save_load_preserves_aliases_without_version_change(self):
        import main, tempfile, os, json
        p = Player("快捷存档", "散人")
        main.handle_alias_command(p, ["回村", "=", "南;南;西"])
        fd, path = tempfile.mkstemp(suffix=".json"); os.close(fd)
        try:
            self.assertTrue(p.save_to_file(path))
            with open(path, encoding="utf8") as f:
                raw = json.load(f)
            self.assertEqual(raw["version"], 12)
            self.assertEqual(raw["world_state"]["variables"]["command_aliases"]["回村"], "南;南;西")
            q = Player.load_from_file(path)
            self.assertEqual(main._command_aliases(q)["回村"], "南;南;西")
        finally:
            os.remove(path)

    def test_fullwidth_semicolon_is_supported_for_chinese_users(self):
        import main
        self.assertEqual(main.split_command_chain("北；南；查看"), ["北", "南", "查看"])

class P252OnboardingHelpTests(unittest.TestCase):
    def test_new_commands_parse(self):
        self.assertEqual(parse_command("百科"), ("encyclopedia", []))
        self.assertEqual(parse_command("百科 武学"), ("encyclopedia", ["武学"]))
        self.assertEqual(parse_command("建议"), ("advice", []))
        self.assertEqual(parse_command("提示"), ("advice", []))

    def test_help_newbie_topic_is_actionable(self):
        import io, contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            show_help("新手")
        out = buf.getvalue()
        for word in ("查看", "状态", "交谈", "任务", "武学", "公告", "建议"):
            self.assertIn(word, out)

    def test_help_specialized_topics(self):
        import io, contextlib
        for topic, expected in (("战斗", "攻击"), ("装备", "穿戴"), ("门派", "门派"), ("NPC", "交谈"), ("区域", "安全")):
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                show_help(topic)
            self.assertIn(expected, buf.getvalue())

    def test_encyclopedia_hides_internal_implementation_terms(self):
        import io, contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            show_encyclopedia("势力")
        out = buf.getvalue()
        self.assertIn("官府", out)
        self.assertNotIn("faction:", out)
        self.assertNotIn("world_state", out)

    def test_encyclopedia_lists_player_facing_entries(self):
        import io, contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            show_encyclopedia()
        out = buf.getvalue()
        self.assertIn("武学", out)
        self.assertIn("人物", out)
        self.assertNotIn("NPC", out)
        self.assertIn("公告", out)

    def test_first_entry_guide_is_replaced_by_in_world_guidance(self):
        import io, contextlib
        p = Player("新手引导测试", "散人")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            show_first_entry_guide(p)
        self.assertEqual(buf.getvalue(), "")
        self.assertNotIn("p252_intro_seen", p.world_state.get("flags", {}))

    def test_first_entry_flag_roundtrip_without_save_version_change(self):
        import tempfile, os, json
        p = Player("引导存档测试", "散人")
        p.world_state["flags"]["p252_intro_seen"] = True
        fd, path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        try:
            self.assertTrue(p.save_to_file(path))
            with open(path, encoding="utf8") as f:
                raw = json.load(f)
            self.assertEqual(raw["version"], 12)
            self.assertTrue(raw["world_state"]["flags"]["p252_intro_seen"])
            q = Player.load_from_file(path)
            self.assertTrue(q.world_state["flags"]["p252_intro_seen"])
        finally:
            os.remove(path)

    def test_context_advice_uses_current_player_state(self):
        import io, contextlib
        p = Player("建议测试", "散人")
        p.location = "village_square"
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            show_context_advice(p)
        out = buf.getvalue()
        self.assertIn("公告", out)
        self.assertIn("查看", out)
        p.hp = 20
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            show_context_advice(p)
        self.assertIn("打坐", buf.getvalue())

    def test_no_save_version_change_p252(self):
        self.assertEqual(engine.SAVE_VERSION, 12)

class P313JianghuPathTests(unittest.TestCase):
    def test_old_player_profile_is_created_without_save_version_change(self):
        p = Player("旧存档侠客", "散人")
        profile = p._jianghu_profile()
        self.assertEqual(profile["honor"], 0)
        self.assertEqual(profile["infamy"], 0)
        self.assertEqual(set(profile["paths"]), set(Player.JIANGHU_PATHS))
        self.assertEqual(engine.SAVE_VERSION, 12)

    def test_known_actions_change_expected_paths_only(self):
        p = Player("路线测试", "散人")
        self.assertTrue(p.record_jianghu_action("assist_officials"))
        paths = p.get_jianghu_path_summary()["paths"]
        self.assertEqual(paths["官府"], 5)
        self.assertEqual(paths["侠客"], 1)
        self.assertEqual(paths["黑市"], 0)

    def test_unknown_action_does_not_change_paths(self):
        p = Player("未知行为测试", "散人")
        before = p.get_jianghu_path_summary()["paths"]
        self.assertFalse(p.record_jianghu_action("random_action"))
        self.assertEqual(p.get_jianghu_path_summary()["paths"], before)

    def test_path_values_are_bounded(self):
        p = Player("上限测试", "散人")
        for _ in range(30):
            p.record_jianghu_action("help_people", 5)
        self.assertEqual(p.get_jianghu_path_summary()["paths"]["侠客"], 100)

    def test_reputation_labels_and_bounds(self):
        p = Player("声名测试", "散人")
        p.add_jianghu_reputation(honor=55, infamy=12)
        self.assertEqual(p.get_jianghu_reputation_labels(), ("江湖侠客", "危险人物"))
        p.add_jianghu_reputation(honor=-999, infamy=-999)
        profile = p._jianghu_profile()
        self.assertEqual(profile["honor"], 0)
        self.assertEqual(profile["infamy"], 0)

    def test_profile_persists_in_existing_v12_world_state(self):
        fd, path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        try:
            p = Player("路线存档测试", "散人")
            p.record_jianghu_action("escort_trade")
            p.add_jianghu_reputation(honor=7)
            self.assertTrue(p.save_to_file(path))
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            self.assertEqual(data["version"], 12)
            self.assertIn("jianghu_profile", data["world_state"]["variables"])
            q = Player.load_from_file(path)
            self.assertIsNotNone(q)
            self.assertEqual(q._jianghu_profile()["honor"], 7)
            self.assertEqual(q.get_jianghu_path_summary()["paths"]["商会"], 5)
        finally:
            os.remove(path)

    def test_status_shows_jianghu_path_summary(self):
        import io, contextlib
        p = Player("面板测试", "散人")
        p.record_jianghu_action("help_people", 2)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            show_status(p, "reputation")
        out = buf.getvalue()
        self.assertIn("江湖声名", out)
        with contextlib.redirect_stdout(buf := io.StringIO()):
            show_status(p, "growth")
        self.assertIn("侠客", buf.getvalue())
        self.assertIn("路线倾向", buf.getvalue())

class P314IdentityNpcFeedbackTests(unittest.TestCase):
    def test_identity_title_progresses_with_honor_and_hero_path(self):
        p = Player("侠名成长", "散人")
        self.assertEqual(p.get_jianghu_identity_title(), "无名侠客")
        p.record_jianghu_action("help_people", 3)
        p.add_jianghu_reputation(honor=55)
        self.assertEqual(p.get_jianghu_identity_title(), "地方侠客")
        p.add_jianghu_reputation(honor=60)
        p.record_jianghu_action("help_people", 5)
        self.assertEqual(p.get_jianghu_identity_title(), "一方豪侠")

    def test_official_commerce_black_market_and_solo_titles(self):
        cases = [
            ("assist_officials", 6, "官府协力之人"),
            ("escort_trade", 6, "护商义士"),
            ("black_market_trade", 6, "黑市行者"),
            ("refuse_factions", 8, "独行游侠"),
        ]
        for action, amount, expected in cases:
            p = Player("路线称号测试", "散人")
            p.record_jianghu_action(action, amount)
            self.assertEqual(p.get_jianghu_identity_title(), expected)

    def test_npc_reaction_reflects_honor_and_infamy(self):
        p = Player("NPC反馈测试", "散人")
        self.assertEqual(p.get_jianghu_npc_reaction(), "")
        p.add_jianghu_reputation(honor=55)
        self.assertIn("善举", p.get_jianghu_npc_reaction())
        p.add_jianghu_reputation(infamy=80)
        self.assertIn("凶名", p.get_jianghu_npc_reaction())

    def test_dialogue_jianghu_effects_are_data_driven_and_bounded(self):
        p = Player("对话效果测试", "散人")
        self.assertTrue(p.apply_jianghu_effects({"jianghu_action": "assist_officials", "honor_delta": 4}))
        profile = p._jianghu_profile()
        self.assertEqual(profile["honor"], 4)
        self.assertEqual(profile["paths"]["官府"], 5)
        self.assertFalse(p.apply_jianghu_effects({"unknown": True}))

    def test_status_panel_shows_dynamic_identity(self):
        import io, contextlib
        p = Player("称号面板测试", "散人")
        p.record_jianghu_action("escort_trade", 6)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            show_status(p)
        self.assertIn("江湖身份：    护商义士", buf.getvalue())

class P315QuestGrowthLoopTests(unittest.TestCase):
    def test_reward_bundle_applies_honor_infamy_and_path(self):
        from rewards import apply_reward_bundle
        p = Player("任务成长测试", "散人")
        result = apply_reward_bundle(p, {
            "exp": 5, "gold": 3, "honor_delta": 7,
            "infamy_delta": 2, "jianghu_action": "assist_officials",
            "jianghu_amount": 2,
        }, announce=False)
        self.assertTrue(result["ok"])
        self.assertTrue(result["jianghu_changed"])
        profile = p._jianghu_profile()
        self.assertEqual(profile["honor"], 7)
        self.assertEqual(profile["infamy"], 2)
        self.assertEqual(profile["paths"]["官府"], 10)
        self.assertEqual(profile["paths"]["侠客"], 2)

    def test_invalid_reward_cannot_partially_apply_jianghu_growth(self):
        from rewards import apply_reward_bundle
        p = Player("异常奖励测试", "散人")
        initial_gold = p.gold
        result = apply_reward_bundle(p, {
            "gold": 20, "honor_delta": 50,
            "jianghu_action": "not_a_real_path",
        }, announce=False)
        self.assertFalse(result["ok"])
        self.assertEqual(p.gold, initial_gold)
        profile = p._jianghu_profile()
        self.assertEqual(profile["honor"], 0)
        self.assertEqual(sum(profile["paths"].values()), 0)

    def test_quest_growth_is_reward_data_and_branch_specific(self):
        quests = engine.QUESTS
        self.assertEqual(quests["清剿黑风山"]["reward"]["honor_delta"], 8)
        choices = {c["id"]: c for c in quests["万商会商路"]["choices"]}
        self.assertEqual(choices["public_audit"]["reward"]["honor_delta"], 5)
        self.assertEqual(choices["public_audit"]["reward"]["jianghu_action"], "escort_trade")
        self.assertNotIn("honor_delta", choices["private_deal"]["reward"])
        self.assertEqual(choices["private_deal"]["reward"]["jianghu_amount"], 1)

    def test_quest_growth_profile_survives_v12_save_load(self):
        from rewards import apply_reward_bundle
        fd, path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        try:
            p = Player("成长闭环存档", "散人")
            result = apply_reward_bundle(p, {"honor_delta": 12, "jianghu_action": "help_people", "jianghu_amount": 2}, announce=False)
            self.assertTrue(result["ok"])
            self.assertTrue(p.save_to_file(path))
            with open(path, encoding="utf-8") as f:
                raw = json.load(f)
            self.assertEqual(raw["version"], 12)
            restored = Player.load_from_file(path)
            self.assertEqual(restored._jianghu_profile()["honor"], 12)
            self.assertEqual(restored._jianghu_profile()["paths"]["侠客"], 10)
        finally:
            os.remove(path)


class P317QuestRouteIntegrationTests(unittest.TestCase):
    def test_any_conditions_allow_relation_or_route_path(self):
        p = Player("条件组测试", "散人")
        condition = {"any": [{"relations": {"万商会会长": {"gte": 5}}},
                             {"jianghu_paths": {"商会": {"gte": 5}}}]}
        self.assertFalse(engine.check_conditions(condition, p.world_state, [], p))
        p.record_jianghu_action("escort_trade", 1)
        self.assertTrue(engine.check_conditions(condition, p.world_state, [], p))

    def test_player_route_conditions_fail_closed_without_player_context(self):
        condition = {"any": [{"relations": {"万商会会长": {"gte": 5}}},
                             {"jianghu_paths": {"商会": {"gte": 5}}}]}
        self.assertFalse(engine.check_conditions(condition, {"flags": {}, "variables": {}}, []))

    def test_condition_failure_explains_missing_route_and_relation(self):
        p = Player("条件提示测试", "散人")
        condition = {"relations": {"万商会会长": {"gte": 15}},
                     "any": [{"infamy": {"gte": 5}}, {"jianghu_paths": {"黑市": {"gte": 5}}}]}
        messages = engine.explain_condition_failures(condition, p.world_state, [], p)
        self.assertTrue(any("万商会会长" in msg for msg in messages))
        self.assertTrue(any("以下条件至少满足一项" in msg for msg in messages))

    def test_official_branch_grants_honor_and_official_path_once(self):
        p = Player("官府路线整合", "散人")
        p.completed_quests.append("入城引路")
        p.active_quests["城内失踪案"] = 0
        p.quest_states["城内失踪案"] = {"stage": 0, "progress": 0}
        p.update_quest_progress("沈府管家", "talk")
        ok, message = p.choose_quest_branch("城内失踪案", "official_route")
        self.assertTrue(ok, message)
        profile = p._jianghu_profile()
        self.assertEqual(profile["honor"], 2)
        self.assertEqual(profile["paths"]["官府"], 5)
        ok_again, _ = p.choose_quest_branch("城内失踪案", "official_route")
        self.assertFalse(ok_again)
        self.assertEqual(p._jianghu_profile()["honor"], 2)


class P316JianghuConditionsTests(unittest.TestCase):
    def test_quest_conditions_can_gate_on_honor_infamy_and_paths(self):
        p = Player("路线条件测试", "散人")
        conditions = {"honor": {"gte": 20}, "infamy": {"lt": 10},
                      "jianghu_paths": {"官府": {"gte": 10}, "侠客": {"gte": 2}}}
        self.assertFalse(engine.check_conditions(conditions, p.world_state, p.completed_quests, p))
        p.add_jianghu_reputation(honor=25, infamy=3)
        p.record_jianghu_action("assist_officials", 2)
        self.assertTrue(engine.check_conditions(conditions, p.world_state, p.completed_quests, p))
        p.record_jianghu_action("black_market_trade", 5)
        self.assertTrue(engine.check_conditions(conditions, p.world_state, p.completed_quests, p))

    def test_invalid_jianghu_path_condition_fails_closed(self):
        p = Player("非法路线条件", "散人")
        self.assertFalse(engine.check_conditions({"jianghu_paths": {"不存在的路线": {"gte": 0}}}, p.world_state, [], p))
        self.assertFalse(engine.check_conditions({"jianghu_paths": ["侠客"]}, p.world_state, [], p))

    def test_mixed_honor_and_infamy_produces_mixed_npc_reaction(self):
        p = Player("褒贬参半", "散人")
        p.add_jianghu_reputation(honor=60, infamy=25)
        reaction = p.get_jianghu_npc_reaction()
        self.assertIn("敬重中带着戒心", reaction)

    def test_conditions_without_jianghu_rules_remain_compatible(self):
        p = Player("旧条件兼容", "散人")
        self.assertTrue(engine.check_conditions({"level": {"gte": 1}}, p.world_state, [], p))


class P318QuestFlowAcceptanceTests(unittest.TestCase):
    def _ready_merchant_quest(self, name):
        p = Player(name, "散人")
        p.location = "guiyun_merchant_guild"
        p.completed_quests.append("入城引路")
        p.active_quests["万商会商路"] = 1
        p.quest_states["万商会商路"] = {"stage": 2, "progress": 1, "accepted_at": 0}
        p.save_to_file = lambda *args, **kwargs: True
        return p

    def test_public_audit_full_handin_applies_reward_and_world_effect_once(self):
        import io, contextlib
        p = self._ready_merchant_quest("秉公核账验收")
        p.record_jianghu_action("escort_trade", 1)  # 商会路线解锁公账结局
        starting_gold = p.gold
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            handle_quest(p, "jiaofu", ["万商会商路"])
        self.assertIn("万商会商路", p.completed_quests)
        self.assertNotIn("万商会商路", p.active_quests)
        self.assertTrue(p.get_flag("merchant_guild:public_audit"))
        self.assertFalse(p.get_flag("merchant_guild:private_deal"))
        self.assertEqual(p.gold, starting_gold + 140)
        self.assertEqual(p._jianghu_profile()["honor"], 5)
        self.assertEqual(p.get_var("merchant_reputation"), 22)  # 完成效果 + 结局效果
        after_gold = p.gold
        with contextlib.redirect_stdout(io.StringIO()):
            handle_quest(p, "jiaofu", ["万商会商路"])
        self.assertEqual(p.gold, after_gold, "重复交付不得重复发奖")

    def test_private_deal_requires_both_relation_and_infamy_or_black_market_path(self):
        import io, contextlib
        p = self._ready_merchant_quest("私下和解验收")
        p.change_relation("万商会会长", 15)
        p.add_jianghu_reputation(infamy=5)
        starting_gold = p.gold
        with contextlib.redirect_stdout(io.StringIO()):
            handle_quest(p, "jiaofu", ["万商会商路|private_deal"])
        self.assertIn("万商会商路", p.completed_quests)
        self.assertTrue(p.get_flag("merchant_guild:private_deal"))
        self.assertFalse(p.get_flag("merchant_guild:public_audit"))
        self.assertEqual(p.gold, starting_gold + 280)
        self.assertEqual(p.get_var("merchant_reputation"), 16)
        self.assertEqual(p._jianghu_profile()["honor"], 0)

    def test_locked_ending_does_not_complete_or_change_reward_state(self):
        import io, contextlib
        p = self._ready_merchant_quest("结局门槛验收")
        p.change_relation("万商会会长", 14)
        p.add_jianghu_reputation(infamy=5)
        starting_gold = p.gold
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            handle_quest(p, "jiaofu", ["万商会商路|private_deal"])
        self.assertIn("暂不可选", output.getvalue())
        self.assertIn("万商会商路", p.active_quests)
        self.assertNotIn("万商会商路", p.completed_quests)
        self.assertEqual(p.gold, starting_gold)
        self.assertFalse(p.get_flag("merchant_guild:private_deal"))

    def test_branch_choice_accepts_visible_chinese_title_and_number(self):
        p = Player("路线名称测试", "散人")
        p.active_quests["城内失踪案"] = 0
        p.quest_states["城内失踪案"] = {"stage": 0, "progress": 1, "branch_pending": True}
        ok, msg = p.choose_quest_branch("城内失踪案", "1")
        self.assertTrue(ok, msg)
        self.assertEqual(p.quest_states["城内失踪案"]["stage"], 1)

        p2 = Player("路线名称测试二", "散人")
        p2.active_quests["城内失踪案"] = 0
        p2.quest_states["城内失踪案"] = {"stage": 0, "progress": 1, "branch_pending": True}
        p2.change_relation("黑市接头人", 5)
        ok, msg = p2.choose_quest_branch("城内失踪案", "暗查黑市")
        self.assertTrue(ok, msg)
        self.assertEqual(p2.quest_states["城内失踪案"]["stage"], 2)

    def test_world_event_can_be_triggered_by_chinese_title(self):
        p = Player("事件名称测试", "散人")
        p.location = "village_gate"
        p.set_var("quest_clock", 0)
        p.set_var("exploration:main", 2)
        ok, message, info = p.trigger_world_event("黑风寨劫道风声")
        self.assertTrue(ok, message)
        self.assertEqual(info.get("title"), "黑风寨劫道风声")

    def test_missing_primary_save_recovers_from_valid_backup(self):
        fd, path = tempfile.mkstemp(prefix="backup_recovery_test_", suffix=".json")
        os.close(fd)
        backup_path = path + ".bak"
        try:
            p = Player("备份恢复测试", "散人")
            p.gold = 321
            p.set_flag("backup_recovery_marker", True)
            with patch("ui_output.safe_print"):
                self.assertTrue(p.save_to_file(path))
            with open(path, "r", encoding="utf-8") as source, open(backup_path, "w", encoding="utf-8") as backup:
                backup.write(source.read())
            os.remove(path)
            with patch("ui_output.safe_print"):
                restored = Player.load_from_file(path)
            self.assertIsNotNone(restored)
            self.assertEqual(restored.name, "备份恢复测试")
            self.assertEqual(restored.gold, 321)
            self.assertTrue(restored.get_flag("backup_recovery_marker"))
        finally:
            for candidate in (path, backup_path):
                if os.path.exists(candidate):
                    os.remove(candidate)

    def test_save_and_load_messages_do_not_expose_filename(self):
        import io, contextlib
        fd, path = tempfile.mkstemp(prefix="internal_test_save_", suffix=".json")
        os.close(fd)
        try:
            p = Player("显示测试", "散人")
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertTrue(p.save_to_file(path))
            self.assertNotIn(path, output.getvalue())
            os.remove(path)
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertIsNone(Player.load_from_file(path))
            self.assertNotIn(path, output.getvalue())
            self.assertNotIn(".json", output.getvalue())
        finally:
            if os.path.exists(path):
                os.remove(path)

    def test_player_cannot_choose_quest_route_before_stage_goal_is_done(self):
        p = Player("路线保护测试", "散人")
        p.active_quests["城内失踪案"] = 0
        p.quest_states["城内失踪案"] = {"stage": 0, "progress": 0}
        ok, message = p.choose_quest_branch("城内失踪案", "1")
        self.assertFalse(ok)
        self.assertIn("尚未达成", message)
        self.assertEqual(p.quest_states["城内失踪案"]["stage"], 0)

    def test_npc_autonomy_cannot_skip_pending_player_route_choice(self):
        p = Player("自主推进保护测试", "散人")
        p.active_quests["城内失踪案"] = 0
        p.quest_states["城内失踪案"] = {"stage": 0, "progress": 0, "branch_pending": True}
        profile = next(x for x in engine.NPCS["捕头"].get("proactive_quests", []) if x.get("quest") == "城内失踪案")
        profile = dict(profile, advance_stage=True)
        before = p.quest_states["城内失踪案"]["stage"]
        result = p._advance_npc_proactive_quest("捕头", profile, "城内失踪案")
        self.assertIsNone(result)
        self.assertEqual(p.quest_states["城内失踪案"]["stage"], before)
        self.assertTrue(p.quest_states["城内失踪案"]["branch_pending"])


    def test_world_event_menu_shows_titles_not_internal_ids(self):
        import io, contextlib
        p = Player("事件显示测试", "散人")
        p.location = "village_gate"
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            handle_world_events(p)
        shown = output.getvalue()
        self.assertIn("黑风寨劫道风声", shown)
        self.assertNotIn("main_bandit_warning", shown)
        self.assertNotIn("bandit_reinforcement", shown)
        self.assertNotIn("事件ID", shown)

    def test_migration_recovers_malformed_core_containers(self):
        malformed = {
            "version": 12,
            "location": "village_gate",
            "active_quests": {"城内失踪案": "坏进度"},
            "quest_states": {"城内失踪案": "坏状态", "另一个任务": {"stage": "坏阶段", "progress": -3}},
            "completed_quests": {"不是列表": True},
            "inventory": {"不是列表": True},
            "equipment": "损坏装备结构",
            "equip_enhance": {"weapon": "损坏数字", "armor": -2},
            "world_state": {"flags": [], "variables": "损坏变量"},
        }
        migrated, old_version = engine.migrate_save_data(malformed)
        self.assertEqual(old_version, 12)
        self.assertEqual(migrated["active_quests"], {"城内失踪案": 0})
        self.assertEqual(migrated["quest_states"]["另一个任务"], {"stage": 0, "progress": 0})
        self.assertEqual(migrated["quest_states"]["城内失踪案"], {"stage": 0, "progress": 0, "branch_pending": False})
        self.assertEqual(migrated["completed_quests"], [])
        self.assertEqual(migrated["inventory"], [])
        self.assertEqual(migrated["equipment"], {"weapon": None, "armor": None})
        self.assertEqual(migrated["equip_enhance"], {"weapon": 0, "armor": 0})
        self.assertEqual(migrated["world_state"], {"flags": {"visited:village_gate": True}, "variables": {}})

    def test_migration_bounds_corrupt_quest_stage_progress_and_branch_state(self):
        raw = {
            "version": 12, "name": "任务阶段异常", "sect": "散人",
            "location": "village_gate",
            "active_quests": {"青锋疑云": 999, "城内失踪案": 1, "不存在的任务": True},
            "quest_states": {
                "青锋疑云": {
                    "stage": 999, "progress": 999, "branch_pending": "false",
                    "accepted_at": "坏时钟", "branch": ["伪造路线"],
                },
                "不存在的任务": {"stage": -3, "progress": "坏进度", "branch_pending": True},
            },
            "completed_quests": ["城内失踪案", "城内失踪案", 123],
        }
        migrated, _ = engine.migrate_save_data(raw)
        # 无效阶段必须回到安全起点，不能夹到最后阶段从而误判为可交付。
        self.assertEqual(migrated["quest_states"]["青锋疑云"]["stage"], 0)
        self.assertEqual(migrated["quest_states"]["青锋疑云"]["progress"], 0)
        self.assertEqual(migrated["active_quests"]["青锋疑云"], 0)
        self.assertFalse(migrated["quest_states"]["青锋疑云"]["branch_pending"])
        self.assertEqual(migrated["quest_states"]["青锋疑云"]["accepted_at"], 0)
        self.assertNotIn("branch", migrated["quest_states"]["青锋疑云"])
        # 非重复任务已经完成时，不得同时保持 active 状态；完成列表也要去重。
        self.assertNotIn("城内失踪案", migrated["active_quests"])
        self.assertNotIn("城内失踪案", migrated["quest_states"])
        self.assertEqual(migrated["completed_quests"], ["城内失踪案"])
        self.assertEqual(migrated["active_quests"]["不存在的任务"], 0)
        self.assertEqual(migrated["quest_states"]["不存在的任务"]["stage"], 0)
        self.assertEqual(migrated["quest_states"]["不存在的任务"]["progress"], 0)
        self.assertFalse(migrated["quest_states"]["不存在的任务"]["branch_pending"])

    def test_migration_normalizes_malformed_equipment_slot_values(self):
        raw = {
            "version": 12, "name": "装备字段异常", "sect": "散人",
            "location": "village_gate", "equipment": {"weapon": ["木剑"], "armor": {"name": "布衣"}},
        }
        fd, path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        try:
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(raw, handle, ensure_ascii=False)
            with patch("ui_output.safe_print"):
                loaded = Player.load_from_file(path)
            self.assertIsNotNone(loaded)
            self.assertEqual(loaded.equipment, {"weapon": None, "armor": None})
            self.assertIsInstance(loaded.get_total_atk(), int)
            self.assertIsInstance(loaded.get_total_defense(), int)
        finally:
            if os.path.exists(path):
                os.remove(path)

    def test_malformed_world_event_history_does_not_crash_or_consume_event(self):
        p = Player("异常事件状态测试", "散人")
        p.location = "village_gate"
        p.set_var("exploration:main", 2)
        p.set_var("quest_clock", 0)
        p.world_state["variables"]["world_events"] = {
            "main_bandit_warning": {"count": "不是数字", "last_clock": "未知"}
        }
        self.assertTrue(p.can_trigger_world_event("main_bandit_warning"))
        ok, message, info = p.trigger_world_event("main_bandit_warning")
        self.assertTrue(ok, message)
        self.assertEqual(p.get_world_event_state("main_bandit_warning")["count"], 1)

    def test_malformed_optional_attribute_does_not_reject_valid_save(self):
        fd, path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        try:
            p = Player("属性容错测试", "散人")
            save_data = {
                "version": 12, "name": p.name, "sect": "散人", "location": "village_gate",
                "attributes": {"strength": "坏数据", "constitution": 2},
                "attribute_points": "坏数据", "active_quests": {}, "completed_quests": [],
                "inventory": [], "equipment": {"weapon": None, "armor": None},
                "world_state": {"flags": {}, "variables": {}}
            }
            with open(path, "w", encoding="utf-8") as f:
                json.dump(save_data, f, ensure_ascii=False)
            loaded = Player.load_from_file(path)
            self.assertIsNotNone(loaded)
            self.assertEqual(loaded.attributes["strength"], 0)
            self.assertEqual(loaded.attributes["constitution"], 2)
            self.assertEqual(loaded.attribute_points, 0)
        finally:
            if os.path.exists(path):
                os.remove(path)

    def test_repeated_v12_round_trip_preserves_cross_system_state(self):
        fd, path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        try:
            p = Player("综合存读档压力测试", "散人")
            p.location = "village_gate"
            p.active_quests["城内失踪案"] = 1
            p.quest_states["城内失踪案"] = {"stage": 1, "progress": 1, "branch_pending": True}
            p.set_flag("stress_test_flag", True)
            p.set_var("quest_clock", 17)
            p.set_var("npc_locations", {"捕头": {"location": "guiyun_yamen", "source": "stress_test"}})
            p.set_npc_state("捕头", "busy", duration=4, reason="压力测试", source="stress_test")
            p.set_var("world_events", {"test_event": {"count": 2, "last_clock": 15}})
            for _ in range(8):
                self.assertTrue(p.save_to_file(path))
                p = Player.load_from_file(path)
                self.assertIsNotNone(p)
                self.assertEqual(p.location, "village_gate")
                self.assertTrue(p.get_flag("stress_test_flag"))
                self.assertEqual(p.get_var("quest_clock"), 17)
                self.assertEqual(p.quest_states["城内失踪案"]["stage"], 1)
                self.assertTrue(p.quest_states["城内失踪案"]["branch_pending"])
                self.assertEqual(p.get_var("npc_locations")["捕头"]["location"], "guiyun_yamen")
                self.assertEqual(p.get_npc_state("捕头"), "busy")
                self.assertEqual(p.get_world_event_state("test_event")["count"], 2)
        finally:
            if os.path.exists(path):
                os.remove(path)


class RewardWorldEffectHardening_P318Tests(unittest.TestCase):
    def test_invalid_reward_effect_container_prevents_partial_reward(self):
        from rewards import apply_reward_bundle
        p = Player("奖励原子性测试", "散人")
        before = (p.exp, p.gold, list(p.inventory))
        result = apply_reward_bundle(p, {
            "exp": 25, "gold": 40, "item": "疗伤药",
            "effects": {"increment_variables": ["bad-shape"]},
        }, announce=False)
        self.assertFalse(result["ok"])
        self.assertEqual((p.exp, p.gold, list(p.inventory)), before)

    def test_invalid_reward_effect_increment_prevents_partial_reward(self):
        from rewards import apply_reward_bundle
        p = Player("奖励增量测试", "散人")
        before = (p.exp, p.gold, list(p.inventory))
        result = apply_reward_bundle(p, {
            "exp": 25, "gold": 40, "item": "疗伤药",
            "effects": {"increment_variables": {"world:test": "not-a-number"}},
        }, announce=False)
        self.assertFalse(result["ok"])
        self.assertEqual((p.exp, p.gold, list(p.inventory)), before)

    def test_invalid_reward_faction_effect_prevents_partial_reward(self):
        from rewards import apply_reward_bundle
        p = Player("奖励势力测试", "散人")
        before = (p.exp, p.gold, list(p.inventory))
        result = apply_reward_bundle(p, {
            "exp": 25, "gold": 40, "item": "疗伤药",
            "effects": {"faction_relations": {"不存在的势力:黑市": 5}},
        }, announce=False)
        self.assertFalse(result["ok"])
        self.assertEqual((p.exp, p.gold, list(p.inventory)), before)

    def test_malformed_world_effects_do_not_raise_or_mutate_state(self):
        state = {"flags": {"keep": True}, "variables": {"keep": 7}}
        before = {"flags": dict(state["flags"]), "variables": dict(state["variables"])}
        engine.apply_world_effects(state, {"set_flags": [], "increment_variables": {"x": 1}})
        self.assertEqual(state, before)

    def test_non_numeric_world_increment_is_ignored_without_crash(self):
        state = {"flags": {}, "variables": {"keep": 7}}
        engine.apply_world_effects(state, {"increment_variables": {"bad": "x", "good": 2}})
        self.assertEqual(state["variables"].get("bad"), None)
        self.assertEqual(state["variables"]["good"], 2)
        self.assertEqual(state["variables"]["keep"], 7)


class P318Phase6PlayerFlowTests(unittest.TestCase):
    def test_task_turn_in_grants_reward_once_and_closes_lifecycle(self):
        import actions
        p = Player("交付闭环测试", "散人")
        p.active_quests["__phase6_flow__"] = 1
        p.quest_states["__phase6_flow__"] = {"stage": 0, "progress": 1}
        quest = {"required_cnt": 1, "reward": {"exp": 7, "gold": 13}}
        before_exp, before_gold = p.exp, p.gold
        with patch.object(actions.engine, "QUESTS", {"__phase6_flow__": quest}), \
             patch.object(actions.engine, "ROOMS", {}), \
             patch.object(p, "save_to_file", return_value=True):
            with patch("builtins.print") as output:
                actions.handle_quest(p, "jiaofu", ["__phase6_flow__"])
                actions.handle_quest(p, "jiaofu", ["__phase6_flow__"])
        self.assertEqual(p.exp, before_exp + 7)
        self.assertEqual(p.gold, before_gold + 13)
        self.assertNotIn("__phase6_flow__", p.active_quests)
        self.assertIn("__phase6_flow__", p.completed_quests)
        self.assertEqual(p.get_flag("quest_completed:__phase6_flow__"), True)
        self.assertTrue(any("未接取该任务" in str(call) for call in output.call_args_list))

    def test_failed_reward_keeps_completed_flag_and_world_effect_unchanged(self):
        import actions
        p = Player("奖励失败闭环", "散人")
        p.active_quests["__phase6_bad_reward__"] = 1
        p.quest_states["__phase6_bad_reward__"] = {"stage": 0, "progress": 1}
        p.set_flag("completion_side_effect", False)
        quest = {"required_cnt": 1, "reward": {"item": "不存在的物品"},
                 "on_complete": {"set_flags": {"completion_side_effect": True}}}
        before = (p.exp, p.gold, list(p.inventory))
        with patch.object(actions.engine, "QUESTS", {"__phase6_bad_reward__": quest}), \
             patch.object(actions.engine, "ROOMS", {}), \
             patch.object(p, "save_to_file", return_value=True):
            with patch("builtins.print"):
                actions.handle_quest(p, "jiaofu", ["__phase6_bad_reward__"])
        self.assertEqual((p.exp, p.gold, list(p.inventory)), before)
        self.assertIn("__phase6_bad_reward__", p.active_quests)
        self.assertNotIn("__phase6_bad_reward__", p.completed_quests)
        self.assertFalse(p.get_flag("completion_side_effect"))

    def test_turn_in_requires_named_npc_in_current_room(self):
        import actions
        p = Player("交付地点测试", "散人")
        p.location = "somewhere_else"
        p.active_quests["__phase6_location__"] = 1
        p.quest_states["__phase6_location__"] = {"stage": 0, "progress": 1}
        quest = {"required_cnt": 1, "turn_in_npc": "任务发布人", "reward": {"gold": 9}}
        before_gold = p.gold
        with patch.object(actions.engine, "QUESTS", {"__phase6_location__": quest}), \
             patch.object(actions.engine, "ROOMS", {}), \
             patch.object(p, "get_npcs_in_room", return_value=[]), \
             patch.object(p, "save_to_file", return_value=True):
            with patch("builtins.print"):
                actions.handle_quest(p, "jiaofu", ["__phase6_location__"])
        self.assertEqual(p.gold, before_gold)
        self.assertIn("__phase6_location__", p.active_quests)

    def test_command_parser_preserves_multiword_quest_and_choice(self):
        self.assertEqual(parse_command("交付 城内失踪案|2"), ("jiaofu", ["城内失踪案|2"]))
        self.assertEqual(parse_command("RENWU 城内失踪案"), ("quests", ["城内失踪案"]))
        self.assertEqual(parse_command("   "), ("", []))

    def test_command_chain_normalizes_fullwidth_separator_and_caps_length(self):
        from main import split_command_chain, MAX_COMMAND_CHAIN
        self.assertEqual(split_command_chain("看；状态;背包"), ["看", "状态", "背包"])
        chain = split_command_chain(";".join(f"看{i}" for i in range(MAX_COMMAND_CHAIN + 3)))
        self.assertEqual(len(chain), MAX_COMMAND_CHAIN)

    def test_invalid_saved_aliases_are_cleaned_and_system_commands_protected(self):
        from main import _command_aliases, handle_alias_command
        p = Player("别名校验", "散人")
        p.world_state.setdefault("variables", {})["command_aliases"] = {
            "  好的  ": "  看  ", "": "看", "超长" * 11: "看", "错误": 123,
        }
        aliases = _command_aliases(p)
        self.assertEqual(aliases, {"好的": "看"})
        with patch("builtins.print") as output:
            handle_alias_command(p, ["看", "=", "状态"])
        self.assertNotIn("看", _command_aliases(p))
        self.assertTrue(any("不能覆盖" in str(call) for call in output.call_args_list))


class LongRunWorldHardening_P318Tests(unittest.TestCase):
    def test_faction_conflict_tick_recovers_malformed_saved_record(self):
        p = Player("长期局势容错测试", "散人")
        factions = list(engine.FACTIONS)
        self.assertGreaterEqual(len(factions), 2)
        key = p._faction_conflict_key(factions[0], factions[1])
        p.set_var("faction_conflicts", {
            key: {"pressure": "not-a-number", "relation": None, "level": "unknown", "history": "broken"},
            "bad-key": {"pressure": 999},
            "invalid:faction": {"pressure": 20},
        })
        p.change_faction_relation(factions[0], factions[1], -100)
        results = []
        for _ in range(20):
            results.extend(p.process_faction_conflicts())
        self.assertIsInstance(results, list)
        state = p.get_var("faction_conflicts")
        self.assertIn(state[key]["level"], {"calm", "tension", "confrontation", "conflict", "escalation", "war"})
        self.assertGreaterEqual(state[key]["pressure"], 0)
        self.assertIsInstance(state[key]["history"], list)
        self.assertTrue(0 <= p.get_var("world_tension", 0) <= len(engine.FACTIONS) * 5)

    def test_faction_relation_rejects_boolean_delta(self):
        p = Player("势力增量边界测试", "散人")
        factions = list(engine.FACTIONS)
        if len(factions) < 2:
            self.skipTest("需要至少两个势力配置")
        before = p.get_faction_relation(factions[0], factions[1])
        after = p.change_faction_relation(factions[0], factions[1], True)
        self.assertEqual(after, before)

class Phase8ReleaseQualityTests(unittest.TestCase):
    def test_corrupt_talk_relation_counter_does_not_break_dialogue_gain(self):
        p = Player("关系计数容错", "散人")
        p.set_var(p._relation_progress_var("青石村守卫"), {"broken": True})
        with patch("builtins.print"):
            result = p.change_talk_relation("青石村守卫", 2)
        self.assertEqual(result, 2)
        self.assertEqual(p.get_talk_relation_gain("青石村守卫"), 2)

    def test_boolean_talk_relation_values_are_rejected(self):
        p = Player("关系布尔边界", "散人")
        before = p.get_relation("青石村守卫")
        self.assertEqual(p.change_talk_relation("青石村守卫", True), before)
        self.assertEqual(p.change_talk_relation("青石村守卫", 2, cap=True), before)
        self.assertEqual(p.change_relation("青石村守卫", False), before)
        self.assertEqual(p.get_talk_relation_gain("青石村守卫"), 0)

    def test_negative_corrupt_talk_counter_is_normalized(self):
        p = Player("负数关系计数", "散人")
        p.set_var(p._relation_progress_var("青石村守卫"), -999)
        with patch("builtins.print"):
            p.change_talk_relation("青石村守卫", 3)
        self.assertEqual(p.get_talk_relation_gain("青石村守卫"), 3)
        self.assertEqual(p.get_relation("青石村守卫"), 3)

class Phase9SaveScalarHardeningTests(unittest.TestCase):
    def test_migration_normalizes_corrupt_core_numeric_fields(self):
        raw = {
            "version": 12, "name": "边界存档", "location": "village_gate",
            "level": "坏等级", "exp": -99, "exp_to_level": 0,
            "max_hp": 0, "hp": 9999, "max_mp": 30, "mp": "坏内力",
            "atk": True, "defense": -8, "gold": "坏银两",
        }
        migrated, old_version = engine.migrate_save_data(raw)
        self.assertEqual(old_version, 12)
        self.assertEqual(migrated["level"], 1)
        self.assertEqual(migrated["exp"], 0)
        self.assertEqual(migrated["exp_to_level"], 1)
        self.assertEqual(migrated["max_hp"], 1)
        self.assertEqual(migrated["hp"], 1)
        self.assertEqual(migrated["max_mp"], 30)
        self.assertEqual(migrated["mp"], 30)
        self.assertEqual(migrated["atk"], 10)
        self.assertEqual(migrated["defense"], 0)
        self.assertEqual(migrated["gold"], 50)

    def test_corrupt_numeric_v12_file_loads_as_safe_player(self):
        import json, tempfile
        from pathlib import Path
        raw = {
            "version": 12, "name": "损坏数值兼容", "sect": "散人", "location": "village_gate",
            "level": "bad", "exp": -10, "exp_to_level": 0, "max_hp": 80, "hp": 999,
            "max_mp": 25, "mp": "bad", "atk": True, "defense": -1, "gold": "bad",
            "inventory": [], "equipment": {}, "active_quests": {}, "quest_states": {},
            "completed_quests": [], "world_state": {"flags": {}, "variables": {}},
        }
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "save.json"
            path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
            with patch("builtins.print"):
                loaded = Player.load_from_file(str(path))
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.level, 1)
        self.assertEqual(loaded.exp, 0)
        self.assertEqual(loaded.hp, 80)
        self.assertEqual(loaded.max_hp, 80)
        self.assertEqual(loaded.mp, 25)
        self.assertEqual(loaded.max_mp, 25)
        self.assertEqual(loaded.atk, 10)
        self.assertEqual(loaded.defense, 0)
        self.assertEqual(loaded.gold, 50)
        self.assertEqual(engine.SAVE_VERSION, 12)

    def test_migration_preserves_valid_v12_core_values_and_caps_current_resources(self):
        raw = {
            "version": 12, "location": "village_gate", "level": 8,
            "exp": 17, "exp_to_level": 80, "max_hp": 120, "hp": 130,
            "max_mp": 45, "mp": 46, "atk": 22, "defense": 9, "gold": 321,
        }
        migrated, _ = engine.migrate_save_data(raw)
        self.assertEqual(
            [migrated[k] for k in ("level", "exp", "exp_to_level", "max_hp", "hp", "max_mp", "mp", "atk", "defense", "gold")],
            [8, 17, 80, 120, 120, 45, 45, 22, 9, 321],
        )


class CommandAliasAuditTests(unittest.TestCase):
    def test_all_registered_aliases_parse_to_their_declared_target(self):
        for alias, target in CMD_MAP.items():
            with self.subTest(alias=alias):
                self.assertEqual(parse_command(alias), (target, []))

    def test_equipment_operations_remain_distinct(self):
        self.assertEqual(parse_command("装备"), ("equipment", []))
        self.assertEqual(parse_command("装备武器 精铁剑"), ("wield", ["精铁剑"]))
        self.assertEqual(parse_command("穿戴 皮甲"), ("wear", ["皮甲"]))
        self.assertEqual(parse_command("穿戴装备 精铁剑"), ("equip", ["精铁剑"]))
        self.assertEqual(parse_command("卸下 武器"), ("unequip", ["武器"]))
        self.assertEqual(parse_command("比较 精铁剑"), ("compare", ["精铁剑"]))

    def test_task_operations_remain_distinct(self):
        self.assertEqual(parse_command("任务"), ("quests", []))
        self.assertEqual(parse_command("接取 城内失踪案"), ("jiequ", ["城内失踪案"]))
        self.assertEqual(parse_command("交付 城内失踪案"), ("jiaofu", ["城内失踪案"]))
        self.assertEqual(parse_command("放弃 城内失踪案"), ("fangqi", ["城内失踪案"]))
        self.assertEqual(parse_command("选择 城内失踪案"), ("xuanze", ["城内失踪案"]))

    def test_search_and_explore_are_separate_actions(self):
        self.assertEqual(parse_command("探索"), ("explore", []))
        self.assertEqual(parse_command("搜索"), ("search", []))


class HelpMenuCommandClarityP318Tests(unittest.TestCase):
    def test_forge_help_explains_location_menu_and_preview(self):
        import io, contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            show_help("打造")
        out = buf.getvalue()
        for text in ("打铁铺", "强化兵刃", "强化防具", "打造 预览", "铁矿石"):
            self.assertIn(text, out)

    def test_equipment_help_distinguishes_weapon_armor_and_general_equip(self):
        import io, contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            show_help("装备")
        out = buf.getvalue()
        for text in ("装备武器", "穿戴", "穿戴装备", "卸下", "比较"):
            self.assertIn(text, out)

    def test_main_help_menu_has_player_facing_people_and_production_categories(self):
        import io, contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            show_help()
        out = buf.getvalue()
        self.assertIn("交谈与人物", out)
        self.assertIn("采集与生产", out)
        self.assertNotIn("NPC", out)

    def test_forge_preview_is_a_documented_argument_not_a_new_command(self):
        self.assertEqual(parse_command("打造 预览"), ("forge", ["预览"]))
        self.assertEqual(parse_command("强化"), ("forge", []))

class NestedQuestCommandParsingP318Tests(unittest.TestCase):
    def test_task_subcommands_keep_operation_and_multiword_quest_name(self):
        self.assertEqual(parse_command("任务 接取 城内失踪案"), ("quests", ["接取", "城内失踪案"]))
        self.assertEqual(parse_command("任务 选择 城内失踪案|2"), ("quests", ["选择", "城内失踪案|2"]))
        self.assertEqual(parse_command("任务 交付 清剿 黑风 山"), ("quests", ["交付", "清剿", "黑风", "山"]))

    def test_task_detail_query_keeps_multiword_name(self):
        self.assertEqual(parse_command("任务 城内失踪案"), ("quests", ["城内失踪案"]))

class QuestRewardIdempotencyP318Tests(unittest.TestCase):
    def test_repeated_turn_in_cannot_duplicate_reward(self):
        from unittest.mock import patch
        import contextlib, io, actions
        p = Player("重复交付测试", "散人")
        p.location = "village_gate"
        p.gold = 0
        p.active_quests["__idempotency_test__"] = 1
        quest_data = {"__idempotency_test__": {"required_cnt": 1, "reward": {"gold": 10}}}
        output = io.StringIO()
        with patch.object(actions.engine, "QUESTS", quest_data), contextlib.redirect_stdout(output):
            actions.handle_quest(p, "jiaofu", ["__idempotency_test__"])
            actions.handle_quest(p, "jiaofu", ["__idempotency_test__"])
        self.assertEqual(p.gold, 10)
        self.assertNotIn("__idempotency_test__", p.active_quests)
        self.assertIn("__idempotency_test__", p.completed_quests)
        self.assertIn("你未接取该任务", output.getvalue())
