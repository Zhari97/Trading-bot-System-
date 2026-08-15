"""
Controllo segnali crypto (EMA cross + RSI) usando dati gratuiti e pubblici
da Kraken, senza bisogno di un abbonamento TradingView e senza bisogno
di un account Kraken (per la sola lettura dei prezzi).

Pensato per essere eseguito periodicamente da GitHub Actions (es. ogni 15 minuti).
Ogni volta che gira: scarica le ultime candele, calcola EMA9/EMA21 e RSI14,
e se le condizioni di LONG o SHORT si sono appena verificate sull'ultima
candela chiusa, manda un messaggio su Telegram.

PRONTO PER IL FUTURO:
Kraken è lo stesso exchange su cui hai già un account. Il giorno in cui
vorrai passare all'esecuzione automatica degli ordini (non solo segnali),
qui sotto si aggiungerebbero solo le chiamate "private" dell'API Kraken
(che richiedono API key con permessi di trading) — la parte di lettura
prezzi che stai usando ora resta identica.

CONFIGURAZIONE:
Le credenziali Telegram vengono lette dalle variabili d'ambiente
TELEGRAM_BOT_TOKEN e TELEGRAM_CHAT_ID (le imposteremo come "secrets"
su GitHub, non scritte nel codice).
"""

import os
import logging
import requests

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("segnale_crypto")

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

# ==== PARAMETRI STRATEGIA (stessi valori dello script Pine) ====
# Formato coppie Kraken: es. "XBTUSD" per Bitcoin/Dollaro, "ETHUSD" per Ethereum/Dollaro.
# "XBT" è il simbolo che Kraken usa per il Bitcoin al posto di "BTC".
PAIR = os.environ.get("PAIR", "XBTUSD")
INTERVAL_MIN = int(os.environ.get("INTERVAL_MIN", "15"))  # minuti: 1,5,15,30,60,240,1440...
EMA_FAST_LEN = 9
EMA_SLOW_LEN = 21
RSI_LEN = 14
RSI_LONG_MAX = 70
RSI_SHORT_MIN = 30

KRAKEN_OHLC_URL = "https://api.kraken.com/0/public/OHLC"


def scarica_candele(pair: str, interval_min: int):
    params = {"pair": pair, "interval": interval_min}
    r = requests.get(KRAKEN_OHLC_URL, params=params, timeout=15)
    r.raise_for_status()
    dati = r.json()

    if dati.get("error"):
        raise RuntimeError(f"Errore API Kraken: {dati['error']}")

    risultato = dati["result"]
    # La chiave del dizionario è il nome interno della coppia scelto da Kraken
    # (es. "XXBTZUSD" per XBTUSD), quindi prendiamo l'unica chiave diversa da "last".
    chiave_coppia = next(k for k in risultato.keys() if k != "last")
    candele = risultato[chiave_coppia]
    # ogni candela: [time, open, high, low, close, vwap, volume, count]
    chiusure = [float(c[4]) for c in candele]
    return chiusure


def calcola_ema(valori, periodo):
    k = 2 / (periodo + 1)
    ema = [valori[0]]
    for prezzo in valori[1:]:
        ema.append(prezzo * k + ema[-1] * (1 - k))
    return ema


def calcola_rsi(valori, periodo):
    guadagni, perdite = [0], [0]
    for i in range(1, len(valori)):
        diff = valori[i] - valori[i - 1]
        guadagni.append(max(diff, 0))
        perdite.append(max(-diff, 0))

    rsi = [50.0] * len(valori)
    if len(valori) <= periodo:
        return rsi

    media_guadagni = sum(guadagni[1:periodo + 1]) / periodo
    media_perdite = sum(perdite[1:periodo + 1]) / periodo

    for i in range(periodo + 1, len(valori)):
        media_guadagni = (media_guadagni * (periodo - 1) + guadagni[i]) / periodo
        media_perdite = (media_perdite * (periodo - 1) + perdite[i]) / periodo
        if media_perdite == 0:
            rsi[i] = 100.0
        else:
            rs = media_guadagni / media_perdite
            rsi[i] = 100 - (100 / (1 + rs))
    return rsi


def invia_telegram(testo: str) -> None:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        log.error("TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID non impostati, salto invio.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": testo, "parse_mode": "HTML"}
    r = requests.post(url, json=payload, timeout=10)
    if not r.ok:
        log.error("Errore invio Telegram: %s", r.text)


def main():
    chiusure = scarica_candele(PAIR, INTERVAL_MIN)
    if len(chiusure) < max(EMA_SLOW_LEN, RSI_LEN) + 2:
        log.warning("Non abbastanza dati per calcolare i segnali.")
        return

    ema_fast = calcola_ema(chiusure, EMA_FAST_LEN)
    ema_slow = calcola_ema(chiusure, EMA_SLOW_LEN)
    rsi = calcola_rsi(chiusure, RSI_LEN)

    # Guardiamo l'ultima candela CHIUSA (penultimo elemento, l'ultimo
    # potrebbe essere ancora in formazione) per evitare falsi segnali
    i = -2
    prezzo = chiusure[i]

    incrocio_long = ema_fast[i - 1] <= ema_slow[i - 1] and ema_fast[i] > ema_slow[i]
    incrocio_short = ema_fast[i - 1] >= ema_slow[i - 1] and ema_fast[i] < ema_slow[i]

    long_ok = incrocio_long and rsi[i] < RSI_LONG_MAX
    short_ok = incrocio_short and rsi[i] > RSI_SHORT_MIN

    log.info(
        "Pair=%s prezzo=%.2f EMA_fast=%.2f EMA_slow=%.2f RSI=%.1f long=%s short=%s",
        PAIR, prezzo, ema_fast[i], ema_slow[i], rsi[i], long_ok, short_ok,
    )

    if long_ok:
        invia_telegram(
            f"🟢 <b>Segnale LONG</b>\nCoppia: <b>{PAIR}</b> (Kraken)\n"
            f"Prezzo: {prezzo:.2f}\nRSI: {rsi[i]:.1f}\nTimeframe: {INTERVAL_MIN}m"
        )
    elif short_ok:
        invia_telegram(
            f"🔴 <b>Segnale SHORT</b>\nCoppia: <b>{PAIR}</b> (Kraken)\n"
            f"Prezzo: {prezzo:.2f}\nRSI: {rsi[i]:.1f}\nTimeframe: {INTERVAL_MIN}m"
        )
    else:
        log.info("Nessun segnale su questa candela.")


if __name__ == "__main__":
    main()
