"""Runner GitHub Actions del motore segnali.

V2.2:
- usa la classificazione complessiva del signal_engine;
- stampa sempre nei log la qualità del setup;
- NON abilita automaticamente nuovi alert: resta conservativo;
- MODALITA_TEST continua a funzionare come prima.

Dashboard:
- inoltra esclusivamente il risultato già prodotto dal motore;
- usa DASHBOARD_URL e DASHBOARD_INGEST_TOKEN;
- l'invio è non-blocking e non può fermare il bot.
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
        log.warning(
            "Dashboard ingest failed: HTTP %s | pair=%s",
            response.status_code,
            record.get("pair"),
        )
    except requests.RequestException as e:
        log.warning("Dashboard unavailable / dashboard ingest failed: %s", e)
    except Exception as e:
        log.warning("Dashboard ingest failed: %s", e)
    return False


def invia_telegram(testo: str, pair: str = "") -> bool:
    """Invia Telegram e registra esplicitamente la decisione/risposta HTTP."""
    log.info(
        "[%s] TELEGRAM DECISION | token=%s chat_id=%s",
        pair or "GLOBAL",
        "SET" if TELEGRAM_BOT_TOKEN else "MISSING",
        "SET" if TELEGRAM_CHAT_ID else "MISSING",
    )
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        log.error("[%s] TELEGRAM -> SKIP | credenziali non impostate", pair or "GLOBAL")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": testo, "parse_mode": "HTML"}
    try:
        r = requests.post(url, json=payload, timeout=10)
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

    if categoria == "FORTE":
        emoji = "🟢"
    elif categoria == "SETUP":
        emoji = "🟡"
    elif categoria == "NO TRADE":
        emoji = "🔴"
    else:
        emoji = "⚪"

    controtrend = ""
    if classificazione.get("controtrend"):
        controtrend = "\n⚠️ <b>CONTRO-TREND</b> — il setup va contro il trend principale."

    return (
        f"{emoji} <b>{pair} — {categoria}</b>\n"
        f"Direzione: <b>{direzione}</b>\n\n"
        f"Score direzionale: <b>{score:.1f}/100</b> "
        f"(50 = neutro | bias {score_bias})\n"
        f"Confluenza: <b>{analisi['confluenza']:.1f}%</b>\n\n"
        f"📈 Trend: <b>{analisi['categorie']['trend']:.1f}</b> "
        f"({classificazione.get('trend_direzione', 'NEUTRO')})\n"
        f"⚡ Momentum: <b>{analisi['categorie']['momentum']:.1f}</b> "
        f"({classificazione.get('momentum_direzione', 'NEUTRO')})\n"
        f"🎯 Setup: <b>{analisi['categorie']['setup']:.1f}</b> "
        f"({classificazione.get('setup_direzione', 'NEUTRO')})\n\n"
        f"🟢 Peso LONG: {analisi['peso_long']:.1f}\n"
        f"🔴 Peso SHORT: {analisi['peso_short']:.1f}"
        f"{controtrend}\n\n"
        f"💡 {motivo}\n"
        f"RSI: {analisi['ctx'].rsi14[analisi['ctx'].i]:.1f} | TF: {INTERVAL_MIN}m"
    )


def controlla_coppia(pair: str) -> None:
    analisi = analizza_coppia(pair)
    ctx = analisi["ctx"]
    prezzo = analisi["prezzo"]
    classificazione = analisi["classificazione"]

    log.info(
        "=== %s | prezzo=%.5f EMA9=%.5f EMA21=%.5f EMA50=%.5f RSI=%.1f SCORE=%.1f (%s) | %s ===",
        pair, prezzo, ctx.ema9[ctx.i], ctx.ema21[ctx.i], ctx.ema50[ctx.i], ctx.rsi14[ctx.i],
        analisi["score"], analisi["bias"], classificazione.get("livello", "WATCH"),
    )

    log.info(
        "[%s] Categorie -> TREND %.1f | MOMENTUM %.1f | SETUP %.1f | %s | Dominante %s %.1f%%",
        pair, analisi["categorie"]["trend"], analisi["categorie"]["momentum"],
        analisi["categorie"]["setup"], "CONFLITTO" if analisi["conflitto"] else "CONFLUENZA",
        analisi["direzione_dominante"], analisi["confluenza"],
    )

    log.info("[%s] QUALITA -> %s | Motivo: %s", pair, classificazione.get("livello", "WATCH"), classificazione.get("motivo", "Nessuna conferma sufficiente."))

    if classificazione.get("controtrend"):
        log.info("[%s] ⚠️ CONTRO-TREND", pair)

    for risultato in analisi["risultati"]:
        modalita = "ATTIVO" if risultato["attivo"] else "in ombra"
        log.info("[%s] [%s] (%s) -> %s | %s", pair, risultato["nome"], modalita, risultato["voto"], risultato["motivo"])

    log.info("\n[%s] REPORT V2.2\n%s", pair, costruisci_report(pair, analisi))

    classificazione_valida, errore_guard_rail = classificazione_v2_2_valida(classificazione)
    if not classificazione_valida:
        log.error("[%s] GUARD-RAIL V2.2: %s. Alert Telegram bloccato.", pair, errore_guard_rail)
        record = salva_stato_dashboard(analisi, "BLOCKED", errore_guard_rail, "BLOCKED")
        invia_dashboard(record)
        return

    alert_automatico = bool(classificazione.get("alert_automatico"))
    direzione = classificazione.get("direzione")
    log.info("[%s] TELEGRAM DECISION | livello=%s alert_automatico=%s direzione=%s", pair, classificazione.get("livello"), alert_automatico, direzione)

    telegram_status = "NOT_SENT"
    if alert_automatico and direzione in ("LONG", "SHORT"):
        telegram_status = "SENT" if invia_telegram(costruisci_report(pair, analisi), pair=pair) else "FAILED"
    else:
        log.info("[%s] TELEGRAM -> SKIP | condizione alert non soddisfatta", pair)

    record = salva_stato_dashboard(analisi, telegram_status=telegram_status)
    invia_dashboard(record)


def main() -> None:
    if MODALITA_TEST:
        invia_telegram(
            "🧪 <b>Messaggio di TEST</b>\nCollegamento GitHub Actions → Telegram funzionante.\n"
            f"Coppie: {', '.join(COPPIE_MONITORATE)} | Timeframe: {INTERVAL_MIN}m",
            pair="TEST",
        )
        return

    for pair in COPPIE_MONITORATE:
        try:
            controlla_coppia(pair)
        except Exception as e:
            log.error("[%s] Errore durante il controllo: %s", pair, e)


if __name__ == "__main__":
    main()
