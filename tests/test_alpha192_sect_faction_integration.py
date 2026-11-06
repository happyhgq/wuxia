import json
import os
import unittest

import engine
from player import Player


class Alpha192SectFactionIntegrationTests(unittest.TestCase):
    def test_formal_sects_are_registered_as_world_factions(self):
        for sect in ("少林", "武当", "华山"):
            self.assertIn(sect, engine.SECTS)
            self.assertIn(sect, engine.FACTIONS)
            self.assertIsInstance(engine.FACTIONS[sect].get("relations"), dict)

    def test_core_sect_npcs_have_their_own_faction(self):
        expected = {
            "少林守山僧": "少林", "少林接引僧": "少林", "少林知客师兄": "少林",
            "少林传功师父": "少林", "少林传功师兄": "少林", "少林戒律僧": "少林",
            "少林守阁僧": "少林", "少林巡院僧": "少林",
            "武当守山弟子": "武当", "武当接引道人": "武当", "武当执事弟子": "武当",
            "武当传功师父": "武当", "武当传功师兄": "武当",
            "华山守门弟子": "华山", "华山接引执事": "华山",
            "华山传功师兄": "华山", "华山授业师父": "华山",
        }
        player = Player("门派势力核验")
        for npc, faction in expected.items():
            with self.subTest(npc=npc):
                self.assertEqual(engine.NPCS[npc].get("faction"), faction)
                self.assertEqual(player.get_npc_faction(npc), faction)

    def test_sect_regions_expose_the_correct_sect_without_losing_jianghu(self):
        expected = {
            "shaolin_mountain": "少林",
            "wudang_mountain": "武当",
            "huashan_mountain": "华山",
        }
        for region, sect in expected.items():
            with self.subTest(region=region):
                exposure = engine.WORLD_REGIONS[region].get("faction_exposure", [])
                self.assertIn("江湖", exposure)
                self.assertIn(sect, exposure)

    def test_sect_relations_are_symmetric_and_do_not_start_as_war(self):
        for a in ("少林", "武当", "华山"):
            for b in ("少林", "武当", "华山"):
                if a == b:
                    continue
                with self.subTest(pair=(a, b)):
                    ab = engine.FACTIONS[a]["relations"][b]
                    ba = engine.FACTIONS[b]["relations"][a]
                    self.assertEqual(ab, ba)
                    self.assertGreater(ab, -60)

    def test_sect_to_general_faction_relations_are_defined(self):
        for sect in ("少林", "武当", "华山"):
            for faction in ("青石村", "官府", "商会", "黑市", "江湖", "沈府", "黑风寨"):
                with self.subTest(pair=(sect, faction)):
                    self.assertIn(faction, engine.FACTIONS[sect]["relations"])
                    self.assertEqual(
                        engine.FACTIONS[sect]["relations"][faction],
                        engine.FACTIONS[faction]["relations"][sect],
                    )


if __name__ == "__main__":
    unittest.main()
