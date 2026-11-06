import unittest
from io import StringIO
from unittest.mock import patch
import main


class Alpha66UiNoiseReductionTests(unittest.TestCase):
    def test_old_saved_queue_only_displays_deduplicated_travel_messages(self):
        class FakePlayer:
            economy_state = {
                "events": {
                    "pending_world_announcements": [
                        "【世界公告】南路商队已抵达村中广场，各地行商可前来交易。",
                        "【商旅消息】南路商队带来沿途货物，正在村中广场停留。",
                        "【江湖传闻】听闻南路商队已到村中广场，有买卖需求者不妨前往看看。",
                        "【商旅消息】南路商队带来沿途货物，正在村中广场停留。",
                    ]
                }
            }

        output = StringIO()
        with patch("sys.stdout", output):
            main.announce_pending_caravan_arrivals(FakePlayer())
        visible = output.getvalue()
        self.assertEqual(visible.count("【商旅消息】"), 1)
        self.assertNotIn("【世界公告】", visible)
        self.assertNotIn("【江湖传闻】", visible)
        self.assertEqual(FakePlayer.economy_state["events"]["pending_world_announcements"], [])


if __name__ == "__main__":
    unittest.main()
