"""Alpha248：门派高阶武学/专属装备、内院地图和铁矿—黑风后山路线闭环。"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def load(name):
    return json.loads((ROOT / 'data' / name).read_text(encoding='utf-8'))

def test_three_major_sects_have_gated_advanced_rooms_and_signature_skills():
    rooms, sects, skills = load('rooms.json'), load('sects.json'), load('skills.json')
    expected = {
        '少林': ('shaolin_vajra_court', '金刚护体拳', '少林戒棍'),
        '武当': ('wudang_taiji_courtyard', '绕指柔剑', '武当云纹剑'),
        '华山': ('huashan_sword_lecture_hall', '苍松迎客剑', '华山松纹剑'),
    }
    items, quests = load('items.json'), load('quests.json')
    quest_names = {'少林':'少林历练·黑风除恶','武当':'武当历练·以静制动','华山':'华山历练·磨剑黑风'}
    for sect, (room_id, skill_name, item_name) in expected.items():
        room = rooms[room_id]
        assert room['access']['sect'] == sect
        assert room['access']['min_rank_index'] >= 3
        skill = next(x for x in skills[sect] if x['name'] == skill_name)
        assert skill['learn_min_rank'] >= 2 and skill['learn_min_reputation'] >= 50
        assert skill_name in sects[sect]['exclusive_skills']
        assert items[item_name]['type'] == 'weapon'
        assert quests[quest_names[sect]]['reward']['item'] == item_name

def test_iron_corridor_quarry_and_blackwind_back_mountain_are_connected():
    rooms = load('rooms.json')
    assert rooms['abandoned_iron_mine']['exits']['北'] == 'collapsed_quarry'
    assert rooms['collapsed_quarry']['exits']['东'] == 'deep_iron_gallery'
    assert rooms['deep_iron_gallery']['exits']['西'] == 'collapsed_quarry'
    assert rooms['collapsed_quarry']['exits']['北'] == 'mistwood_ridge_path'
    assert rooms['mistwood_ridge_path']['exits']['东'] == 'bandit_back_mountain'
    assert rooms['bandit_back_mountain']['exits']['西'] == 'mistwood_ridge_path'
    assert rooms['mistwood_ridge_path']['recommended_level'] >= 7

def test_all_new_same_zone_exits_are_reciprocal_and_coordinate_consistent():
    rooms = load('rooms.json')
    vec = {'北':(0,1),'南':(0,-1),'东':(1,0),'西':(-1,0)}
    opposite = {'北':'南','南':'北','东':'西','西':'东'}
    audited = {'shaolin_scripture_court','shaolin_vajra_court','wudang_zhenwu_hall',
               'wudang_taiji_courtyard','huashan_master_hall','huashan_sword_lecture_hall',
               'abandoned_iron_mine','collapsed_quarry','deep_iron_gallery','mistwood_ridge_path'}
    for room_id in audited:
        room = rooms[room_id]
        for direction, target_id in room.get('exits',{}).items():
            target = rooms[target_id]
            if target_id not in audited or room.get('zone','main') != target.get('zone','main'):
                continue
            x,y = room['coord']; tx,ty = target['coord']; dx,dy = vec[direction]
            assert (tx,ty) == (x+dx,y+dy), (room_id,direction,target_id)
            assert target.get('exits',{}).get(opposite[direction]) == room_id, (room_id,direction,target_id)

def test_signature_skills_obey_formal_sect_rank_and_reputation_gates():
    from player import Player
    cases = [('少林','金刚护体拳'),('武当','绕指柔剑'),('华山','苍松迎客剑')]
    for sect, skill_name in cases:
        player = Player(f'Alpha248-{sect}', '散人')
        player.level = 10
        assert player.join_sect(sect)[0]
        # Reputation alone must not bypass formal promotion.
        player.change_sect_reputation(sect, 150)
        ok, reason = player.can_learn_skill(skill_name)
        assert not ok and '正式晋升' in reason
        player._sect_progress_state()[sect]['official_rank_index'] = 2
        player.change_sect_reputation(sect, -150)
        ok, reason = player.can_learn_skill(skill_name)
        assert not ok and '声望' in reason
        player.change_sect_reputation(sect, 50)
        player.level = 10
        ok, reason = player.can_learn_skill(skill_name)
        assert ok, (sect, reason)
