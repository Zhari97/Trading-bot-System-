"""Server Flask per webhook TradingView, comandi Telegram e dashboard."""

import html
import hmac
import json
import logging
import os
from pathlib import Path

import requests
from flask import Flask, jsonify, render_template, request

from dashboard_state import read_state, save_ingested_record
from signal_engine import (
    COPPIE_MONITORATE,
    INTERVAL_MIN,
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
    analizza_coppia,
)

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("webhook_server")
app = Flask(__name__)
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")
DASHBOARD_INGEST_TOKEN = os.environ.get("DASHBOARD_INGEST_TOKEN", "")
PAIR = os.environ.get("PAIR", COPPIE_MONITORATE[0] if COPPIE_MONITORATE else "XBTUSD")
RESEARCH_FILE = Path(__file__).with_name("backtest_results.json")

MAPPA_COPPIE = {"BTC": "XBTUSD", "BITCOIN": "XBTUSD", "XBTUSD": "XBTUSD", "ETH": "ETHUSD", "ETHEREUM": "ETHUSD", "ETHUSD": "ETHUSD", "SOL": "SOLUSD", "SOLANA": "SOLUSD", "SOLUSD": "SOLUSD"}
CLASSIFICAZIONI_V22 = {"FORTE", "SETUP", "WATCH", "NO TRADE"}
DIREZIONI = {"LONG", "SHORT", "NEUTRO"}
GUARD_STATI = {"PASS", "BLOCKED", "WARN"}
TELEGRAM_STATI = {"SENT", "FAILED", "NOT_SENT", "BLOCKED"}


def etichetta_categoria(score: float) -> str:
    score = float(score)
    if score >= 70: return "FORTE"
    if score >= 60: return "SETUP"
    if score > 50: return "WATCH"
    if score <= 30: return "FORTE"
    if score <= 40: return "SETUP"
    if score < 50: return "WATCH"
    return "NO TRADE"


def risolvi_coppia(testo_comando: str) -> str:
    parti = testo_comando.strip().split()
    return MAPPA_COPPIE.get(parti[1].upper(), PAIR) if len(parti) >= 2 else PAIR


def invia_telegram(testo: str, chat_id: str = None) -> None:
    if not TELEGRAM_BOT_TOKEN:
        log.error("TELEGRAM_BOT_TOKEN non impostato.")
        return
    destinatario = chat_id or TELEGRAM_CHAT_ID
    if not destinatario:
        log.error("TELEGRAM_CHAT_ID non impostato.")
        return
    try:
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage", json={"chat_id": destinatario, "text": testo, "parse_mode": "HTML"}, timeout=10).raise_for_status()
    except requests.RequestException as exc:
        log.error("Errore invio Telegram: %s", exc)


def costruisci_analisi_html(analisi: dict) -> str:
    categorie = analisi["categorie"]
    righe = [f"🔎 <b>Analisi — {html.escape(analisi['pair'])}</b>", f"Prezzo: <b>{analisi['prezzo']:.5f}</b>", f"🧠 <b>Score: {analisi['score']:.1f}/100 — {analisi['bias']}</b>", f"Trend: {categorie['trend']:.1f}/100 ({etichetta_categoria(categorie['trend'])})", f"Momentum: {categorie['momentum']:.1f}/100 ({etichetta_categoria(categorie['momentum'])})", f"Setup: {categorie['setup']:.1f}/100 ({etichetta_categoria(categorie['setup'])})", f"Confluenza: {'⚠️ CONFLITTO' if analisi['conflitto'] else '✅ CONFLUENZA'}", f"Direzione dominante: {analisi['direzione_dominante']} ({analisi['confluenza']:.1f}%)", ""]
    for risultato in analisi["risultati"]:
        emoji = {"LONG": "🟢", "SHORT": "🔴", "NEUTRO": "⚪"}[risultato["voto"]]
        stato = "ATTIVO" if risultato["attivo"] else "ombra"
        righe.append(f"{emoji} <b>{html.escape(risultato['nome'])}</b>: {risultato['voto']} ({stato})\n<i>{html.escape(risultato['motivo'])}</i>")
    return "\n".join(righe)


def _numero(value, nome, minimo=None, massimo=None):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{nome} non numerico")
    value = float(value)
    if minimo is not None and value < minimo: raise ValueError(f"{nome} sotto il minimo")
    if massimo is not None and value > massimo: raise ValueError(f"{nome} sopra il massimo")
    return value


