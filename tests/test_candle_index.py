import unittest

from candle_index import (
    CURRENT_CANDLE,
    LAST_CLOSED_CANDLE,
    closed_candle,
    index_from_latest,
    latest_closed_index,
    require_candle,
)


class CandleIndexTests(unittest.TestCase):
    def test_semantic_offsets_map_to_latest_first(self):
        self.assertEqual(CURRENT_CANDLE, 0)
        self.assertEqual(LAST_CLOSED_CANDLE, 1)
        self.assertEqual(index_from_latest(0), -1)
        self.assertEqual(index_from_latest(1), -2)
        self.assertEqual(index_from_latest(2), -3)

    def test_live_closed_candle_is_second_from_latest(self):
        candles = [{"id": i} for i in range(4)]
        self.assertEqual(latest_closed_index(candles, includes_forming=True), 2)
        self.assertEqual(closed_candle(candles, includes_forming=True)["id"], 2)
        self.assertEqual(require_candle(candles, 0, includes_forming=True)["id"], 3)
        self.assertEqual(require_candle(candles, 1, includes_forming=True)["id"], 2)
        self.assertEqual(require_candle(candles, 2, includes_forming=True)["id"], 1)

    def test_historical_closed_only_data_has_no_candle_zero(self):
        candles = [{"id": i} for i in range(4)]
        self.assertEqual(latest_closed_index(candles, includes_forming=False), 3)
        self.assertEqual(closed_candle(candles, includes_forming=False)["id"], 3)
        self.assertEqual(require_candle(candles, 1, includes_forming=False)["id"], 3)
        self.assertEqual(require_candle(candles, 2, includes_forming=False)["id"], 2)
        with self.assertRaises(ValueError):
            require_candle(candles, CURRENT_CANDLE, includes_forming=False)

    def test_insufficient_history_fails_closed(self):
        with self.assertRaises(ValueError):
            closed_candle([{"id": 0}])
        with self.assertRaises(ValueError):
            latest_closed_index([], includes_forming=False)

    def test_negative_offset_is_rejected(self):
        with self.assertRaises(ValueError):
            index_from_latest(-1)


if __name__ == "__main__":
    unittest.main()
