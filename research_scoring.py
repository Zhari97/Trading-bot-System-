"""Research-only continuous scoring for Trend, Momentum and Setup.

This module intentionally does not alter the production signal engine. Historical
replay can use richer continuous evidence while LIVE keeps its existing logic.
"""
from __future__ import annotations


def _directional_strength(long_value: float, short_value: float, neutral_value: float = 0.0) -> float:
    """Return a signed strength in [-1, 1], preserving neutral evidence."""
    total = long_value + short_value + neutral_value
    if total <= 0:
        return 0.0
    return (long_value - short_value) / total


def _score_from_signed_strength(strength: float) -> float:
    return max(0.0, min(100.0, 50.0 + strength * 50.0))


def _module_weighted_vote(result: dict, weight: float) -> tuple[float, float, float]:
    vote = result.get("voto")
    if vote == "LONG":
        return weight, 0.0, 0.0
    if vote == "SHORT":
        return 0.0, weight, 0.0
    return 0.0, 0.0, weight


def continuous_categories(ctx, results: list[dict]) -> dict:
    """Build continuous category scores without changing production scoring.

    Trend combines price-vs-EMA50 distance (continuous) with Ichimoku direction.
    Momentum combines RSI position and MACD histogram direction.
    Setup combines candle-pattern evidence, Bollinger position and Fibonacci
    proximity. Values are intentionally bounded to 0..100.
    """
    i = ctx.i
    price = ctx.chiusure[i]

    # TREND: EMA50 distance is continuous and Ichimoku contributes directional evidence.
    ema50 = ctx.ema50[i]
    ema_distance = 0.0 if ema50 == 0 else (price - ema50) / ema50
    ema_component = max(-1.0, min(1.0, ema_distance / 0.02))
    ichimoku = results[3].get("voto")
    ichi_component = 1.0 if ichimoku == "LONG" else -1.0 if ichimoku == "SHORT" else 0.0
    trend_strength = 0.70 * ema_component + 0.30 * ichi_component

    # MOMENTUM: RSI is continuous; MACD histogram adds directional confirmation.
    rsi = ctx.rsi14[i]
    rsi_component = max(-1.0, min(1.0, (rsi - 50.0) / 25.0))
    hist = ctx.macd_istogramma[i]
    macd_scale = max(abs(x) for x in ctx.macd_istogramma[max(0, i - 50):i + 1]) or 1.0
    macd_component = max(-1.0, min(1.0, hist / macd_scale))
    momentum_strength = 0.60 * rsi_component + 0.40 * macd_component

    # SETUP: aggregate independent setup modules, keeping neutral evidence neutral.
    setup_long = setup_short = setup_neutral = 0.0
    setup_weights = {
        "Bollinger Bands": 0.40,
        "Fibonacci retracement": 0.25,
        "Price Action": 0.35,
    }
    for result in results:
        weight = setup_weights.get(result.get("nome"))
        if weight is None:
            continue
        long, short, neutral = _module_weighted_vote(result, weight)
        setup_long += long
        setup_short += short
        setup_neutral += neutral
    setup_strength = _directional_strength(setup_long, setup_short, setup_neutral)

    return {
        "trend": _score_from_signed_strength(trend_strength),
        "momentum": _score_from_signed_strength(momentum_strength),
        "setup": _score_from_signed_strength(setup_strength),
        "trend_strength": trend_strength,
        "momentum_strength": momentum_strength,
        "setup_strength": setup_strength,
        "scoring_version": "research_continuous_v1",
    }
