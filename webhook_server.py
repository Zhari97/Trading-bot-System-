"""
Server webhook: riceve i segnali da TradingView (se in futuro li userai) e li
inoltra su Telegram. Ora ascolta ANCHE i comandi che scrivi al bot Telegram
(es. /status) e risponde in tempo reale.

TEST IN LOCALE:
1. pip install flask requests
2. python webhook_server.py
3. Il server parte su http://localhost:5000

QUANDO METTI ONLINE (Render/Railway):
Sposta TOKEN e CHAT_ID nelle variabili d'ambiente della piattaforma
invece di lasciarli scritti nel codice, per sicurezza.

PER ATTIVARE I COMANDI TELEGRAM (/status ecc.):
Dopo il deploy, va registrato l'URL del server come "webhook" del bot,
chiamando UNA VOLTA questo indirizzo nel browser (sostituendo TOKEN e URL):
https://api.telegram.org/bot<IL_TUO_TOKEN>/setWebhook?url=https://IL-TUO-SERVER.onrender.com/telegram-webhook
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

# ==== PARAMETRI STRATEGIA (stessi valori degli altri script) ====
PAIR = os.environ.get("PAIR", "XBTUSD")
INTERVAL_MIN = int(os.environ.get("INTERVAL_MIN", "15"))
EMA_FAST_LEN = 9
EMA_SLOW_LEN = 21
RSI_LEN = 14

KRAKEN_OHLC_URL = "https://api.kraken.com/0/public/OHLC"


# ---------- Funzioni condivise con lo script di controllo periodico ----------

def scarica_candele(pair: str, interval_min: int):
    """Restituisce solo le chiusure (usato da calcola_stato_attuale per /status)."""
    return [c["close"] for c in scarica_candele_ohlc(pair, interval_min)]


def scarica_candele_ohlc(pair: str, interval_min: int):
    """Restituisce candele complete (OHLC + volume), usato da /analisi."""
    params = {"pair": pair, "interval": interval_min}
    r = requests.get(KRAKEN_OHLC_URL, params=params, timeout=15)
    r.raise_for_status()
    dati = r.json()
    if dati.get("error"):
        raise RuntimeError(f"Errore API Kraken: {dati['error']}")
    risultato = dati["result"]
    chiave_coppia = next(k for k in risultato.keys() if k != "last")
    candele_raw = risultato[chiave_coppia]
    return [
        {
            "open": float(c[1]), "high": float(c[2]),
            "low": float(c[3]), "close": float(c[4]),
            "volume": float(c[6]),
        }
        for c in candele_raw
    ]


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


# ---------- Moduli strategia (stessa logica di segnale_crypto_binance.py) ----------

def calcola_bollinger(valori, periodo=20, num_deviazioni=2):
    centro, superiore, inferiore = [], [], []
    for i in range(len(valori)):
        inizio = max(0, i - periodo + 1)
        finestra = valori[inizio:i + 1]
        media = sum(finestra) / len(finestra)
        varianza = sum((x - media) ** 2 for x in finestra) / len(finestra)
        dev_std = varianza ** 0.5
        centro.append(media)
        superiore.append(media + num_deviazioni * dev_std)
        inferiore.append(media - num_deviazioni * dev_std)
    return centro, superiore, inferiore


def calcola_atr(candele, periodo=14):
    tr = []
    for i in range(len(candele)):
        if i == 0:
            tr.append(candele[i]["high"] - candele[i]["low"])
        else:
            prev_close = candele[i - 1]["close"]
            tr.append(max(
                candele[i]["high"] - candele[i]["low"],
                abs(candele[i]["high"] - prev_close),
                abs(candele[i]["low"] - prev_close),
            ))
    atr = []
    for i in range(len(tr)):
        inizio = max(0, i - periodo + 1)
        finestra = tr[inizio:i + 1]
        atr.append(sum(finestra) / len(finestra))
    return atr


def donchian_mid(candele, periodo):
    valori = []
    for i in range(len(candele)):
        inizio = max(0, i - periodo + 1)
        finestra = candele[inizio:i + 1]
        massimo = max(c["high"] for c in finestra)
        minimo = min(c["low"] for c in finestra)
        valori.append((massimo + minimo) / 2)
    return valori


def trova_swing_high_low(candele, i, lookback=50):
    inizio = max(0, i - lookback + 1)
    finestra = candele[inizio:i + 1]
    idx_max = max(range(len(finestra)), key=lambda k: finestra[k]["high"])
    idx_min = min(range(len(finestra)), key=lambda k: finestra[k]["low"])
    return {
        "massimo": finestra[idx_max]["high"], "minimo": finestra[idx_min]["low"],
        "idx_massimo": inizio + idx_max, "idx_minimo": inizio + idx_min,
    }


def conferma_rialzista(candele, i):
    return is_engulfing_rialzista(candele[i - 1], candele[i]) or is_pin_bar_rialzista(candele[i])


def conferma_ribassista(candele, i):
    return is_engulfing_ribassista(candele[i - 1], candele[i]) or is_pin_bar_ribassista(candele[i])


def corpo(c):
    return abs(c["close"] - c["open"])


def is_rialzista(c):
    return c["close"] > c["open"]


def is_ribassista(c):
    return c["close"] < c["open"]


def is_engulfing_rialzista(prev, cur):
    return (is_ribassista(prev) and is_rialzista(cur)
            and cur["open"] <= prev["close"] and cur["close"] >= prev["open"])


def is_engulfing_ribassista(prev, cur):
    return (is_rialzista(prev) and is_ribassista(cur)
            and cur["open"] >= prev["close"] and cur["close"] <= prev["open"])


def is_pin_bar_rialzista(c):
    range_totale = c["high"] - c["low"]
    if range_totale <= 0:
        return False
    ombra_inferiore = min(c["open"], c["close"]) - c["low"]
    return ombra_inferiore > 2 * corpo(c) and ombra_inferiore > range_totale * 0.5


def is_pin_bar_ribassista(c):
    range_totale = c["high"] - c["low"]
    if range_totale <= 0:
        return False
    ombra_superiore = c["high"] - max(c["open"], c["close"])
    return ombra_superiore > 2 * corpo(c) and ombra_superiore > range_totale * 0.5


def calcola_analisi_completa():
    """Calcola il voto di tutti e 6 i moduli strategia, come nel controllo
    automatico ogni 15 minuti, ma richiamabile in tempo reale da Telegram."""
    candele = scarica_candele_ohlc(PAIR, INTERVAL_MIN)
    chiusure = [c["close"] for c in candele]

    ema9 = calcola_ema(chiusure, 9)
    ema21 = calcola_ema(chiusure, 21)
    ema50 = calcola_ema(chiusure, 50)
    rsi14 = calcola_rsi(chiusure, 14)
    ema12 = calcola_ema(chiusure, 12)
    ema26 = calcola_ema(chiusure, 26)
    macd_linea = [a - b for a, b in zip(ema12, ema26)]
    macd_segnale = calcola_ema(macd_linea, 9)
    macd_istogramma = [a - b for a, b in zip(macd_linea, macd_segnale)]
    bb_centro, bb_superiore, bb_inferiore = calcola_bollinger(chiusure, 20, 2)
    atr14 = calcola_atr(candele, 14)
    tenkan = donchian_mid(candele, 9)
    kijun = donchian_mid(candele, 26)
    senkou_b = donchian_mid(candele, 52)
    senkou_a = [(a + b) / 2 for a, b in zip(tenkan, kijun)]

    i = len(candele) - 2
    prezzo = chiusure[i]
    risultati = []

    # 1) EMA + RSI + conferma
    incrocio_long = ema9[i - 1] <= ema21[i - 1] and ema9[i] > ema21[i]
    incrocio_short = ema9[i - 1] >= ema21[i - 1] and ema9[i] < ema21[i]
    trend_su = prezzo > ema50[i]
    trend_giu = prezzo < ema50[i]
    conf_long = is_engulfing_rialzista(candele[i - 1], candele[i]) or is_pin_bar_rialzista(candele[i])
    conf_short = is_engulfing_ribassista(candele[i - 1], candele[i]) or is_pin_bar_ribassista(candele[i])
    if incrocio_long and rsi14[i] < 70 and trend_su and conf_long:
        v1 = ("LONG", "Incrocio EMA + RSI ok + trend + candela conferma")
    elif incrocio_short and rsi14[i] > 30 and trend_giu and conf_short:
        v1 = ("SHORT", "Incrocio EMA + RSI ok + trend + candela conferma")
    else:
        v1 = ("NEUTRO", "Condizioni non allineate")
    risultati.append(("EMA9/21+RSI+conferma", *v1))

    # 2) MACD
    incrocio_macd_su = macd_linea[i - 1] <= macd_segnale[i - 1] and macd_linea[i] > macd_segnale[i]
    incrocio_macd_giu = macd_linea[i - 1] >= macd_segnale[i - 1] and macd_linea[i] < macd_segnale[i]
    if incrocio_macd_su and macd_istogramma[i] > macd_istogramma[i - 1]:
        v2 = ("LONG", "MACD incrocia sopra segnale")
    elif incrocio_macd_giu and macd_istogramma[i] < macd_istogramma[i - 1]:
        v2 = ("SHORT", "MACD incrocia sotto segnale")
    else:
        v2 = ("NEUTRO", "Nessun incrocio MACD")
    risultati.append(("MACD 12/26/9", *v2))

    # 3) Bollinger
    c = candele[i]
    if c["low"] <= bb_inferiore[i] and c["close"] > bb_inferiore[i]:
        v3 = ("LONG", "Rientro da banda inferiore")
    elif c["high"] >= bb_superiore[i] and c["close"] < bb_superiore[i]:
        v3 = ("SHORT", "Rientro da banda superiore")
    else:
        v3 = ("NEUTRO", "Nessun tocco/rientro bande")
    risultati.append(("Bollinger 20,2", *v3))

    # 4) Struttura trend
    finestra = 10
    if i - 2 * finestra >= 0:
        recenti = candele[i - finestra + 1: i + 1]
        precedenti = candele[i - 2 * finestra + 1: i - finestra + 1]
        max_r, max_p = max(x["high"] for x in recenti), max(x["high"] for x in precedenti)
        min_r, min_p = min(x["low"] for x in recenti), min(x["low"] for x in precedenti)
        if max_r > max_p and min_r > min_p:
            v4 = ("LONG", "Massimi/minimi crescenti")
        elif max_r < max_p and min_r < min_p:
            v4 = ("SHORT", "Massimi/minimi calanti")
        else:
            v4 = ("NEUTRO", "Struttura non chiara")
    else:
        v4 = ("NEUTRO", "Dati insufficienti")
    risultati.append(("Struttura trend HH/HL", *v4))

    # 5) Supporti/Resistenze
    finestra_sr = 20
    if i - finestra_sr >= 0:
        precedenti = candele[i - finestra_sr: i]
        resistenza = max(x["high"] for x in precedenti)
        supporto = min(x["low"] for x in precedenti)
        if c["close"] > resistenza:
            v5 = ("LONG", f"Rottura sopra resistenza {finestra_sr} candele")
        elif c["close"] < supporto:
            v5 = ("SHORT", f"Rottura sotto supporto {finestra_sr} candele")
        else:
            v5 = ("NEUTRO", "Dentro il range recente")
    else:
        v5 = ("NEUTRO", "Dati insufficienti")
    risultati.append(("Rottura S/R", *v5))

    # 6) Wyckoff-lite
    finestra_w = 15
    if i - finestra_w - 1 >= 0:
        range_prec = candele[i - finestra_w: i]
        ampiezza_media = sum(x["high"] - x["low"] for x in range_prec) / finestra_w
        volume_medio = sum(x["volume"] for x in range_prec) / finestra_w
        compresso = ampiezza_media > 0 and all(
            (x["high"] - x["low"]) < ampiezza_media * 1.3 for x in range_prec[-5:]
        )
        rottura_vol = c["volume"] > volume_medio * 1.5 and (c["high"] - c["low"]) > ampiezza_media
        minimo_r = min(x["low"] for x in range_prec)
        massimo_r = max(x["high"] for x in range_prec)
        spring = compresso and rottura_vol and c["low"] < minimo_r and c["close"] > minimo_r
        upthrust = compresso and rottura_vol and c["high"] > massimo_r and c["close"] < massimo_r
        if spring:
            v6 = ("LONG", "Possibile spring (approssimato)")
        elif upthrust:
            v6 = ("SHORT", "Possibile upthrust (approssimato)")
        else:
            v6 = ("NEUTRO", "Nessun pattern rilevato")
    else:
        v6 = ("NEUTRO", "Dati insufficienti")
    risultati.append(("Wyckoff-lite (approssimato)", *v6))

    # 7) ATR Breakout
    range_candela = c["high"] - c["low"]
    if range_candela > 0 and atr14[i] > 0:
        range_anomalo = range_candela > atr14[i] * 1.5
        posizione = (c["close"] - c["low"]) / range_candela
        if range_anomalo and posizione > 0.7 and is_rialzista(c):
            v7 = ("LONG", "Candela range anomalo, chiusura vicina al massimo")
        elif range_anomalo and posizione < 0.3 and is_ribassista(c):
            v7 = ("SHORT", "Candela range anomalo, chiusura vicina al minimo")
        else:
            v7 = ("NEUTRO", "Nessun breakout di volatilita")
    else:
        v7 = ("NEUTRO", "Dati insufficienti")
    risultati.append(("ATR Breakout", *v7))

    # 8) Fibonacci
    if i >= 51:
        swing = trova_swing_high_low(candele, i, lookback=50)
        ampiezza = swing["massimo"] - swing["minimo"]
        if ampiezza > 0:
            tolleranza = ampiezza * 0.05
            swing_ribassista = swing["idx_minimo"] > swing["idx_massimo"]
            if swing_ribassista:
                liv_50 = swing["minimo"] + 0.5 * ampiezza
                liv_618 = swing["minimo"] + 0.382 * ampiezza
                vicino = abs(c["close"] - liv_50) < tolleranza or abs(c["close"] - liv_618) < tolleranza
                if vicino and conferma_rialzista(candele, i):
                    v8 = ("LONG", "Rimbalzo su livello Fibonacci con conferma")
                else:
                    v8 = ("NEUTRO", "Nessun rimbalzo Fibonacci confermato")
            else:
                liv_50 = swing["massimo"] - 0.5 * ampiezza
                liv_618 = swing["massimo"] - 0.382 * ampiezza
                vicino = abs(c["close"] - liv_50) < tolleranza or abs(c["close"] - liv_618) < tolleranza
                if vicino and conferma_ribassista(candele, i):
                    v8 = ("SHORT", "Ritracciamento su livello Fibonacci con conferma")
                else:
                    v8 = ("NEUTRO", "Nessun ritracciamento Fibonacci confermato")
        else:
            v8 = ("NEUTRO", "Range piatto")
    else:
        v8 = ("NEUTRO", "Dati insufficienti")
    risultati.append(("Fibonacci 50/61.8", *v8))

    # 9) Ichimoku (approssimato)
    if i >= 52:
        nuvola_sup = max(senkou_a[i], senkou_b[i])
        nuvola_inf = min(senkou_a[i], senkou_b[i])
        if prezzo > nuvola_sup and tenkan[i] > kijun[i]:
            v9 = ("LONG", "Prezzo sopra la nuvola, Tenkan sopra Kijun")
        elif prezzo < nuvola_inf and tenkan[i] < kijun[i]:
            v9 = ("SHORT", "Prezzo sotto la nuvola, Tenkan sotto Kijun")
        else:
            v9 = ("NEUTRO", "Dentro la nuvola o segnali contrastanti")
    else:
        v9 = ("NEUTRO", "Dati insufficienti")
    risultati.append(("Ichimoku (approssimato)", *v9))

    return prezzo, rsi14[i], risultati


# ---------- Invio messaggi Telegram ----------

def invia_telegram(testo: str, chat_id: str = None) -> None:
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id or TELEGRAM_CHAT_ID, "text": testo, "parse_mode": "HTML"}
    try:
        r = requests.post(url, json=payload, timeout=10)
        r.raise_for_status()
    except requests.RequestException as e:
        log.error("Errore invio Telegram: %s", e)


# ---------- Route: segnali da TradingView (se in futuro li usi) ----------

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


# ---------- Route: comandi che scrivi al bot Telegram ----------

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

    elif comando in ("/analisi", "/voti"):
        try:
            prezzo, rsi_attuale, risultati = calcola_analisi_completa()
            righe = [f"🔎 <b>Analisi completa — {PAIR}</b>", f"Prezzo: {prezzo:.2f} | RSI: {rsi_attuale:.1f}", ""]
            voti_long = 0
            voti_short = 0
            for nome, voto, motivo in risultati:
                emoji = {"LONG": "🟢", "SHORT": "🔴", "NEUTRO": "⚪"}[voto]
                righe.append(f"{emoji} <b>{nome}</b>: {voto}\n<i>{motivo}</i>")
                if voto == "LONG":
                    voti_long += 1
                elif voto == "SHORT":
                    voti_short += 1
            righe.append("")
            righe.append(f"Totale: {voti_long} LONG / {voti_short} SHORT su {len(risultati)} moduli")
            risposta = "\n".join(righe)
        except Exception as e:
            log.error("Errore calcolo analisi completa: %s", e)
            risposta = "⚠️ Non sono riuscito a calcolare l'analisi in questo momento, riprova tra poco."
        invia_telegram(risposta, chat_id=chat_id)

    elif comando in ("/start", "/help", "/aiuto"):
        risposta = (
            "👋 Ciao! Comandi disponibili:\n"
            "/status — prezzo, EMA e RSI attuali (rapido)\n"
            "/analisi — voto di tutti e 6 i moduli strategia in tempo reale\n\n"
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
