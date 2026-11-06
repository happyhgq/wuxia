import contextlib
import io
import unittest
from pathlib import Path

from ui_output import safe_print, sanitize_player_text

BASE = Path(__file__).resolve().parents[1]


class InternalOutputFirewallTests(unittest.TestCase):
    def test_namespaced_world_and_quest_ids_are_not_displayed(self):
        rendered = sanitize_player_text('任务状态：quest:mistwood_herbs:resolved；world:trade_network:warehouse_evidence_secured')
        self.assertNotIn('quest:', rendered)
        self.assertNotIn('world:', rendered)
        self.assertNotIn('mistwood_herbs', rendered)
        self.assertNotIn('warehouse_evidence_secured', rendered)

    def test_code_names_and_file_paths_are_not_displayed(self):
        rendered = sanitize_player_text('读取 game/actions.py 时发生错误，字段 transfer_chain_evidence 无效')
        self.assertNotIn('actions.py', rendered)
        self.assertNotIn('transfer_chain_evidence', rendered)
        self.assertNotIn('game/', rendered)

    def test_traceback_and_structured_objects_are_suppressed(self):
        self.assertEqual(sanitize_player_text('Traceback (most recent call last): ValueError'), '相关操作未能完成，请稍后重试。')
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            safe_print({'event_id': 'guiyun_transfer_warehouse_review', 'flag': 'quest:foo'})
        self.assertEqual(output.getvalue().strip(), '相关信息暂不可查看。')
        self.assertNotIn('guiyun_transfer_warehouse_review', output.getvalue())


    def test_english_internal_statuses_are_localized_for_current_and_old_saves(self):
        rendered = sanitize_player_text('状态：忙碌（官府与黑市局势升级至confrontation）')
        self.assertEqual(rendered, '状态：忙碌（官府与黑市局势升级至对峙）')
        self.assertEqual(sanitize_player_text('冲突状态：conflict_fatigue'), '冲突状态：冲突暂歇')
        self.assertEqual(sanitize_player_text('status: event_affected'), 'status: 受事件影响')

    def test_common_world_levels_never_leak_english(self):
        for token, label in [('calm', '平静'), ('tension', '紧张'), ('confrontation', '对峙'), ('conflict', '冲突'), ('escalation', '升级'), ('war', '战乱')]:
            self.assertNotIn(token, sanitize_player_text(f'局势进入{token}阶段').lower())
            self.assertIn(label, sanitize_player_text(f'局势进入{token}阶段'))

    def test_normal_game_numbers_and_item_names_are_preserved(self):
        self.assertEqual(sanitize_player_text('气血 100/100，内力 50/50'), '气血 100/100，内力 50/50')
        self.assertEqual(sanitize_player_text('获得战利品【金创药】×1'), '获得战利品【金创药】×1')

    def test_exploration_never_dumps_raw_event_dictionary(self):
        source = (BASE / 'actions.py').read_text(encoding='utf-8')
        self.assertNotIn('print(str(event))', source)
        self.assertIn('print("你仔细搜索了一番，没有发现值得记录的线索。")', source)
        self.assertNotIn("event.get('title', event.get('event_id'", source)


if __name__ == '__main__':
    unittest.main()
