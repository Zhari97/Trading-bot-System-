"""Entry point GitHub Actions with quality, timing and deduplication guards."""

from signal_timing_guard import candle_is_closed, should_emit_signal

import signal_engine
from signal_quality_guard import analizza_coppia_con_guard

signal_engine.analizza_coppia = analizza_coppia_con_guard

import segnale_crypto_binance
from trade_plan import costruisci_trade_plan, format_trade_plan

_report_base = segnale_crypto_binance.costruisci_report


def costruisci_report_con_trade_plan(pair: str, analisi: dict) -> str:
    report = _report_base(pair, analisi)
    return report + format_trade_plan(costruisci_trade_plan(analisi))


segnale_crypto_binance.costruisci_report = costruisci_report_con_trade_plan


_original_controlla = segnale_crypto_binance.controlla_coppia


def controlla_coppia_con_timing_guard(pair: str) -> None:
    """Apply timing/deduplication only to the live alert path.

    The underlying engine remains unchanged. A missing/invalid candle timestamp
    fails closed rather than allowing an alert whose candle state is unknown.
    """
    analisi = signal_engine.analizza_coppia(pair)
    ctx = analisi.get("ctx")
    candle_open_time = getattr(ctx, "candle_open_time", None)
    if candle_open_time is None:
        candle_open_time = getattr(ctx, "open_time", None)
    if candle_open_time is None:
        raise RuntimeError("Missing candle open timestamp; refusing live alert")

    import datetime as _dt

    now = _dt.datetime.now(_dt.timezone.utc)
    decision = candle_is_closed(candle_open_time, signal_engine.INTERVAL_MIN, now)
    if not decision.accepted:
        return

    classification = analisi["classificazione"]
    categories = analisi["categorie"]
    last = segnale_crypto_binance.recupera_ultimo_alert_inviato(pair)
    last_key = None
    if last:
        previous = last.get("categories", {})
        last_key = (
            str(last.get("pair", pair)).upper(),
            str(last.get("candle_open_time", candle_open_time.isoformat())),
            str(last.get("direction", "NEUTRO")).upper(),
            float(last.get("score", 50)),
        )
    timing = should_emit_signal(
        pair,
        candle_open_time,
        classification.get("direzione", "NEUTRO"),
        float(analisi["score"]),
        float(analisi["confluenza"]),
        last_key,
    )
    if not timing.accepted:
        return

    # Reuse the established live path after the new guard has approved it.
    _original_controlla(pair)


segnale_crypto_binance.controlla_coppia = controlla_coppia_con_timing_guard


if __name__ == "__main__":
    segnale_crypto_binance.main() if hasattr(segnale_crypto_binance, "main") else [
        controlla_coppia_con_timing_guard(pair) for pair in segnale_crypto_binance.COPPIE_MONITORATE
    ]
