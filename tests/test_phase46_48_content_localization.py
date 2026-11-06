import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path

import engine
from actions import handle_quest
from main import parse_command, show_help, show_encyclopedia
from player import Player

BASE = Path(__file__).resolve().parents[1]
DATA = BASE / 'data'


def load(name):
    return json.loads((DATA / name).read_text(encoding='utf-8'))


class Phase46To48ContentTests(unittest.TestCase):
    def test_transfer_warehouse_quest_is_connected_to_existing_story_chain(self):
        quests = load('quests.json')
        npcs = load('npcs.json')
        rooms = load('rooms.json')
        enemies = load('enemies.json')
        quest = quests['暗仓转运疑云']
        self.assertEqual(quest['npc'], '万商会会长')
        self.assertIn('world:trade_network:transfer_chain_traced', quest['requires']['flags'])
        self.assertIn('northfront:trade_route_safe', quest['requires']['flags'])
        self.assertIn('暗仓转运疑云', npcs['万商会会长']['quests'])
        self.assertIn('北境货栈掌柜', npcs)
        self.assertIn('货船伙计小满', npcs)
        self.assertIn('河埠私枭', enemies)
        self.assertIn('河埠私枭', rooms['northfront_wharf'].get('enemies', []))
        self.assertEqual(quest['stages'][-1]['target_name'], '万商会会长')
        self.assertTrue(quest['on_complete']['set_flags']['world:trade_network:warehouse_evidence_secured'])
        events = load('world_events.json')
        review = events['guiyun_transfer_warehouse_review']
        self.assertIn('quest:transfer_warehouse:resolved', review['requires']['flags'])
        self.assertTrue(review['once'])
        self.assertEqual(review['region'], 'guiyun_city')

    def test_quest_can_be_accepted_only_after_story_prerequisites(self):
        p = Player('暗仓任务验收', '散人')
        p.location = 'guiyun_merchant_guild'
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            handle_quest(p, 'jiequ', ['暗仓转运疑云'])
        self.assertNotIn('暗仓转运疑云', p.active_quests)
        self.assertIn('不满足接取', out.getvalue())
        p.set_flag('world:trade_network:transfer_chain_traced', True)
        p.set_flag('northfront:trade_route_safe', True)
        p.set_flag('visited_zone:northfront_town', True)
        p.level = 8
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            handle_quest(p, 'jiequ', ['暗仓转运疑云'])
        self.assertIn('暗仓转运疑云', p.active_quests)
        self.assertIn('已接取任务', out.getvalue())

    def test_warehouse_review_event_is_one_time_and_v12_safe(self):
        p = Player('暗仓会审验收', '散人')
        p.location = 'guiyun_merchant_guild'
        p.set_flag('quest:transfer_warehouse:resolved', True)
        p.set_flag('world:trade_network:warehouse_evidence_secured', True)
        first_ok, _, _ = p.trigger_world_event('guiyun_transfer_warehouse_review')
        second_ok, _, _ = p.trigger_world_event('guiyun_transfer_warehouse_review')
        self.assertTrue(first_ok)
        self.assertFalse(second_ok)
        self.assertTrue(p.get_flag('world:trade_network:warehouse_reviewed'))
        self.assertEqual(engine.SAVE_VERSION, 12)

    def test_quest_rewards_and_stage_counts_are_valid(self):
        quest = load('quests.json')['暗仓转运疑云']
        self.assertEqual([s['target_type'] for s in quest['stages']], ['talk', 'kill', 'talk', 'talk'])
        self.assertTrue(all(int(s.get('required_cnt', 1)) > 0 for s in quest['stages']))
        self.assertGreater(quest['reward']['gold'], 0)
        self.assertGreater(quest['reward']['exp'], 0)
        self.assertIn(quest['reward']['item'], load('items.json'))

    def test_v12_save_schema_remains_unchanged(self):
        self.assertEqual(engine.SAVE_VERSION, 12)
        p = Player('阶段验收角色', '散人')
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, 'save.json')
            with contextlib.redirect_stdout(io.StringIO()):
                p.save_to_file(path)
            raw = json.loads(Path(path).read_text(encoding='utf-8'))
        self.assertEqual(raw.get('version'), 12)
        self.assertNotIn('dialogue_state', raw)

    def test_player_help_no_longer_displays_npc_abbreviation(self):
        main_source = (BASE / 'main.py').read_text(encoding='utf-8')
        actions_source = (BASE / 'actions.py').read_text(encoding='utf-8')
        self.assertNotIn('公告、NPC、存档', main_source)
        self.assertNotIn('与 NPC 交谈', actions_source)
        self.assertNotIn('输入 jiequ', actions_source)
        self.assertNotIn('查看 NPC 基本情况', main_source)
        self.assertNotIn('V12 存档结构', main_source)

    def test_help_and_encyclopedia_do_not_print_internal_english_labels(self):
        for renderer, args in ((show_help, ('人物',)), (show_encyclopedia, ('人物',)), (show_help, ())):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                renderer(*args)
            rendered = output.getvalue()
            self.assertNotIn('NPC', rendered)
            self.assertNotIn('n/s/e/w', rendered)
            self.assertNotIn('V12', rendered)
            self.assertNotIn('.json', rendered)
            self.assertNotIn('.py', rendered)

    def test_chinese_talk_alias_still_parses_after_output_localization(self):
        self.assertEqual(parse_command('交谈 万商会会长 暗仓'), ('talk', ['万商会会长', '暗仓']))


if __name__ == '__main__':
    unittest.main()
