import json
import os
import unittest
import engine
from player import Player

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(BASE, 'data')
def load(name):
    with open(os.path.join(DATA, name), encoding='utf-8') as f:
        return json.load(f)

class Phase19To21ExpansionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.quests = load('quests.json')
        cls.items = load('items.json')
        cls.skills = load('skills.json')
        cls.factions = load('factions.json')

    def test_sunken_and_northfront_quests_have_meaningful_branches(self):
        for qname in ('沉河旧商队遗证', '北境失货追查'):
            choices = self.quests[qname]['choices']
            self.assertEqual(len(choices), 2)
            self.assertNotEqual(choices[0]['effects'], choices[1]['effects'])
            for choice in choices:
                self.assertIn(choice['reward']['item'], self.items)
                self.assertTrue(choice['effects'].get('set_flags'))
                self.assertTrue(choice['effects'].get('faction_relations'))

    def test_branch_effects_persist_in_world_state_and_are_distinct(self):
        p_official = Player('路线官府验收', '散人')
        p_black = Player('路线黑市验收', '散人')
        official = self.quests['沉河旧商队遗证']['choices'][0]['effects']
        black = self.quests['沉河旧商队遗证']['choices'][1]['effects']
        engine.apply_world_effects(p_official.world_state, official)
        engine.apply_world_effects(p_black.world_state, black)
        self.assertTrue(p_official.get_flag('sunken_ruins:evidence_to_officials'))
        self.assertTrue(p_black.get_flag('sunken_ruins:evidence_to_black_market'))
        self.assertNotEqual(p_official.world_state['variables'], p_black.world_state['variables'])

    def test_new_items_have_valid_existing_schema(self):
        expected = {'雾隐短刃','沉河护腕','北境巡河刀','行商软甲','清心散','行军干粮'}
        self.assertTrue(expected.issubset(self.items))
        for name in expected:
            item = self.items[name]
            self.assertIn(item['type'], {'weapon','armor','consumable'})
            self.assertGreaterEqual(item.get('price', 0), 0)
            if item['type'] in {'weapon','armor'}:
                self.assertIn(item.get('slot'), {'weapon','armor'})
            if item['type'] == 'consumable':
                self.assertTrue(item.get('effect'))

    def test_new_wanderer_skills_have_unique_names_and_valid_combat_effects(self):
        skills = self.skills['散人']
        names = [x['name'] for x in skills]
        self.assertEqual(len(names), len(set(names)))
        expected = {'流云步','回风刺','破势掌','凝息诀'}
        self.assertTrue(expected.issubset(set(names)))
        for skill in skills:
            if skill['name'] in expected:
                self.assertIn(skill['effect']['type'], {'status','self_status','combo'})
                self.assertGreater(skill['mp_cost'], 0)
                self.assertGreater(skill['power'], 0)

    def test_new_skills_can_be_learned_by_wanderer_and_keep_unique_state(self):
        p = Player('新武学验收', '散人')
        p.level = 10
        for name in ('流云步', '回风刺', '破势掌', '凝息诀'):
            ok, reason = p.learn_skill(name)
            self.assertTrue(ok, f'{name}: {reason}')
            self.assertTrue(p.get_skill_progress(name)['learned'])

    def test_choice_rewards_make_new_equipment_obtainable(self):
        awarded = set()
        for qname in ('沉河旧商队遗证', '北境失货追查'):
            for choice in self.quests[qname]['choices']:
                awarded.add(choice['reward'].get('item'))
        self.assertTrue({'沉河护腕', '北境巡河刀', '行商软甲'}.issubset(awarded))

    def test_save_version_remains_v12(self):
        self.assertEqual(engine.SAVE_VERSION, 12)

if __name__ == '__main__':
    unittest.main()
