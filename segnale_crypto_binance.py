"""Runner GitHub Actions del motore segnali.

V2.2:
- usa la classificazione complessiva del signal_engine;
- stampa sempre nei log la qualità del setup;
- evita alert Telegram duplicati usando la cronologia persistente della dashboard;
- MODALITA_TEST continua a funzionare come prima.

Trade plan:
- per i segnali FORTE validi calcola entry, zona, TP, SL, R:R e qualita' ingresso;
- il piano e' informativo/manuale e non esegue ordini.
"""

import logging
import os

import requests

from api_budget import guard_requests

guard_requests()

from dashboard_state import save_analysis
from trade_plan import costruisci_trade_plan, format_trade_plan

from signal_engine import (
    COPPIE_MONITORATE,
    INTERVAL_MIN,
    MODALITA_TEST,
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
    analizza_coppia,
    classificazione_v2_2_valida,
)

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


def invia_dashboard(record: dict) -> bool:
    if not DASHBOARD_URL or not DASHBOARD_INGEST_TOKEN:
        log.info("Dashboard ingest non configurato: analisi e Telegram continuano normalmente.")
        return False
    if not isinstance(record, dict):
        log.warning("Dashboard ingest saltato: record analisi non disponibile.")
        return False
    try:
        response = requests.post(
            f"{DASHBOARD_URL}/api/ingest",
            headers={"X-Dashboard-Token": DASHBOARD_INGEST_TOKEN},
            json=record,
            timeout=10,
        )
        if response.ok:
            log.info("Dashboard ingest OK: %s", record.get("pair"))
            return True
        log.warning("Dashboard ingest failed: HTTP %s | pair=%s", response.status_code, record.get("pair"))
    except requests.RequestException as e:
        log.warning("Dashboard unavailable / dashboard ingest failed: %s", e)
    except Exception as e:
        log.warning("Dashboard ingest failed: %s", e)
    return False


def firma_alert(analisi: dict) -> tuple:
    classificazione = analisi["classificazione"]
    categorie = analisi["categorie"]
    return (
        classificazione.get("livello", "WATCH"), classificazione.get("direzione", "NEUTRO"),
        classificazione.get("trend_direzione", "NEUTRO"), classificazione.get("setup_direzione", "NEUTRO"),
        classificazione.get("momentum_direzione", "NEUTRO"), bool(classificazione.get("controtrend")),
        round(float(analisi["score"])), round(float(analisi["confluenza"])),
        round(float(categorie["trend"])), round(float(categorie["momentum"])), round(float(categorie["setup"])),
    )


def recupera_ultimo_alert_inviato(pair: str) -> dict | None:
    if not DASHBOARD_URL:
        log.warning("[%s] ALERT GATE -> dashboard non configurata: impossibile verificare duplicati", pair)
        return None
    try:
        response = requests.get(f"{DASHBOARD_URL}/api/history", timeout=10)
        if not response.ok:
            log.warning("[%s] ALERT GATE -> history HTTP %s: fail-open", pair, response.status_code)
            return None
        history = response.json()
        if not isinstance(history, list):
            return None
        for record in reversed(history):
            if isinstance(record, dict) and str(record.get("pair", "")).upper() == pair.upper() and record.get("telegram") == "SENT":
                return record
        return None
    except (requests.RequestException, ValueError, TypeError) as e:
        log.warning("[%s] ALERT GATE -> history unavailable (%s): fail-open", pair, e)
        return None


def alert_duplicato(analisi: dict, ultimo_alert: dict | None) -> bool:
    if not ultimo_alert:
        return False
    categorie = analisi["categorie"]
    firma_attuale = firma_alert(analisi)
    previous_categories = ultimo_alert.get("categories", {})
    firma_precedente = (
        ultimo_alert.get("classification", "WATCH"), ultimo_alert.get("direction", "NEUTRO"),
        "LONG" if float(previous_categories.get("trend", 50)) > 55 else "SHORT" if float(previous_categories.get("trend", 50)) < 45 else "NEUTRO",
        "LONG" if float(previous_categories.get("setup", 50)) > 55 else "SHORT" if float(previous_categories.get("setup", 50)) < 45 else "NEUTRO",
        "LONG" if float(previous_categories.get("momentum", 50)) > 55 else "SHORT" if float(previous_categories.get("momentum", 50)) < 45 else "NEUTRO",
        bool(ultimo_alert.get("counter_trend")), round(float(ultimo_alert.get("score", 50))),
        round(float(ultimo_alert.get("confluence", 50))), round(float(previous_categories.get("trend", 50))),
        round(float(previous_categories.get("momentum", 50))), round(float(previous_categories.get("setup", 50))),
    )
    return firma_attuale == firma_precedente


def invia_telegram(testo: str, pair: str = "") -> bool:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        log.error("[%s] TELEGRAM -> SKIP | credenziali non impostate", pair or "GLOBAL")
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        r = requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": testo, "parse_mode": "HTML"}, timeout=10)
        if not r.ok:
            log.error("[%s] TELEGRAM -> FAILED | HTTP %s | %s", pair or "GLOBAL", r.status_code, r.text)
            return False
        log.info("[%s] TELEGRAM -> SENT | HTTP %s", pair or "GLOBAL", r.status_code)
        return True
    except requests.RequestException as e:
        log.error("[%s] TELEGRAM -> FAILED | rete: %s", pair or "GLOBAL", e)
        return False


