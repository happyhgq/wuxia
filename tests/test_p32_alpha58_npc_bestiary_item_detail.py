"""Alpha58：人物、敌人、物品详情字段及展示回归。"""
import contextlib, io, json, os, unittest
from actions import look
from player import Player
BASE = os.path.dirname(os.path.dirname(__file__))
def read(name):
    with open(os.path.join(BASE, 'data', name), encoding='utf-8') as f: return json.load(f)
class Alpha58DetailTests(unittest.TestCase):
    def test_all_npcs_have_identity_and_behavior_details(self):
        npcs=read('npcs.json')
        for name,d in npcs.items():
            for field in ('appearance','voice','demeanor','behavior_hint'):
                self.assertTrue(str(d.get(field,'')).strip(), f'{name}: {field}')
    def test_all_enemies_have_description_and_tactical_hint(self):
        enemies=read('enemies.json')
        for name,d in enemies.items():
            self.assertTrue(str(d.get('desc','')).strip(), name)
            self.assertTrue(str(d.get('combat_hint','')).strip(), name)
    def test_equipment_and_materials_have_item_detail(self):
        items=read('items.json')
        for name,d in items.items():
            if d.get('type') in ('weapon','armor','material','consumable'):
                self.assertTrue(d.get('material'), name)
                self.assertTrue(d.get('condition'), name)
                self.assertTrue(d.get('craft_note'), name)
    def test_npc_inspection_shows_new_identity_fields(self):
        p=Player('测试侠客')
        p.set_var('quest_clock', 7)  # 13:00，避开守卫巡逻日程
        p.location='village_gate'
        out=io.StringIO()
        with contextlib.redirect_stdout(out): look(p,['守卫'])
        val=out.getvalue()
        self.assertIn('他穿着一身粗布甲胄', val)
        self.assertIn('他约莫三十来岁。', val)
        self.assertIn('他看起来有些拳脚底子，枪势沉稳，守多于攻。', val)
        self.assertIn('他装备着：', val)
        for text in ('相貌衣着','言谈声音','行事气度','相处提示','随身装备','关系：','势力：'):
            self.assertNotIn(text, val)
    def test_enemy_inspection_shows_description_and_tactic(self):
        p=Player('测试侠客'); p.location='mistwood_trail'
        room=read('rooms.json')[p.location]
        if not room.get('enemies'):
            self.skipTest('测试房间无敌人配置')
        out=io.StringIO()
        with contextlib.redirect_stdout(out): look(p,[room['enemies'][0]])
        val=out.getvalue()
        self.assertIn('应对建议',val)
if __name__=='__main__': unittest.main()