def _valida_ingest_payload(data):
    if not isinstance(data, dict): raise ValueError("payload JSON non valido")
    required = {"timestamp", "pair", "price", "rsi", "score", "confluence", "direction", "classification", "reason", "counter_trend", "guard_rail", "telegram", "categories", "weights", "strategies"}
    missing = sorted(required - set(data))
    if missing: raise ValueError(f"campi mancanti: {', '.join(missing)}")
    pair = str(data["pair"]).upper()
    classification = str(data["classification"]).upper()
    if classification not in CLASSIFICAZIONI_V22: raise ValueError("classification V2.2 non valida")
    direction = str(data["direction"]).upper()
    if direction not in DIREZIONI: raise ValueError("direction non valida")
    if not isinstance(data["timestamp"], str) or not data["timestamp"].strip(): raise ValueError("timestamp non valido")
    if not isinstance(data["reason"], str): raise ValueError("reason non valido")
    if not isinstance(data["counter_trend"], bool): raise ValueError("counter_trend non valido")
    guard = data["guard_rail"]
    if not isinstance(guard, dict) or guard.get("status") not in GUARD_STATI or not isinstance(guard.get("reason", ""), str): raise ValueError("guard_rail non valido")
    telegram = data["telegram"]
    if telegram not in TELEGRAM_STATI: raise ValueError("telegram status non valido")
    categories, weights, strategies = data["categories"], data["weights"], data["strategies"]
    if not isinstance(categories, dict) or not all(k in categories for k in ("trend", "momentum", "setup")): raise ValueError("categories non valide")
    if not isinstance(weights, dict) or not all(k in weights for k in ("long", "short")): raise ValueError("weights non validi")
    if not isinstance(strategies, list): raise ValueError("strategies non valide")
    clean = {"timestamp": data["timestamp"].strip(), "pair": pair, "price": round(_numero(data["price"], "price", 0), 8), "rsi": round(_numero(data["rsi"], "rsi", 0, 100), 2), "score": round(_numero(data["score"], "score", 0, 100), 2), "confluence": round(_numero(data["confluence"], "confluence", 0, 100), 2), "direction": direction, "classification": classification, "reason": data["reason"][:1000], "counter_trend": data["counter_trend"], "guard_rail": {"status": guard["status"], "reason": guard.get("reason", "")[:1000]}, "telegram": telegram, "categories": {"trend": round(_numero(categories["trend"], "categories.trend", 0, 100), 2), "momentum": round(_numero(categories["momentum"], "categories.momentum", 0, 100), 2), "setup": round(_numero(categories["setup"], "categories.setup", 0, 100), 2)}, "weights": {"long": round(_numero(weights["long"], "weights.long", 0, 100), 2), "short": round(_numero(weights["short"], "weights.short", 0, 100), 2)}, "strategies": []}
    for item in strategies[:30]:
        if isinstance(item, dict) and all(k in item for k in ("nome", "voto", "motivo", "attivo")):
            clean["strategies"].append({"nome": str(item["nome"])[:200], "voto": str(item["voto"])[:20], "motivo": str(item["motivo"])[:500], "attivo": bool(item["attivo"])})
    return clean


@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json(silent=True) or {}
    if WEBHOOK_SECRET and data.get("secret") != WEBHOOK_SECRET: return jsonify({"status": "unauthorized"}), 401
    side = str(data.get("side", "N/D")).upper()
    emoji = "🟢" if side == "LONG" else "🔴" if side == "SHORT" else "⚪"
    invia_telegram(f"{emoji} <b>Segnale {html.escape(side)}</b>\nSimbolo: <b>{html.escape(str(data.get('symbol', 'N/D')))}</b>\nPrezzo: {html.escape(str(data.get('price', 'N/D')))}\nOrario: {html.escape(str(data.get('time', 'N/D')))}")
    return jsonify({"status": "ok"}), 200


