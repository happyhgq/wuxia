"""Alpha55：普通店铺报价与成交统一响应当前行情事件。"""
import unittest
from actions import _market_event_rate, _market_quote


class QuotePlayer:
    def __init__(self, location="village_square", rate=1.0):
        self.location = location
        self.economy_state = {"events": {"market_event_rate": rate}, "market": {"木材": {"supply": 20}}}


class Alpha55MarketEventQuoteTests(unittest.TestCase):
    def test_ordinary_shop_quote_responds_to_market_event(self):
        normal = QuotePlayer(rate=1.0)
        boom = QuotePlayer(rate=1.5)
        normal_quote = _market_quote(normal, "木材", 10, "buy", 1.0)
        event_quote = _market_quote(boom, "木材", 10, "buy", 1.0)
        self.assertEqual(normal_quote, 10)
        self.assertEqual(event_quote, 15)

    def test_invalid_or_missing_event_rate_falls_back_to_normal(self):
        player = QuotePlayer(rate="broken")
        self.assertEqual(_market_event_rate(player), 1.0)
        player.economy_state = {}
        self.assertEqual(_market_event_rate(player), 1.0)
        self.assertEqual(_market_quote(player, "木材", 10, "buy"), 10)

    def test_buy_and_sell_quotes_both_use_event_rate(self):
        player = QuotePlayer(rate=1.2)
        self.assertEqual(_market_quote(player, "木材", 10, "buy", 1.0), 12)
        self.assertEqual(_market_quote(player, "木材", 10, "sell", 1.0), 12)


if __name__ == "__main__":
    unittest.main()
