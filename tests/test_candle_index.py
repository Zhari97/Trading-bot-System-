import pytest

from candle_index import (
    CURRENT_CANDLE,
    LAST_CLOSED_CANDLE,
    closed_candle,
    index_from_latest,
    latest_closed_index,
    require_candle,
)


def test_semantic_offsets_map_to_latest_first():
    assert CURRENT_CANDLE == 0
    assert LAST_CLOSED_CANDLE == 1
    assert index_from_latest(0) == -1
    assert index_from_latest(1) == -2
    assert index_from_latest(2) == -3


def test_live_closed_candle_is_second_from_latest():
    candles = [{"id": i} for i in range(4)]
    assert latest_closed_index(candles, includes_forming=True) == 2
    assert closed_candle(candles, includes_forming=True)["id"] == 2
    assert require_candle(candles, 0, includes_forming=True)["id"] == 3
    assert require_candle(candles, 1, includes_forming=True)["id"] == 2
    assert require_candle(candles, 2, includes_forming=True)["id"] == 1


def test_historical_closed_only_data_has_no_candle_zero():
    candles = [{"id": i} for i in range(4)]
    assert latest_closed_index(candles, includes_forming=False) == 3
    assert closed_candle(candles, includes_forming=False)["id"] == 3
    assert require_candle(candles, 1, includes_forming=False)["id"] == 3
    assert require_candle(candles, 2, includes_forming=False)["id"] == 2
    with pytest.raises(ValueError):
        require_candle(candles, CURRENT_CANDLE, includes_forming=False)


def test_insufficient_history_fails_closed():
    with pytest.raises(ValueError):
        closed_candle([{"id": 0}])
    with pytest.raises(ValueError):
        latest_closed_index([], includes_forming=False)


def test_negative_offset_is_rejected():
    with pytest.raises(ValueError):
        index_from_latest(-1)