@app.route("/telegram-webhook", methods=["POST"])
def telegram_webhook():
    update = request.get_json(silent=True) or {}
    messaggio = update.get("message", {})
    testo = (messaggio.get("text") or "").strip()
    chat_id = messaggio.get("chat", {}).get("id")
    if not testo or not chat_id: return jsonify({"status": "ignored"}), 200
    comando = testo.lower()
    try:
        if comando.startswith(("/status", "/stato")):
            analisi = analizza_coppia(risolvi_coppia(testo)); ctx = analisi["ctx"]; i = ctx.i
            trend = "rialzista" if ctx.ema9[i] > ctx.ema21[i] else "ribassista"
            risposta = f"📊 <b>Stato attuale</b>\nCoppia: <b>{analisi['pair']}</b> (Kraken)\nPrezzo: {analisi['prezzo']:.5f}\nEMA9: {ctx.ema9[i]:.5f}\nEMA21: {ctx.ema21[i]:.5f}\nTrend EMA: {trend}\nRSI: {ctx.rsi14[i]:.1f}\nScore: <b>{analisi['score']:.1f}/100</b> — {analisi['bias']}\nTrend/Momentum/Setup: {analisi['categorie']['trend']:.1f} / {analisi['categorie']['momentum']:.1f} / {analisi['categorie']['setup']:.1f}\nConfluenza: {'⚠️ CONFLITTO' if analisi['conflitto'] else '✅ CONFLUENZA'}\nTimeframe: {INTERVAL_MIN}m"
        elif comando.startswith(("/analisi", "/voti")):
            risposta = costruisci_analisi_html(analizza_coppia(risolvi_coppia(testo)))
        elif comando.startswith("/score"):
            analisi = analizza_coppia(risolvi_coppia(testo))
            risposta = f"🧠 <b>Score {analisi['pair']}</b>\n<b>{analisi['score']:.1f}/100 — {analisi['bias']}</b>\n🟢 Peso LONG: {analisi['peso_long']:.0f}\n🔴 Peso SHORT: {analisi['peso_short']:.0f}\nTrend: {analisi['categorie']['trend']:.1f}\nMomentum: {analisi['categorie']['momentum']:.1f}\nSetup: {analisi['categorie']['setup']:.1f}\nConfluenza: {'⚠️ CONFLITTO' if analisi['conflitto'] else '✅ CONFLUENZA'}\nRSI: {analisi['ctx'].rsi14[analisi['ctx'].i]:.1f}\nTF: {INTERVAL_MIN}m"
        elif comando in ("/start", "/help", "/aiuto"):
            risposta = "👋 <b>Bot segnali</b>\n\n/status [BTC|ETH|SOL] — stato rapido\n/score [BTC|ETH|SOL] — score confluenza 0-100\n/analisi [BTC|ETH|SOL] — tutti i moduli\n\n" + f"Coppie monitorate: {', '.join(COPPIE_MONITORATE)}\nTimeframe: {INTERVAL_MIN}m"
        else:
            risposta = "❓ Comando non riconosciuto. Usa /help."
    except Exception:
        log.exception("Errore gestione comando Telegram")
        risposta = "⚠️ Errore durante l'analisi. Riprova tra poco."
    invia_telegram(risposta, str(chat_id))
    return jsonify({"status": "ok"}), 200


@app.route("/health", methods=["GET"])
def health(): return jsonify({"status": "ok", "service": "webhook_server"}), 200


@app.route("/api/status", methods=["GET"])
def api_status(): return jsonify(read_state().get("status", {})), 200


@app.route("/api/markets", methods=["GET"])
def api_markets(): return jsonify(read_state().get("markets", {})), 200


@app.route("/api/history", methods=["GET"])
def api_history(): return jsonify(read_state().get("history", [])), 200


@app.route("/api/signals", methods=["GET"])
def api_signals(): return jsonify(read_state().get("signals", [])), 200


@app.route("/api/research", methods=["GET"])
def api_research():
    if not RESEARCH_FILE.exists():
        return jsonify({"status": "not_ready", "timeframes": {}}), 200
    try:
        return jsonify(json.loads(RESEARCH_FILE.read_text(encoding="utf-8"))), 200
    except (OSError, json.JSONDecodeError):
        log.exception("Impossibile leggere i risultati research")
        return jsonify({"status": "error", "timeframes": {}}), 500


@app.route("/api/ingest", methods=["POST"])
def api_ingest():
    expected = DASHBOARD_INGEST_TOKEN
    provided = request.headers.get("X-Dashboard-Token", "")
    if not expected or not hmac.compare_digest(provided, expected): return jsonify({"status": "unauthorized"}), 401
    try:
        clean = _valida_ingest_payload(request.get_json(silent=True)); save_ingested_record(clean)
        return jsonify({"status": "ok", "pair": clean["pair"], "classification": clean["classification"]}), 200
    except ValueError as exc: return jsonify({"status": "invalid", "error": str(exc)}), 400
    except Exception:
        log.exception("Errore ingest dashboard"); return jsonify({"status": "error"}), 500


@app.route("/", methods=["GET"])
def dashboard(): return render_template("dashboard.html", stato=read_state())


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    app.run(host="0.0.0.0", port=port, debug=False)
