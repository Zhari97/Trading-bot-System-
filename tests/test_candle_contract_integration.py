from signal_engine import ContestoMercato
from signal_engine_replay_adapter import analyze_closed_candles


def _candles(n=60):
    return [
        {
            "open": 100.0 + i * 0.1,
            "high": 101.0 + i * 0.1,
            "low": 99.0 + i * 0.1,
            "close": 100.5 + i * 0.1,
            "volume": 1000.0,
        }
        for i in range(n)
    ]


def test_live_context_uses_semantic_candle_one():
    candles = _candles()
    ctx = ContestoMercato(candles)
    assert ctx.i == len(candles) - 2
    assert ctx.chiusure[ctx.i] == candles[-2]["close"]


def test_historical_adapter_uses_final_closed_row_as_candle_one():
    candles = _candles()
    analysis = analyze_closed_candles(candles)
    assert analysis is not None
    assert analysis["ctx"].i == len(candles) - 1
    assert analysis["prezzo"] == candles[-1]["close"]
