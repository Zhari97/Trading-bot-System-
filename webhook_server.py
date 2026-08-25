"""Server Flask per webhook TradingView e comandi Telegram."""

import html
import logging
import os

import requests
from flask import Flask, jsonify, request

from signal_engine import (
    COPPIE_MONITORATE,
    INTERVAL_MIN,
    MODULI_STRATEGIA,
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
    analizza_coppia,
)

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("webhook_server")
app = Flask(__name__)

WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")
PAIR = os.environ.get("PAIR", COPPIE_MONITORATE[0] if COPPIE_MONITORATE else "XBTUSD")

MAPPA_COPPIE = {
    "BTC": "XBTUSD", "BITCOIN": "XBTUSD", "XBTUSD": "XBTUSD",
    "ETH": "ETHUSD", "ETHEREUM": "ETHUSD", "ETHUSD": "ETHUSD",
    "SOL": "SOLUSD", "SOLANA": "SOLUSD", "SOLUSD": "SOLUSD",
}


def risolvi_coppia(testo_comando: str) -> str:
    parti = testo_comando.strip().split()
    if len(parti) >= 2:
        richiesta = parti[1].upper()
        return MAPPA_COPPIE.get(richiesta, PAIR)
    return PAIR


def invia_telegram(testo: str, chat_id: str = None) -> None:
    if not TELEGRAM_BOT_TOKEN:
        log.error("TELEGRAM_BOT_TOKEN non impostato.")
        return
    destinatario = chat_id or TELEGRAM_CHAT_ID
    if not destinatario:
        log.error("TELEGRAM_CHAT_ID non impostato.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": destinatario, "text": testo, "parse_mode": "HTML"}
    try:
        r = requests.post(url, json=payload, timeout=10)
        r.raise_for_status()
    except requests.RequestException as e:
        log.error("Errore invio Telegram: %s", e)


def costruisci_analisi_html(analisi: dict) -> str:
    righe = [
        f"🔎 <b>Analisi — {html.escape(analisi['pair'])}</b>",
        f"Prezzo: <b>{analisi['prezzo']:.5f}</b> | RSI: {analisi['rsi']:.1f}",
        f"🧠 <b>Score: {analisi['score']:.1f}/100 — {analisi['bias']}</b>",
        f"Confluenza pesata: 🟢 {analisi['peso_long']:.0f} / 🔴 {analisi['peso_short']:.0f}",
        "",
    ]
    for risultato in analisi["risultati"]:
        emoji = {"LONG": "🟢", "SHORT": "🔴", "NEUTRO": "⚪"}[risultato["voto"]]
        stato = "ATTIVO" if risultato["attivo"] else "ombra"
        righe.append(
            f"{emoji} <b>{html.escape(risultato['nome'])}</b>: {risultato['voto']} ({stato})\n"
            f"<i>{html.escape(risultato['motivo'])}</i>"
        )
    return "\n".join(righe)


@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json(silent=True) or {}
    if WEBHOOK_SECRET and data.get("secret") != WEBHOOK_SECRET:
        return jsonify({"status": "unauthorized"}), 401

    side = str(data.get("side", "N/D")).upper()
    emoji = "🟢" if side == "LONG" else "🔴" if side == "SHORT" else "⚪"
    messaggio = (
        f"{emoji} <b>Segnale {html.escape(side)}</b>\n"
        f"Simbolo: <b>{html.escape(str(data.get('symbol', 'N/D')))}</b>\n"
        f"Prezzo: {html.escape(str(data.get('price', 'N/D')))}\n"
        f"Orario: {html.escape(str(data.get('time', 'N/D')))}"
    )
    invia_telegram(messaggio)
    return jsonify({"status": "ok"}), 200


@app.route("/telegram-webhook", methods=["POST"])
def telegram_webhook():
    update = request.get_json(silent=True) or {}
    messaggio = update.get("message", {})
    testo = (messaggio.get("text") or "").strip()
    chat_id = messaggio.get("chat", {}).get("id")
    if not testo or not chat_id:
        return jsonify({"status": "ignored"}), 200

    comando = testo.lower()
    try:
        if comando.startswith(("/status", "/stato")):
            analisi = analizza_coppia(risolvi_coppia(testo))
            ctx = analisi["ctx"]
            i = ctx.i
            trend = "rialzista" if ctx.ema9[i] > ctx.ema21[i] else "ribassista"
            risposta = (
                f"📊 <b>Stato attuale</b>\n"
                f"Coppia: <b>{analisi['pair']}</b> (Kraken)\n"
                f"Prezzo: {analisi['prezzo']:.5f}\n"
                f"EMA9: {ctx.ema9[i]:.5f}\n"
                f"EMA21: {ctx.ema21[i]:.5f}\n"
                f"Trend EMA: {trend}\n"
                f"RSI: {analisi['rsi']:.1f}\n"
                f"Score: <b>{analisi['score']:.1f}/100</b> — {analisi['bias']}\n"
                f"Timeframe: {INTERVAL_MIN}m"
            )
        elif comando.startswith(("/analisi", "/voti")):
            risposta = costruisci_analisi_html(analizza_coppia(risolvi_coppia(testo)))
        elif comando.startswith("/score"):
            analisi = analizza_coppia(risolvi_coppia(testo))
            risposta = (
                f"🧠 <b>Score {analisi['pair']}</b>\n"
                f"<b>{analisi['score']:.1f}/100 — {analisi['bias']}</b>\n"
                f"🟢 Peso LONG: {analisi['peso_long']:.0f}\n"
                f"🔴 Peso SHORT: {analisi['peso_short']:.0f}\n"
                f"RSI: {analisi['rsi']:.1f}\n"
                f"TF: {INTERVAL_MIN}m"
            )
        elif comando in ("/start", "/help", "/aiuto"):
            risposta = (
                "👋 <b>Bot segnali</b>\n\n"
                "/status [BTC|ETH|SOL] — stato rapido\n"
                "/score [BTC|ETH|SOL] — score confluenza 0-100\n"
                "/analisi [BTC|ETH|SOL] — tutti i moduli\n\n"
                f"Coppie monitorate: {', '.join(COPPIE_MONITORATE)}\n"
                f"Timeframe: {INTERVAL_MIN}m"
            )
        else:
            risposta = "❓ Comando non riconosciuto. Usa /help."
    except Exception as e:
        log.exception("Errore comando Telegram")
        risposta = "⚠️ Errore durante l'analisi. Riprova tra poco."

    invia_telegram(risposta, chat_id=chat_id)
    return jsonify({"status": "ok"}), 200


@app.route("/", methods=["GET"])
def health():
    return "Webhook server attivo", 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
