"""Runner GitHub Actions del motore segnali.

V2.3:
- usa la classificazione complessiva del signal_engine;
- salva ogni analisi nel dataset live;
- mantiene Alert Gate e Telegram.
"""

import logging
import os

import requests

from api_budget import guard_requests

guard_requests()

from dashboard_state import save_analysis
from signal_engine import (
    COPPIE_MONITORATE,
    INTERVAL_MIN,
    MODALITA_TEST,
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
    analizza_coppia,
)
from signal_history import append_signal, build_signal_record
from trade_history import append_sent_trade

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("segnale_crypto")

DASHBOARD_URL = os.environ.get("DASHBOARD_URL", "").strip().rstrip("/")
DASHBOARD_INGEST_TOKEN = os.environ.get("DASHBOARD_INGEST_TOKEN", "")


def salva_stato_dashboard(analisi: dict, *args, **kwargs) -> dict:
    try:
        return save_analysis(analisi, *args, **kwargs)
    except Exception as e:
        log.error("Errore persistenza dashboard locale: %s", e)
        return None


def registra_segnale_live(pair: str, analisi: dict) -> dict | None:
    """Registra sempre l'analisi, anche se non genera un alert Telegram."""
    try:
        record = build_signal_record(pair, analisi)
        append_signal(record)
        log.info("[%s] SIGNAL HISTORY -> SAVED | level=%s direction=%s score=%.1f", pair, record["level"], record["direction"], record["score"])
        return record
    except Exception as e:
        log.warning("[%s] SIGNAL HISTORY -> FAILED | %s", pair, e)
        return None


def registra_trade_telegram(record: dict | None) -> None:
    """Persist only signals that were actually sent successfully to Telegram."""
    try:
        append_sent_trade(record or {})
        log.info("[%s] TRADE HISTORY -> SAVED", (record or {}).get("pair", "?"))
    except Exception as e:
        log.warning("[%s] TRADE HISTORY -> FAILED | %s", (record or {}).get("pair", "?"), e)


def invia_dashboard(record: dict) -> bool:
    if not DASHBOARD_URL or not DASHBOARD_INGEST_TOKEN or not isinstance(record, dict):
        return False
    try:
        response = requests.post(
            f"{DASHBOARD_URL}/api/ingest",
            headers={"X-Dashboard-Token": DASHBOARD_INGEST_TOKEN},
            json=record,
            timeout=10,
        )
        return bool(response.ok)
    except requests.RequestException:
        return False


def firma_alert(analisi: dict) -> tuple:
    classificazione = analisi["classificazione"]
    categorie = analisi["categorie"]
    return (
        classificazione.get("livello", "WATCH"),
        classificazione.get("direzione", "NEUTRO"),
        classificazione.get("trend_direzione", "NEUTRO"),
        classificazione.get("setup_direzione", "NEUTRO"),
        classificazione.get("momentum_direzione", "NEUTRO"),
        bool(classificazione.get("controtrend")),
        round(float(analisi["score"])),
        round(float(analisi["confluenza"])),
        round(float(categorie["trend"])),
        round(float(categorie["momentum"])),
        round(float(categorie["setup"])),
    )


def recupera_ultimo_alert_inviato(pair: str) -> dict | None:
    if not DASHBOARD_URL:
        return None
    try:
        response = requests.get(f"{DASHBOARD_URL}/api/history", timeout=10)
        if not response.ok:
            return None
        history = response.json()
        if not isinstance(history, list):
            return None
        for record in reversed(history):
            if isinstance(record, dict) and str(record.get("pair", "")).upper() == pair.upper() and record.get("telegram") == "SENT":
                return record
    except (requests.RequestException, ValueError, TypeError):
        pass
    return None


def alert_duplicato(analisi: dict, ultimo_alert: dict | None) -> bool:
    if not ultimo_alert:
        return False
    c = analisi["classificazione"]
    cats = analisi["categorie"]
    previous = ultimo_alert.get("categories", {})
    firma_precedente = (
        ultimo_alert.get("classification", "WATCH"),
        ultimo_alert.get("direction", "NEUTRO"),
        "LONG" if float(previous.get("trend", 50)) > 55 else "SHORT" if float(previous.get("trend", 50)) < 45 else "NEUTRO",
        "LONG" if float(previous.get("setup", 50)) > 55 else "SHORT" if float(previous.get("setup", 50)) < 45 else "NEUTRO",
        "LONG" if float(previous.get("momentum", 50)) > 55 else "SHORT" if float(previous.get("momentum", 50)) < 45 else "NEUTRO",
        bool(ultimo_alert.get("counter_trend")),
        round(float(ultimo_alert.get("score", 50))),
        round(float(ultimo_alert.get("confluence", 50))),
        round(float(previous.get("trend", 50))),
        round(float(previous.get("momentum", 50))),
        round(float(previous.get("setup", 50))),
    )
    return firma_alert(analisi) == firma_precedente


def invia_telegram(testo: str, pair: str = "") -> bool:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        r = requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": testo, "parse_mode": "HTML"}, timeout=10)
        return bool(r.ok)
    except requests.RequestException:
        return False


def costruisci_report(pair: str, analisi: dict) -> str:
    c = analisi["classificazione"]
    livello = c.get("livello", "WATCH")
    direzione = c.get("direzione", "NEUTRO")
    emoji = "🟢" if livello == "FORTE" else "🟡" if livello == "SETUP" else "🔴" if livello == "NO TRADE" else "⚪"
    return (
        f"{emoji} <b>{pair} — {livello}</b>\n"
        f"Direzione: <b>{direzione}</b>\n\n"
        f"Score: <b>{analisi['score']:.1f}/100</b>\n"
        f"Confluenza: <b>{analisi['confluenza']:.1f}%</b>\n"
        f"📈 Trend: <b>{analisi['categorie']['trend']:.1f}</b> ({c.get('trend_direzione', 'NEUTRO')})\n"
        f"⚡ Momentum: <b>{analisi['categorie']['momentum']:.1f}</b> ({c.get('momentum_direzione', 'NEUTRO')})\n"
        f"🎯 Setup: <b>{analisi['categorie']['setup']:.1f}</b> ({c.get('setup_direzione', 'NEUTRO')})\n\n"
        f"RSI: {analisi['ctx'].rsi14[analisi['ctx'].i]:.1f} | TF: {INTERVAL_MIN}m\n"
        f"💡 {c.get('motivo', 'Nessuna conferma sufficiente.') }"
    )


def controlla_coppia(pair: str) -> None:
    analisi = analizza_coppia(pair)
    record = registra_segnale_live(pair, analisi)

    c = analisi["classificazione"]
    log.info("=== %s | prezzo=%.5f SCORE=%.1f | %s ===", pair, analisi["prezzo"], analisi["score"], c.get("livello", "WATCH"))

    if not c.get("alert_automatico"):
        return

    ultimo = recupera_ultimo_alert_inviato(pair)
    if alert_duplicato(analisi, ultimo):
        log.info("[%s] ALERT GATE -> SUPPRESS DUPLICATE", pair)
        return

    testo = costruisci_report(pair, analisi)
    if invia_telegram(testo, pair):
        log.info("[%s] TELEGRAM -> SENT", pair)


if __name__ == "__main__":
    for coppia in COPPIE_MONITORATE:
        try:
            controlla_coppia(coppia)
        except Exception as e:
            log.exception("[%s] Errore controllo: %s", coppia, e)
