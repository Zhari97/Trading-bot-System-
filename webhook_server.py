"""
Server webhook: riceve i segnali da TradingView (se in futuro li userai) e li
inoltra su Telegram. Ora ascolta ANCHE i comandi che scrivi al bot Telegram
(es. /status) e risponde in tempo reale.
"""

import os
import logging
from flask import Flask, request, jsonify
import requests

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("webhook_server")

app = Flask(__name__)

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "8888365707:AAG8cBP1zcWNKDkvwutvkw97BH0bYY-4DVQ")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "661547674")

WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")

PAIR = os.environ.get("PAIR", "XBTUSD")
INTERVAL_MIN = int(os.environ.get("INTERVAL_MIN", "15"))
EMA_FAST_LEN = 9
EMA_SLOW_LEN = 21
RSI_LEN = 14

KRAKEN_OHLC_URL = "https://api.kraken.com/0/public/OHLC"


def scarica_candele(pair: str, interval_min: int):
    params = {"pair": pair, "interval": interval_min}
    r = requests.get(KRAKEN_OHLC_URL, params=params, timeout=15)
    r.raise_for_status()
    dati = r.json()
    if dati.get("error"):
        raise RuntimeError(f"Errore API Kraken: {dati['error']}")
    risultato = dati["result"]
    chiave_coppia = next(k for k in risultato.keys() if k != "last")
    candele = risultato[chiave_coppia]
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


def calcola_stato_attuale():
    chiusure = scarica_candele(PAIR, INTERVAL_MIN)
    ema_fast = calcola_ema(chiusure, EMA_FAST_LEN)
    ema_slow = calcola_ema(chiusure, EMA_SLOW_LEN)
    rsi = calcola_rsi(chiusure, RSI_LEN)
    return {
        "prezzo": chiusure[-1],
        "ema_fast": ema_fast[-1],
        "ema_slow": ema_slow[-1],
        "rsi": rsi[-1],
    }


def invia_telegram(testo: str, chat_id: str = None) -> None:
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id or TELEGRAM_CHAT_ID, "text": testo, "parse_mode": "HTML"}
    try:
        r = requests.post(url, json=payload, timeout=10)
        r.raise_for_status()
    except requests.RequestException as e:
        log.error("Errore invio Telegram: %s", e)


@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json(silent=True) or {}
    log.info("Segnale ricevuto: %s", data)

    if WEBHOOK_SECRET and data.get("secret") != WEBHOOK_SECRET:
        return jsonify({"status": "unauthorized"}), 401

    symbol = data.get("symbol", "N/D")
    side = data.get("side", "N/D")
    price = data.get("price", "N/D")
    time_ = data.get("time", "N/D")

    emoji = "🟢" if side.upper() == "LONG" else "🔴"
    messaggio = (
        f"{emoji} <b>Segnale {side}</b>\n"
        f"Simbolo: <b>{symbol}</b>\n"
        f"Prezzo: {price}\n"
        f"Orario: {time_}"
    )
    invia_telegram(messaggio)
    return jsonify({"status": "ok"}), 200


@app.route("/telegram-webhook", methods=["POST"])
def telegram_webhook():
    update = request.get_json(silent=True) or {}
    log.info("Update Telegram ricevuto: %s", update)

    messaggio = update.get("message", {})
    testo = (messaggio.get("text") or "").strip()
    chat_id = messaggio.get("chat", {}).get("id")

    if not testo or not chat_id:
        return jsonify({"status": "ignored"}), 200

    comando = testo.lower()

    if comando in ("/status", "/stato"):
        try:
            stato = calcola_stato_attuale()
            trend = "sopra" if stato["ema_fast"] > stato["ema_slow"] else "sotto"
            risposta = (
                f"📊 <b>Stato attuale</b>\n"
                f"Coppia: <b>{PAIR}</b> (Kraken)\n"
                f"Prezzo: {stato['prezzo']:.2f}\n"
                f"EMA{EMA_FAST_LEN}: {stato['ema_fast']:.2f}\n"
                f"EMA{EMA_SLOW_LEN}: {stato['ema_slow']:.2f} (veloce {trend} lenta)\n"
                f"RSI: {stato['rsi']:.1f}\n"
                f"Timeframe: {INTERVAL_MIN}m"
            )
        except Exception as e:
            log.error("Errore calcolo stato: %s", e)
            risposta = "⚠️ Non sono riuscito a leggere i dati in questo momento, riprova tra poco."
        invia_telegram(risposta, chat_id=chat_id)

    elif comando in ("/start", "/help", "/aiuto"):
        risposta = (
            "👋 Ciao! Comandi disponibili:\n"
            "/status — prezzo, EMA e RSI attuali in tempo reale\n\n"
            "I segnali automatici (LONG/SHORT) arrivano da soli ogni volta "
            "che le condizioni si verificano, non serve chiederli."
        )
        invia_telegram(risposta, chat_id=chat_id)

    else:
        invia_telegram("Comando non riconosciuto. Scrivi /status per il prezzo attuale.", chat_id=chat_id)

    return jsonify({"status": "ok"}), 200


@app.route("/", methods=["GET"])
def health():
    return "Webhook server attivo", 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
