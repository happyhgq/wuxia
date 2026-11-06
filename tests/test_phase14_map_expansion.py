import json
import os
import unittest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(BASE, 'data')

class Phase14MapExpansionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(os.path.join(DATA, 'rooms.json'), encoding='utf-8') as f:
            cls.rooms = json.load(f)
        with open(os.path.join(DATA, 'world_regions.json'), encoding='utf-8') as f:
            cls.regions = json.load(f)

    def test_all_new_regions_have_rooms(self):
        for zone in ('mistwood', 'sunken_ruins', 'northfront_town'):
            self.assertIn(zone, self.regions)
            self.assertTrue(any(r.get('zone') == zone for r in self.rooms.values()))

    def test_new_zone_internal_exits_are_reciprocal_and_adjacent(self):
        vectors = {'北': (0, 1), '南': (0, -1), '东': (1, 0), '西': (-1, 0)}
        opposite = {'北': '南', '南': '北', '东': '西', '西': '东'}
        zones = {'mistwood', 'sunken_ruins', 'northfront_town'}
        for rid, room in self.rooms.items():
            if room.get('zone') not in zones:
                continue
            for direction, target_id in room.get('exits', {}).items():
                target = self.rooms[target_id]
                if target.get('zone') != room.get('zone'):
                    continue
                dx, dy = vectors[direction]
                self.assertEqual((room['coord'][0] + dx, room['coord'][1] + dy), tuple(target['coord']))
                reverse = target.get('exits', {}).get(opposite[direction])
                hidden_reverse = target.get('hidden_exits', {}).get(opposite[direction], {})
                self.assertTrue(reverse == rid or (isinstance(hidden_reverse, dict) and hidden_reverse.get('target') == rid))

    def test_each_new_zone_is_fully_reachable_from_its_gate(self):
        gates = {'mistwood': 'mistwood_trail', 'sunken_ruins': 'sunken_stairs', 'northfront_town': 'northfront_gate'}
        for zone, start in gates.items():
            seen, pending = set(), [start]
            while pending:
                rid = pending.pop()
                if rid in seen:
                    continue
                seen.add(rid)
                targets = list(self.rooms[rid].get('exits', {}).values())
                targets.extend(entry.get('target') for entry in self.rooms[rid].get('hidden_exits', {}).values() if isinstance(entry, dict))
                for target in targets:
                    if self.rooms[target].get('zone') == zone and target not in seen:
                        pending.append(target)
            expected = {rid for rid, room in self.rooms.items() if room.get('zone') == zone}
            self.assertEqual(expected, seen)

    def test_all_three_regions_have_cross_zone_return_routes(self):
        links = [('wild_fields', 'mistwood_trail'), ('bandit_back_mountain', 'sunken_stairs'), ('guiyun_south_gate', 'northfront_gate')]
        for old_id, new_id in links:
            old, new = self.rooms[old_id], self.rooms[new_id]
            self.assertIn(new_id, old.get('exits', {}).values())
            self.assertIn(old_id, new.get('exits', {}).values())
            self.assertNotEqual(old.get('zone'), new.get('zone'))

if __name__ == '__main__':
    unittest.main()
