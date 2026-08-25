"""Motore centrale del bot crypto.

Contiene acquisizione dati, indicatori, strategie e scoring condivisi da
GitHub Actions e dal server Telegram. Nessun token viene hardcodato.
"""


import os
import logging
import requests

from api_budget import cached_call

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("segnale_crypto")

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

MODALITA_TEST = os.environ.get("MODALITA_TEST", "0") == "1"

# ==== PARAMETRI GENERALI ====
# Coppie CRYPTO (Kraken), separate da virgola.
COPPIE_CRYPTO = [p.strip() for p in os.environ.get("PAIRS", "XBTUSD,ETHUSD,SOLUSD").split(",") if p.strip()]

# Coppie FOREX (Twelve Data), separate da virgola. Formato Twelve Data: "EUR/USD".
COPPIE_FOREX = [p.strip() for p in os.environ.get("FOREX_PAIRS", "EUR/USD,GBP/USD,USD/JPY").split(",") if p.strip()]

TWELVE_DATA_API_KEY = os.environ.get("TWELVE_DATA_API_KEY", "")
TWELVE_DATA_URL = "https://api.twelvedata.com/time_series"

# Lista unificata: ogni strumento sa da solo quale fonte dati usare.
COPPIE_MONITORATE = COPPIE_CRYPTO

STRUMENTI_MONITORATI = (
    [{"nome": p, "mercato": "crypto"} for p in COPPIE_CRYPTO]
    + [{"nome": p, "mercato": "forex"} for p in COPPIE_FOREX]
)

INTERVAL_MIN = int(os.environ.get("INTERVAL_MIN", "15"))

KRAKEN_OHLC_URL = "https://api.kraken.com/0/public/OHLC"


# ============================================================
# ACQUISIZIONE DATI
# ============================================================

def _scarica_candele_ohlc(pair: str, interval_min: int):
    """Richiesta HTTP effettiva verso Kraken."""
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
            "open": float(c[1]),
            "high": float(c[2]),
            "low": float(c[3]),
            "close": float(c[4]),
            "volume": float(c[6]),
        }
        for c in candele_raw
    ]


def scarica_candele_ohlc(pair: str, interval_min: int):
    """Restituisce le candele con cache breve, rate guard e retry transitori."""
    key = f"kraken:ohlc:{pair}:{interval_min}"
    return cached_call(key, lambda: _scarica_candele_ohlc(pair, interval_min))


# ============================================================
# INDICATORI CONDIVISI (usati da più moduli)
# ============================================================

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


def calcola_bollinger(valori, periodo=20, num_deviazioni=2):
    """Restituisce (banda_centrale, banda_superiore, banda_inferiore),
    ognuna lunga quanto 'valori' (i primi punti, prima di avere
    abbastanza storico, usano la media/deviazione disponibile fino a quel momento)."""
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
    """Average True Range: misura la volatilità media recente."""
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
    """Punto medio tra massimo e minimo delle ultime N candele — usato
    per Tenkan-sen, Kijun-sen e Senkou Span B dell'Ichimoku semplificato."""
    valori = []
    for i in range(len(candele)):
        inizio = max(0, i - periodo + 1)
        finestra = candele[inizio:i + 1]
        massimo = max(c["high"] for c in finestra)
        minimo = min(c["low"] for c in finestra)
        valori.append((massimo + minimo) / 2)
    return valori


def trova_swing_high_low(candele, i, lookback=50):
    """Trova il massimo e il minimo (con relativi indici) nelle ultime
    'lookback' candele fino all'indice i incluso. Usato per Fibonacci."""
    inizio = max(0, i - lookback + 1)
    finestra = candele[inizio:i + 1]
    idx_max = max(range(len(finestra)), key=lambda k: finestra[k]["high"])
    idx_min = min(range(len(finestra)), key=lambda k: finestra[k]["low"])
    return {
        "massimo": finestra[idx_max]["high"],
        "minimo": finestra[idx_min]["low"],
        "idx_massimo": inizio + idx_max,
        "idx_minimo": inizio + idx_min,
    }


def corpo(c):
    return abs(c["close"] - c["open"])


def is_rialzista(c):
    return c["close"] > c["open"]


def is_ribassista(c):
    return c["close"] < c["open"]


def is_engulfing_rialzista(prev, cur):
    return (
        is_ribassista(prev)
        and is_rialzista(cur)
        and cur["open"] <= prev["close"]
        and cur["close"] >= prev["open"]
    )


def is_engulfing_ribassista(prev, cur):
    return (
        is_rialzista(prev)
        and is_ribassista(cur)
        and cur["open"] >= prev["close"]
        and cur["close"] <= prev["open"]
    )


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


def conferma_rialzista(candele, i):
    return is_engulfing_rialzista(candele[i - 1], candele[i]) or is_pin_bar_rialzista(candele[i])


def conferma_ribassista(candele, i):
    return is_engulfing_ribassista(candele[i - 1], candele[i]) or is_pin_bar_ribassista(candele[i])


# ============================================================
# CONTESTO DI MERCATO — calcolato una volta sola, passato a ogni modulo
# ============================================================

