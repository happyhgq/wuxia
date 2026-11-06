import json
import os
import unittest
from player import Player

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(BASE, 'data')

def load(name):
    with open(os.path.join(DATA, name), encoding='utf-8') as f:
        return json.load(f)

class Phase16To18ExpansionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rooms = load('rooms.json')
        cls.npcs = load('npcs.json')
        cls.enemies = load('enemies.json')
        cls.items = load('items.json')
        cls.quests = load('quests.json')
        cls.events = load('world_events.json')

    def test_three_region_quest_chain_exists_and_is_ordered(self):
        expected = ['雾隐失药案', '沉河旧商队遗证', '北境失货追查']
        for name in expected:
            self.assertIn(name, self.quests)
            quest = self.quests[name]
            self.assertIn(quest['npc'], self.npcs)
            self.assertIn(quest['turn_in_npc'], self.npcs)
            self.assertGreaterEqual(len(quest['stages']), 3)
            self.assertIn('reward', quest)
        self.assertIn('quest:mistwood_herbs:resolved', self.quests['沉河旧商队遗证']['requires']['flags'])
        self.assertIn('sunken_ruins:caravan_truth_known', self.quests['北境失货追查']['requires']['flags'])

    def test_all_new_quest_stage_targets_resolve(self):
        for name in ['雾隐失药案', '沉河旧商队遗证', '北境失货追查']:
            q = self.quests[name]
            stages = q['stages']
            for stage in stages:
                target = stage['target_name']
                if stage['target_type'] == 'kill':
                    self.assertIn(target, self.enemies, f'{name}: {target}')
                elif stage['target_type'] == 'talk':
                    self.assertIn(target, self.npcs, f'{name}: {target}')

    def test_new_quest_rewards_reference_existing_items_and_valid_routes(self):
        for name in ['雾隐失药案', '沉河旧商队遗证', '北境失货追查']:
            reward = self.quests[name]['reward']
            if reward.get('item'):
                self.assertIn(reward['item'], self.items)
            if reward.get('jianghu_action'):
                self.assertIn(reward['jianghu_action'], {'help_people','rescue_npc','assist_officials','escort_trade','black_market_trade','refuse_factions','solo_explore'})

    def test_six_new_world_events_are_region_bound_and_once_or_cooldown(self):
        expected = {
            'mistwood_herb_cache':'mistwood', 'mistwood_beast_signs':'mistwood',
            'sunken_inscription':'sunken_ruins', 'sunken_channel_cache':'sunken_ruins',
            'northfront_cargo_manifest':'northfront_town', 'northfront_wharf_patrol':'northfront_town'
        }
        for event_id, region in expected.items():
            self.assertIn(event_id, self.events)
            event = self.events[event_id]
            self.assertEqual(event['region'], region)
            self.assertTrue(event.get('once') or isinstance(event.get('cooldown'), int))
            self.assertTrue(event.get('title'))
            self.assertTrue(event.get('text'))

    def test_event_rewards_reference_valid_items_and_npcs(self):
        for event_id in ['mistwood_herb_cache','mistwood_beast_signs','sunken_inscription','sunken_channel_cache','northfront_cargo_manifest','northfront_wharf_patrol']:
            rewards = self.events[event_id].get('rewards', {})
            if rewards.get('item'):
                self.assertIn(rewards['item'], self.items, event_id)
            for npc in rewards.get('relations', {}):
                self.assertIn(npc, self.npcs, event_id)

    def test_event_once_reward_and_v12_state_round_trip(self):
        p = Player('区域事件验收', '散人')
        p.location = 'mistwood_trail'
        p.set_var('exploration:mistwood', 1)
        start_gold = p.gold
        ok, message, info = p.trigger_world_event('雾林药草补给')
        self.assertTrue(ok, message)
        self.assertEqual(info.get('title'), '雾林药草补给')
        self.assertGreaterEqual(p.gold, start_gold + 12)
        self.assertTrue(p.get_flag('world:mistwood:herb_cache_found'))
        ok2, _, _ = p.trigger_world_event('雾林药草补给')
        self.assertFalse(ok2)
        state = p.world_state
        p2 = Player('区域事件读档验收', '散人')
        p2.world_state = state
        self.assertTrue(p2.get_flag('world:mistwood:herb_cache_found'))

    def test_new_quest_stage_progression_can_advance(self):
        p = Player('任务阶段验收', '散人')
        p.active_quests['雾隐失药案'] = 0
        p.quest_states['雾隐失药案'] = {'stage': 0, 'progress': 0}
        p.update_quest_progress('失踪猎户的同伴', 'talk')
        self.assertEqual(p.quest_states['雾隐失药案']['stage'], 1)
        p.update_quest_progress('迷雾毒蛛', 'kill')
        self.assertEqual(p.quest_states['雾隐失药案']['stage'], 1)
        p.update_quest_progress('迷雾毒蛛', 'kill')
        self.assertEqual(p.quest_states['雾隐失药案']['stage'], 2)


    def test_first_region_quest_can_finish_and_reward_is_not_repeated(self):
        import contextlib, io
        from actions import handle_quest
        p = Player('区域任务闭环验收', '散人')
        qname = '雾隐失药案'
        p.active_quests[qname] = 0
        p.quest_states[qname] = {'stage': 0, 'progress': 0}
        p.update_quest_progress('失踪猎户的同伴', 'talk')
        p.update_quest_progress('迷雾毒蛛', 'kill')
        p.update_quest_progress('迷雾毒蛛', 'kill')
        p.update_quest_progress('采药人阿芷', 'talk')
        npc_room = next(rid for rid, room in self.rooms.items() if '采药人阿芷' in room.get('npcs', []))
        p.location = npc_room
        before_gold = p.gold
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            handle_quest(p, 'jiaofu', [qname])
        self.assertIn(qname, p.completed_quests)
        self.assertGreaterEqual(p.gold, before_gold + 45)
        after_gold = p.gold
        with contextlib.redirect_stdout(io.StringIO()):
            handle_quest(p, 'jiaofu', [qname])
        self.assertEqual(p.gold, after_gold)

    def test_save_version_remains_v12(self):
        import engine
        self.assertEqual(engine.SAVE_VERSION, 12)

if __name__ == '__main__':
    unittest.main()
