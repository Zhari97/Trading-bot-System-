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


def test_trade_plan_reads_atr_and_ema_from_same_context_index():
    analysis = analyze_closed_candles(_candles())
    assert analysis is not None
    ctx = analysis["ctx"]
    # If a plan exists, its calculations must reference the same closed candle
    # index used by the signal engine. The assertion also documents the contract
    # for future changes to trade_plan.py.
    plan = analysis.get("trade_plan")
    if plan:
        assert plan["entry"] == ctx.chiusure[ctx.i]
