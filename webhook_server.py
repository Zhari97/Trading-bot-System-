"""
Server webhook: riceve i segnali da TradingView e li inoltra su Telegram.

TEST IN LOCALE:
1. pip install flask requests
2. python webhook_server.py
3. Il server parte su http://localhost:5000
4. In un'altra finestra del terminale, testa con:

   curl -X POST http://localhost:5000/webhook -H "Content-Type: application/json" -d "{\"symbol\":\"BTCUSDT\",\"side\":\"LONG\",\"price\":65000,\"time\":\"2026-08-15T10:00:00Z\"}"

   Se tutto funziona, ricevi subito il messaggio sul tuo bot Telegram.

QUANDO METTI ONLINE (Render/Railway):
Sposta TOKEN e CHAT_ID nelle variabili d'ambiente della piattaforma
invece di lasciarli scritti nel codice, per sicurezza.
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

# Opzionale: una "password" nel messaggio del webhook per verificare che
# arrivi davvero da TradingView e non da qualcun altro che ha indovinato l'URL
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")


def invia_telegram(testo: str) -> None:
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": testo, "parse_mode": "HTML"}
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


@app.route("/", methods=["GET"])
def health():
    return "Webhook server attivo", 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