def costruisci_report(pair: str, analisi: dict) -> str:
    classificazione = analisi["classificazione"]
    categoria = classificazione.get("livello", "WATCH")
    motivo = classificazione.get("motivo", "Nessuna conferma sufficiente.")
    direzione = classificazione.get("direzione", "NEUTRO")
    score = analisi["score"]
    score_bias = "LONG" if score > 50 else "SHORT" if score < 50 else "NEUTRO"
    emoji = "🟢" if categoria == "FORTE" else "🟡" if categoria == "SETUP" else "🔴" if categoria == "NO TRADE" else "⚪"
    controtrend = "\n⚠️ <b>CONTRO-TREND</b> — il setup va contro il trend principale." if classificazione.get("controtrend") else ""

    report = (
        f"{emoji} <b>{pair} — {categoria}</b>\n"
        f"Direzione: <b>{direzione}</b>\n\n"
        f"Score direzionale: <b>{score:.1f}/100</b> (50 = neutro | bias {score_bias})\n"
        f"Confluenza: <b>{analisi['confluenza']:.1f}%</b>\n\n"
        f"📈 Trend: <b>{analisi['categorie']['trend']:.1f}</b> ({classificazione.get('trend_direzione', 'NEUTRO')})\n"
        f"⚡ Momentum: <b>{analisi['categorie']['momentum']:.1f}</b> ({classificazione.get('momentum_direzione', 'NEUTRO')})\n"
        f"🎯 Setup: <b>{analisi['categorie']['setup']:.1f}</b> ({classificazione.get('setup_direzione', 'NEUTRO')})\n\n"
        f"🟢 Peso LONG: {analisi['peso_long']:.1f}\n🔴 Peso SHORT: {analisi['peso_short']:.1f}"
        f"{controtrend}\n\n💡 {motivo}\nRSI: {analisi['ctx'].rsi14[analisi['ctx'].i]:.1f} | TF: {INTERVAL_MIN}m"
    )
    plan = costruisci_trade_plan(analisi)
    return report + format_trade_plan(plan)


def controlla_coppia(pair: str) -> None:
    analisi = analizza_coppia(pair)
    ctx = analisi["ctx"]
    prezzo = analisi["prezzo"]
    classificazione = analisi["classificazione"]
    log.info("=== %s | prezzo=%.5f EMA9=%.5f EMA21=%.5f EMA50=%.5f RSI=%.1f SCORE=%.1f (%s) | %s ===", pair, prezzo, ctx.ema9[ctx.i], ctx.ema21[ctx.i], ctx.ema50[ctx.i], ctx.rsi14[ctx.i], analisi["score"], analisi["bias"], classificazione.get("livello", "WATCH"))
    log.info("[%s] QUALITA -> %s | Motivo: %s", pair, classificazione.get("livello", "WATCH"), classificazione.get("motivo", "Nessuna conferma sufficiente."))

    for risultato in analisi["risultati"]:
        log.info("[%s] [%s] -> %s | %s", pair, risultato["nome"], risultato["voto"], risultato["motivo"])

    classificazione_valida, errore_guard_rail = classificazione_v2_2_valida(classificazione)
    if not classificazione_valida:
        log.error("[%s] GUARD-RAIL V2.2: %s. Alert Telegram bloccato.", pair, errore_guard_rail)
        record = salva_stato_dashboard(analisi, "BLOCKED", errore_guard_rail, "BLOCKED")
        invia_dashboard(record)
        return

    alert_automatico = bool(classificazione.get("alert_automatico"))
    direzione = classificazione.get("direzione")
    telegram_status = "NOT_SENT"
    if alert_automatico and direzione in ("LONG", "SHORT"):
        ultimo_alert = recupera_ultimo_alert_inviato(pair)
        if alert_duplicato(analisi, ultimo_alert):
            log.info("[%s] ALERT GATE -> SUPPRESS DUPLICATE | stesso setup gia notificato", pair)
        else:
            telegram_status = "SENT" if invia_telegram(costruisci_report(pair, analisi), pair=pair) else "FAILED"
    else:
        log.info("[%s] TELEGRAM -> SKIP | condizione alert non soddisfatta", pair)

    record = salva_stato_dashboard(analisi, telegram_status=telegram_status)
    invia_dashboard(record)


def main() -> None:
    if MODALITA_TEST:
        invia_telegram("🧪 <b>Messaggio di TEST</b>\nCollegamento GitHub Actions → Telegram funzionante.\n" f"Coppie: {', '.join(COPPIE_MONITORATE)} | Timeframe: {INTERVAL_MIN}m", pair="TEST")
        return
    for pair in COPPIE_MONITORATE:
        try:
            controlla_coppia(pair)
        except Exception as e:
            log.error("[%s] Errore durante il controllo: %s", pair, e)


if __name__ == "__main__":
    main()
