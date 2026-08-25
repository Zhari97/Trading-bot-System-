"""Runner GitHub Actions del motore segnali."""

import logging
import requests

from signal_engine import (
    COPPIE_MONITORATE,
    INTERVAL_MIN,
    MODALITA_TEST,
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
    MODULI_STRATEGIA,
    analizza_coppia,
)

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("segnale_crypto")


def invia_telegram(testo: str) -> None:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        log.error("TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID non impostati, salto invio.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": testo, "parse_mode": "HTML"}
    r = requests.post(url, json=payload, timeout=10)
    if not r.ok:
        log.error("Errore invio Telegram: %s", r.text)


def controlla_coppia(pair: str):
    analisi = analizza_coppia(pair)
    ctx = analisi["ctx"]
    prezzo = analisi["prezzo"]

    log.info(
        "=== %s | prezzo=%.5f EMA9=%.5f EMA21=%.5f EMA50=%.5f RSI=%.1f SCORE=%.1f (%s) ===",
        pair, prezzo, ctx.ema9[ctx.i], ctx.ema21[ctx.i], ctx.ema50[ctx.i],
        ctx.rsi14[ctx.i], analisi["score"], analisi["bias"],
    )

    for risultato in analisi["risultati"]:
        modalita = "ATTIVO" if risultato["attivo"] else "in ombra"
        log.info(
            "[%s] [%s] (%s) -> %s | %s",
            pair, risultato["nome"], modalita, risultato["voto"], risultato["motivo"],
        )
        # Compatibilita: gli alert automatici continuano a dipendere dal campo
        # 'attivo', quindi non attiviamo improvvisamente i moduli shadow.
        if risultato["attivo"] and risultato["voto"] != "NEUTRO":
            emoji = "🟢" if risultato["voto"] == "LONG" else "🔴"
            invia_telegram(
                f"{emoji} <b>Segnale {risultato['voto']}</b>\n"
                f"Coppia: <b>{pair}</b> (Kraken)\n"
                f"Prezzo: {prezzo:.5f}\n"
                f"Score confluenza: <b>{analisi['score']:.1f}/100</b> ({analisi['bias']})\n"
                f"RSI: {ctx.rsi14[ctx.i]:.1f}\n"
                f"Modulo: {risultato['nome']}\n"
                f"Motivo: {risultato['motivo']}\n"
                f"Timeframe: {INTERVAL_MIN}m"
            )


def main():
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
