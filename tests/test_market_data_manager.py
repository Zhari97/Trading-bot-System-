import unittest

from market_data_manager import MarketDataCache, cache_key


class MarketDataCacheTests(unittest.TestCase):
    def test_closed_bucket_reuses_value(self):
        cache = MarketDataCache(clock=lambda: 1000.0)
        calls = []

        def fetch():
            calls.append(1)
            return {"close": 123}

        value1 = cache.get_or_fetch("kraken:XBTUSD:15m", 900, fetch)
        value2 = cache.get_or_fetch("kraken:XBTUSD:15m", 900, fetch)

        self.assertEqual(value1, value2)
        self.assertEqual(len(calls), 1)

    def test_cache_key_is_stable(self):
        self.assertEqual(cache_key("Kraken", "xbtusd", 15), "kraken:XBTUSD:15m")

    def test_cache_misses_after_new_closed_bucket(self):
        now = [1000.0]
        cache = MarketDataCache(clock=lambda: now[0])
        calls = []

        def fetch():
            calls.append(now[0])
            return len(calls)

        self.assertEqual(cache.get_or_fetch("k", 900, fetch), 1)
        now[0] = 1801.0
        self.assertEqual(cache.get_or_fetch("k", 900, fetch), 2)
        self.assertEqual(len(calls), 2)


if __name__ == "__main__":
    unittest.main()
