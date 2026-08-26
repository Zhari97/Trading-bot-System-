"""Entry point GitHub Actions with timing and deduplication guards."""
from __future__ import annotations

import datetime as dt

from signal_timing_guard import candle_is_closed, should_emit_signal
import signal_engine
from signal_quality_guard import analizza_coppia_con_guard

signal_engine.analizza_coppia = analizza_coppia_con_guard

import segnale_crypto_binance
from trade_plan import costruisci_trade_plan, format_trade_plan

_base_report = segnale_crypto_binance.costruisci_report
segnale_crypto_binance.costruisci_report = lambda pair, analysis: _base_report(pair, analysis) + format_trade_plan(costruisci_trade_plan(analysis))


def _expected_closed_candle_open(now: dt.datetime, interval_minutes: int) -> dt.datetime:
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    interval_seconds = interval_minutes * 60
    bucket = int(now.timestamp()) // interval_seconds
    return dt.datetime.fromtimestamp((bucket - 1) * interval_seconds, tz=dt.timezone.utc)


def controlla_coppia_con_timing_guard(pair: str) -> None:
    """Compute once, then guard the same analysis before any live side effect."""
    analysis = signal_engine.analizza_coppia(pair)
    now = dt.datetime.now(dt.timezone.utc)
    candle_open = getattr(analysis.get("ctx"), "candle_open_time", None) or _expected_closed_candle_open(now, signal_engine.INTERVAL_MIN)
    if not candle_is_closed(candle_open, signal_engine.INTERVAL_MIN, now).accepted:
        return
    c = analysis["classificazione"]
    last = segnale_crypto_binance.recupera_ultimo_alert_inviato(pair)
    last_key = None
    if last:
        last_key = (str(last.get("pair", pair)).upper(), str(last.get("candle_open_time", candle_open.isoformat())), str(last.get("direction", "NEUTRO")).upper(), float(last.get("score", 50)))
    if not should_emit_signal(pair, candle_open, c.get("direzione", "NEUTRO"), float(analysis["score"]), float(analysis["confluenza"]), last_key).accepted:
        return
    segnale_crypto_binance.registra_segnale_live(pair, analysis)
    if not c.get("alert_automatico"):
        return
    if segnale_crypto_binance.invia_telegram(segnale_crypto_binance.costruisci_report(pair, analysis), pair):
        segnale_crypto_binance.log.info("[%s] TELEGRAM -> SENT", pair)


segnale_crypto_binance.controlla_coppia = controlla_coppia_con_timing_guard

if __name__ == "__main__":
    for pair in segnale_crypto_binance.COPPIE_MONITORATE:
        try:
            controlla_coppia_con_timing_guard(pair)
        except Exception as exc:
            segnale_crypto_binance.log.exception("[%s] Errore controllo: %s", pair, exc)
