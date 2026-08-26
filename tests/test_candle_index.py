import pytest

from candle_index import CURRENT_CANDLE, LAST_CLOSED_CANDLE, closed_candle, index_from_latest, require_candle


def test_semantic_offsets_map_to_latest_first():
    assert CURRENT_CANDLE == 0
    assert LAST_CLOSED_CANDLE == 1
    assert index_from_latest(0) == -1
    assert index_from_latest(1) == -2
    assert index_from_latest(2) == -3


def test_closed_candle_is_second_from_latest():
    candles = [{"id": i} for i in range(4)]
    assert closed_candle(candles)["id"] == 2
    assert require_candle(candles, 2)["id"] == 1


def test_insufficient_history_fails_closed():
    with pytest.raises(ValueError):
        closed_candle([{"id": 0}])


def test_negative_offset_is_rejected():
    with pytest.raises(ValueError):
        index_from_latest(-1)
