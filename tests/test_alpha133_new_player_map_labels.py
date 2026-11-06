"""Alpha133：新手地图上的连续同名道路应可区分。"""
import unittest
import engine


class Alpha133NewPlayerMapLabelTests(unittest.TestCase):
    def test_main_map_disambiguates_three_road_segments(self):
        rendered = engine.MAP_ENGINE.render("village_gate")
        # 地图节点使用紧凑简称，避免长道路名撑宽整列；完整名称仍由出口显示名保留。
        for label in ("官道·村口", "官道·东段", "官道·城南"):
            with self.subTest(label=label):
                self.assertIn(label, rendered)
        self.assertIn("黄土官道（村口段）", rendered)
        self.assertEqual(engine.MAP_ENGINE.display_name("official_road_east_1"), "黄土官道（东段）")

    def test_direction_destination_uses_same_disambiguated_label(self):
        rendered = engine.MAP_ENGINE.render("official_road")
        self.assertIn("东 -> 黄土官道（东段）", rendered)

    def test_room_names_and_save_location_ids_remain_unchanged(self):
        self.assertEqual(engine.ROOMS["official_road"]["name"], "黄土官道")
        self.assertEqual(engine.ROOMS["official_road_east_1"]["name"], "黄土官道")
        self.assertEqual(engine.ROOMS["official_road_east_2"]["name"], "黄土官道")
        self.assertEqual(engine.SAVE_VERSION, 12)


if __name__ == "__main__":
    unittest.main()
