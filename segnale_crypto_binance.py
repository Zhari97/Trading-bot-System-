"""Runner GitHub Actions del motore segnali.

V2.2:
- usa la classificazione complessiva del signal_engine;
- stampa sempre nei log la qualità del setup;
- NON abilita automaticamente nuovi alert: resta conservativo;
- MODALITA_TEST continua a funzionare come prima.
"""

import logging
import requests

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


def invia_telegram(testo: str) -> None:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        log.error("TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID non impostati, salto invio.")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": testo,
        "parse_mode": "HTML",
    }

    try:
        r = requests.post(url, json=payload, timeout=10)
        if not r.ok:
            log.error("Errore invio Telegram: %s", r.text)
    except requests.RequestException as e:
        log.error("Errore di rete Telegram: %s", e)


def costruisci_report(pair: str, analisi: dict) -> str:
    """Costruisce lo stesso formato leggibile che useremo per Telegram."""
    classificazione = analisi["classificazione"]
    categoria = classificazione.get("livello", "WATCH")
    motivo = classificazione.get("motivo", "Nessuna conferma sufficiente.")
    direzione = classificazione.get("direzione", "NEUTRO")

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
        f"Score: <b>{analisi['score']:.1f}/100</b>\n"
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

    # Header sintetico.
    log.info(
        "=== %s | prezzo=%.5f EMA9=%.5f EMA21=%.5f EMA50=%.5f "
        "RSI=%.1f SCORE=%.1f (%s) | %s ===",
        pair,
        prezzo,
        ctx.ema9[ctx.i],
        ctx.ema21[ctx.i],
        ctx.ema50[ctx.i],
        ctx.rsi14[ctx.i],
        analisi["score"],
        analisi["bias"],
        classificazione.get("livello", "WATCH"),
    )

    # Lettura per categorie.
    log.info(
        "[%s] Categorie -> TREND %.1f | MOMENTUM %.1f | SETUP %.1f | %s | "
        "Dominante %s %.1f%%",
        pair,
        analisi["categorie"]["trend"],
        analisi["categorie"]["momentum"],
        analisi["categorie"]["setup"],
        "CONFLITTO" if analisi["conflitto"] else "CONFLUENZA",
        analisi["direzione_dominante"],
        analisi["confluenza"],
    )

    log.info(
        "[%s] QUALITA -> %s | Motivo: %s",
        pair,
        classificazione.get("livello", "WATCH"),
        classificazione.get("motivo", "Nessuna conferma sufficiente."),
    )

    if classificazione.get("controtrend"):
        log.info("[%s] ⚠️ CONTRO-TREND", pair)

    # Tutti i moduli restano visibili nei log.
    for risultato in analisi["risultati"]:
        modalita = "ATTIVO" if risultato["attivo"] else "in ombra"
        log.info(
            "[%s] [%s] (%s) -> %s | %s",
            pair,
            risultato["nome"],
            modalita,
            risultato["voto"],
            risultato["motivo"],
        )

    # Report completo sempre nei log: ci permette di validare il sistema
    # prima di aumentare il numero degli alert automatici.
    log.info("\n[%s] REPORT V2.2\n%s", pair, costruisci_report(pair, analisi))

    classificazione_valida, errore_guard_rail = classificazione_v2_2_valida(classificazione)
    if not classificazione_valida:
        log.error("[%s] GUARD-RAIL V2.2: %s. Alert Telegram bloccato.", pair, errore_guard_rail)
        return

    # Gli alert reali restano governati dalla classificazione del motore.
    # Non attiviamo nuovi moduli singolarmente.
    if (
        classificazione.get("alert_automatico")
        and classificazione.get("direzione") in ("LONG", "SHORT")
    ):
        invia_telegram(costruisci_report(pair, analisi))


def main() -> None:
    if MODALITA_TEST:
        invia_telegram(
            "🧪 <b>Messaggio di TEST</b>\n"
            "Collegamento GitHub Actions → Telegram funzionante.\n"
            f"Coppie: {', '.join(COPPIE_MONITORATE)} | Timeframe: {INTERVAL_MIN}m"
        )
        return

    for pair in COPPIE_MONITORATE:
        try:
            controlla_coppia(pair)
        except Exception as e:
            log.error("[%s] Errore durante il controllo: %s", pair, e)


if __name__ == "__main__":
    main()