class ContestoMercato:
    """Raccoglie candele e indicatori comuni, così ogni modulo strategia
    non deve ricalcolare da zero le stesse cose."""

    def __init__(self, candele):
        self.candele = candele
        self.chiusure = [c["close"] for c in candele]
        self.ema9 = calcola_ema(self.chiusure, 9)
        self.ema21 = calcola_ema(self.chiusure, 21)
        self.ema50 = calcola_ema(self.chiusure, 50)
        self.rsi14 = calcola_rsi(self.chiusure, 14)

        # MACD: EMA12 - EMA26, linea segnale = EMA9 del MACD
        ema12 = calcola_ema(self.chiusure, 12)
        ema26 = calcola_ema(self.chiusure, 26)
        self.macd_linea = [a - b for a, b in zip(ema12, ema26)]
        self.macd_segnale = calcola_ema(self.macd_linea, 9)
        self.macd_istogramma = [a - b for a, b in zip(self.macd_linea, self.macd_segnale)]

        # Bollinger Bands: SMA20 +/- 2 deviazioni standard
        self.bb_centro, self.bb_superiore, self.bb_inferiore = calcola_bollinger(self.chiusure, 20, 2)

        # ATR (volatilita)
        self.atr14 = calcola_atr(candele, 14)

        # Ichimoku semplificato (senza il forward-shift classico, approssimato)
        self.tenkan = donchian_mid(candele, 9)
        self.kijun = donchian_mid(candele, 26)
        self.senkou_b = donchian_mid(candele, 52)
        self.senkou_a = [(a + b) / 2 for a, b in zip(self.tenkan, self.kijun)]

        # indice dell'ultima candela CHIUSA (l'ultima potrebbe essere in formazione)
        self.i = len(candele) - 2

    def abbastanza_dati(self) -> bool:
        return len(self.chiusure) >= 60  # margine sufficiente per tutti i moduli attivi


# ============================================================
# MODULI STRATEGIA
# Ogni modulo: riceve il ContestoMercato, restituisce un dict con
# nome, voto ("LONG" / "SHORT" / "NEUTRO"), motivo, attivo (bool)
# ============================================================


def strategia_ema_rsi_conferma(ctx: ContestoMercato) -> dict:
    """Modulo originale: incrocio EMA9/21 + filtro RSI + filtro di trend
    EMA50 + candela di conferma (engulfing o pin bar). ATTIVO: manda
    davvero gli alert su Telegram, come nella versione precedente."""
    i = ctx.i
    prezzo = ctx.chiusure[i]

    incrocio_long = ctx.ema9[i - 1] <= ctx.ema21[i - 1] and ctx.ema9[i] > ctx.ema21[i]
    incrocio_short = ctx.ema9[i - 1] >= ctx.ema21[i - 1] and ctx.ema9[i] < ctx.ema21[i]

    trend_su = prezzo > ctx.ema50[i]
    trend_giu = prezzo < ctx.ema50[i]

    rsi_ok_long = ctx.rsi14[i] < 70
    rsi_ok_short = ctx.rsi14[i] > 30

    conferma_long = (
        is_engulfing_rialzista(ctx.candele[i - 1], ctx.candele[i])
        or is_pin_bar_rialzista(ctx.candele[i])
    )
    conferma_short = (
        is_engulfing_ribassista(ctx.candele[i - 1], ctx.candele[i])
        or is_pin_bar_ribassista(ctx.candele[i])
    )

    long_ok = incrocio_long and rsi_ok_long and trend_su and conferma_long
    short_ok = incrocio_short and rsi_ok_short and trend_giu and conferma_short

    if long_ok:
        voto, motivo = "LONG", "Incrocio EMA9>21 + RSI ok + trend rialzista + candela di conferma"
    elif short_ok:
        voto, motivo = "SHORT", "Incrocio EMA9<21 + RSI ok + trend ribassista + candela di conferma"
    else:
        voto, motivo = "NEUTRO", "Condizioni non tutte allineate"

    return {
        "nome": "EMA9/21 + RSI + conferma",
        "voto": voto,
        "motivo": motivo,
        "attivo": True,
    }


def strategia_macd(ctx: ContestoMercato) -> dict:
    """Modulo MACD: incrocio tra la linea MACD e la linea segnale.
    IN OMBRA per ora."""
    i = ctx.i
    incrocio_rialzista = (
        ctx.macd_linea[i - 1] <= ctx.macd_segnale[i - 1]
        and ctx.macd_linea[i] > ctx.macd_segnale[i]
    )
    incrocio_ribassista = (
        ctx.macd_linea[i - 1] >= ctx.macd_segnale[i - 1]
        and ctx.macd_linea[i] < ctx.macd_segnale[i]
    )
    if incrocio_rialzista:
        voto, motivo = "LONG", "Incrocio MACD rialzista"
    elif incrocio_ribassista:
        voto, motivo = "SHORT", "Incrocio MACD ribassista"
    else:
        voto, motivo = "NEUTRO", "Nessun incrocio MACD"
    return {"nome": "MACD", "voto": voto, "motivo": motivo, "attivo": False}


def _carica_strategie(ctx: ContestoMercato) -> list[dict]:
    """Mantiene l'ordine e il set di strategie già usati dal motore."""
    risultati = [strategia_ema_rsi_conferma(ctx), strategia_macd(ctx)]
    # Il resto del file contiene le strategie e funzioni di scoring originali.
    return risultati
