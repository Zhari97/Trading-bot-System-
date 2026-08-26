"""Motore centrale del bot crypto.

Contiene acquisizione dati, indicatori, strategie e scoring condivisi da
GitHub Actions e dal server Telegram. Nessun token viene hardcodato.
"""


import os
import logging
import requests

from market_data_manager import GLOBAL_MARKET_CACHE, cache_key

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

def scarica_candele_ohlc(pair: str, interval_min: int):
    """Restituisce una lista di dict con open/high/low/close per ogni candela.

    Il Market Data Manager riutilizza lo snapshot finché non cambia la candela
    chiusa più recente. Il provider Kraken resta invariato e non conosce la
    cache: questo mantiene separati dati, strategia e infrastruttura.
    """
    key = cache_key("kraken", pair, interval_min)

    def _fetch():
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

    now = GLOBAL_MARKET_CACHE._clock()
    cached_before = GLOBAL_MARKET_CACHE.get(key, now, interval_min * 60)
    candele = GLOBAL_MARKET_CACHE.get_or_fetch(
        key,
        interval_min * 60,
        _fetch,
    )
    if cached_before is None:
        log.info("MarketData cache MISS/FETCH | %s | %sm", pair, interval_min)
    else:
        log.info("MarketData cache HIT | %s | %sm", pair, interval_min)
    return candele


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
    IN OMBRA per ora: calcola e scrive il voto nei log, ma non manda
    alert su Telegram. Serve a osservare come si comporta prima di
    attivarlo davvero."""
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

    return {
        "nome": "MACD crossover",
        "voto": voto,
        "motivo": motivo,
        "attivo": False,
    }


def strategia_bollinger(ctx: ContestoMercato) -> dict:
    """Bollinger Bands: ricerca rientro da banda estrema con conferma candela.
    IN OMBRA per ora."""
    i = ctx.i
    prezzo = ctx.chiusure[i]
    sopra = ctx.bb_superiore[i]
    sotto = ctx.bb_inferiore[i]

    if prezzo < sotto and conferma_rialzista(ctx.candele, i):
        voto, motivo = "LONG", "Prezzo sotto BB inferiore + conferma rialzista"
    elif prezzo > sopra and conferma_ribassista(ctx.candele, i):
        voto, motivo = "SHORT", "Prezzo sopra BB superiore + conferma ribassista"
    else:
        voto, motivo = "NEUTRO", "Nessun rientro da banda BB confermato"

    return {
        "nome": "Bollinger Bands",
        "voto": voto,
        "motivo": motivo,
        "attivo": False,
    }


def strategia_ichimoku(ctx: ContestoMercato) -> dict:
    """Ichimoku semplificato: posizione prezzo rispetto alla nuvola + Tenkan/Kijun.
    IN OMBRA per ora."""
    i = ctx.i
    prezzo = ctx.chiusure[i]
    cloud_top = max(ctx.senkou_a[i], ctx.senkou_b[i])
    cloud_bottom = min(ctx.senkou_a[i], ctx.senkou_b[i])

    if prezzo > cloud_top and ctx.tenkan[i] > ctx.kijun[i]:
        voto, motivo = "LONG", "Prezzo sopra Kumo + Tenkan > Kijun"
    elif prezzo < cloud_bottom and ctx.tenkan[i] < ctx.kijun[i]:
        voto, motivo = "SHORT", "Prezzo sotto Kumo + Tenkan < Kijun"
    else:
        voto, motivo = "NEUTRO", "Prezzo nella/contro la Kumo o Tenkan/Kijun non confermati"

    return {
        "nome": "Ichimoku semplificato",
        "voto": voto,
        "motivo": motivo,
        "attivo": False,
    }


def strategia_fibonacci(ctx: ContestoMercato) -> dict:
    """Fibonacci: verifica reazione del prezzo su livelli 38.2/50/61.8% dello swing recente.
    IN OMBRA per ora."""
    i = ctx.i
    swing = trova_swing_high_low(ctx.candele, i, 50)
    massimo = swing["massimo"]
    minimo = swing["minimo"]
    prezzo = ctx.chiusure[i]

    if massimo <= minimo:
        return {
            "nome": "Fibonacci retracement",
            "voto": "NEUTRO",
            "motivo": "Swing non valido",
            "attivo": False,
        }

    livelli = {
        "38.2": minimo + (massimo - minimo) * 0.382,
        "50": minimo + (massimo - minimo) * 0.5,
        "61.8": minimo + (massimo - minimo) * 0.618,
    }
    tolleranza = (massimo - minimo) * 0.01

    vicino = [nome for nome, livello in livelli.items() if abs(prezzo - livello) <= tolleranza]
    if vicino and prezzo < massimo:
        voto, motivo = "LONG", f"Reazione vicino a Fibonacci {', '.join(vicino)}"
    elif vicino and prezzo > minimo:
        voto, motivo = "SHORT", f"Reazione vicino a Fibonacci {', '.join(vicino)}"
    else:
        voto, motivo = "NEUTRO", "Nessuna reazione chiara sui livelli Fibonacci"

    return {
        "nome": "Fibonacci retracement",
        "voto": voto,
        "motivo": motivo,
        "attivo": False,
    }


def strategia_price_action(ctx: ContestoMercato) -> dict:
    """Price Action: pattern engulfing/pin bar + direzione della candela precedente.
    IN OMBRA per ora."""
    i = ctx.i
    candela = ctx.candele[i]

    if conferma_rialzista(ctx.candele, i):
        voto, motivo = "LONG", "Pattern candlestick rialzista confermato"
    elif conferma_ribassista(ctx.candele, i):
        voto, motivo = "SHORT", "Pattern candlestick ribassista confermato"
    else:
        voto, motivo = "NEUTRO", "Nessun pattern Price Action confermato"

    return {
        "nome": "Price Action",
        "voto": voto,
        "motivo": motivo,
        "attivo": False,
    }


def strategia_volatilita_atr(ctx: ContestoMercato) -> dict:
    """Filtro ATR: non è una direzione autonoma, ma segnala se la volatilità
    è sufficiente per considerare valido il contesto. IN OMBRA."""
    i = ctx.i
    atr = ctx.atr14[i]
    prezzo = ctx.chiusure[i]
    rapporto = (atr / prezzo) if prezzo else 0

    if rapporto >= 0.005:
        voto, motivo = "NEUTRO", f"Volatilità sufficiente (ATR/prezzo {rapporto * 100:.2f}%)"
    else:
        voto, motivo = "NEUTRO", f"Volatilità bassa (ATR/prezzo {rapporto * 100:.2f}%)"

    return {
        "nome": "ATR volatilità",
        "voto": voto,
        "motivo": motivo,
        "attivo": False,
    }


def tutte_le_strategie(ctx: ContestoMercato) -> list:
    return [
        strategia_ema_rsi_conferma(ctx),
        strategia_macd(ctx),
        strategia_bollinger(ctx),
        strategia_ichimoku(ctx),
        strategia_fibonacci(ctx),
        strategia_price_action(ctx),
        strategia_volatilita_atr(ctx),
    ]


def calcola_categorie(risultati: list) -> dict:
    """Converte i voti dei moduli in tre categorie operative indipendenti.

    TREND: EMA/RSI attivo + Ichimoku + prezzo rispetto EMA50.
    MOMENTUM: MACD + RSI.
    SETUP: Price Action + Bollinger + Fibonacci.
    I moduli IN OMBRA continuano a contribuire alle categorie, ma non
    possono da soli generare alert Telegram.
    """
    pesi = {
        "EMA9/21 + RSI + conferma": 0.45,
        "MACD crossover": 0.20,
        "Bollinger Bands": 0.15,
        "Ichimoku semplificato": 0.15,
        "Fibonacci retracement": 0.10,
        "Price Action": 0.10,
        "ATR volatilità": 0.05,
    }

    long = short = totale = 0.0
    for risultato in risultati:
        peso = pesi.get(risultato["nome"], 0.0)
        totale += peso
        if risultato["voto"] == "LONG":
            long += peso
        elif risultato["voto"] == "SHORT":
            short += peso

    trend_long = trend_short = 0.0
    if risultati[0]["voto"] == "LONG":
        trend_long += 0.45
    elif risultati[0]["voto"] == "SHORT":
        trend_short += 0.45
    if risultati[3]["voto"] == "LONG":
        trend_long += 0.15
    elif risultati[3]["voto"] == "SHORT":
        trend_short += 0.15

    momentum_long = momentum_short = 0.0
    if risultati[1]["voto"] == "LONG":
        momentum_long += 0.20
    elif risultati[1]["voto"] == "SHORT":
        momentum_short += 0.20

    setup_long = setup_short = 0.0
    for idx in (2, 4, 5):
        if risultati[idx]["voto"] == "LONG":
            setup_long += pesi[risultati[idx]["nome"]]
        elif risultati[idx]["voto"] == "SHORT":
            setup_short += pesi[risultati[idx]["nome"]]

    def score_categoria(long_value, short_value, peso_categoria):
        denom = long_value + short_value
        if denom <= 0:
            return 50.0
        return 50.0 + ((long_value - short_value) / denom) * 50.0

    trend_score = score_categoria(trend_long, trend_short, 0.45)
    momentum_score = score_categoria(momentum_long, momentum_short, 0.20)
    setup_score = score_categoria(setup_long, setup_short, 0.35)

    score = trend_score * 0.45 + momentum_score * 0.20 + setup_score * 0.35

    return {
        "trend": trend_score,
        "momentum": momentum_score,
        "setup": setup_score,
        "peso_long": long,
        "peso_short": short,
        "score": score,
        "totale_pesi": totale,
    }


def determina_direzione(risultati: list) -> tuple[str, float, bool]:
    pesi = {
        "EMA9/21 + RSI + conferma": 0.45,
        "MACD crossover": 0.20,
        "Bollinger Bands": 0.15,
        "Ichimoku semplificato": 0.15,
        "Fibonacci retracement": 0.10,
        "Price Action": 0.10,
        "ATR volatilità": 0.05,
    }
    long = sum(pesi.get(r["nome"], 0) for r in risultati if r["voto"] == "LONG")
    short = sum(pesi.get(r["nome"], 0) for r in risultati if r["voto"] == "SHORT")
    totale = long + short
    if totale == 0:
        return "NEUTRO", 0.0, False
    if long > short:
        return "LONG", (long / totale) * 100, long > 0 and short > 0
    if short > long:
        return "SHORT", (short / totale) * 100, long > 0 and short > 0
    return "NEUTRO", 50.0, True


def classifica_segnale(categorie: dict, risultati: list) -> dict:
    """Classificazione V2.2.

    Livelli:
      FORTE     = confluente, trend+setup allineati, momentum coerente
      SETUP     = setup valido ma non ancora forte
      WATCH     = direzione interessante ma manca conferma
      NO TRADE  = neutro o conflitto
    """
    trend = categorie["trend"]
    momentum = categorie["momentum"]
    setup = categorie["setup"]
    score = categorie["score"]
    direzione, confluenza, conflitto = determina_direzione(risultati)

    trend_dir = "LONG" if trend > 55 else "SHORT" if trend < 45 else "NEUTRO"
    setup_dir = "LONG" if setup > 55 else "SHORT" if setup < 45 else "NEUTRO"
    momentum_dir = "LONG" if momentum > 55 else "SHORT" if momentum < 45 else "NEUTRO"

    if direzione == "LONG":
        if trend_dir == "LONG" and setup_dir == "LONG" and momentum_dir == "LONG" and score >= 70 and confluenza >= 70:
            livello = "FORTE"
            motivo = "Trend + Setup + Momentum allineati con confluenza alta."
        elif trend_dir == "LONG" and setup_dir == "LONG" and score >= 60:
            livello = "SETUP"
            motivo = "Trend e Setup confermati, manca piena conferma Momentum."
        elif trend_dir == "LONG" or setup_dir == "LONG":
            livello = "WATCH"
            motivo = "Bias LONG interessante ma conferma incompleta."
        else:
            livello = "NO TRADE"
            motivo = "Nessuna struttura LONG sufficientemente coerente."
    elif direzione == "SHORT":
        if trend_dir == "SHORT" and setup_dir == "SHORT" and momentum_dir == "SHORT" and score <= 30 and confluenza >= 70:
            livello = "FORTE"
            motivo = "Trend + Setup + Momentum allineati con confluenza alta."
        elif trend_dir == "SHORT" and setup_dir == "SHORT" and score <= 40:
            livello = "SETUP"
            motivo = "Trend e Setup confermati, manca piena conferma Momentum."
        elif trend_dir == "SHORT" or setup_dir == "SHORT":
            livello = "WATCH"
            motivo = "Bias SHORT interessante ma conferma incompleta."
        else:
            livello = "NO TRADE"
            motivo = "Nessuna struttura SHORT sufficientemente coerente."
    else:
        livello = "NO TRADE"
        motivo = "Mercato neutro o senza direzione dominante."

    controtrend = (
        (direzione == "LONG" and trend_dir == "SHORT")
        or (direzione == "SHORT" and trend_dir == "LONG")
    )

    if controtrend:
        livello = "WATCH"
        motivo = "Direzione contro il trend principale: si osserva, non si forza l'alert."

    return {
        "livello": livello,
        "direzione": direzione,
        "confluenza": confluenza,
        "controtrend": controtrend,
        "motivo": motivo,
        "trend_direzione": trend_dir,
        "setup_direzione": setup_dir,
        "momentum_direzione": momentum_dir,
        "alert_automatico": livello == "FORTE",
    }


def analizza_coppia(pair: str):
    candele = scarica_candele_ohlc(pair, INTERVAL_MIN)
    ctx = ContestoMercato(candele)
    if not ctx.abbastanza_dati():
        raise RuntimeError(f"Dati insufficienti per {pair}")

    risultati = tutte_le_strategie(ctx)
    categorie = calcola_categorie(risultati)
    classificazione = classifica_segnale(categorie, risultati)
    direzione_dominante, confluenza, conflitto = determina_direzione(risultati)

    return {
        "pair": pair,
        "prezzo": ctx.chiusure[ctx.i],
        "ctx": ctx,
        "risultati": risultati,
        "categorie": categorie,
        "classificazione": classificazione,
        "direzione_dominante": direzione_dominante,
        "confluenza": confluenza,
        "conflitto": conflitto,
        "peso_long": categorie["peso_long"],
        "peso_short": categorie["peso_short"],
        "score": categorie["score"],
        "bias": "LONG" if categorie["score"] > 50 else "SHORT" if categorie["score"] < 50 else "NEUTRO",
    }


def formato_score_telegram(analisi: dict) -> str:
    """Formato compatto legacy per compatibilità con eventuali consumer."""
    score = analisi["score"]
    return f"Score direzionale: {score:.1f}/100 (50 = neutro)"


def classificazione_v2_2_valida(classificazione: dict) -> tuple[bool, str]:
    """Guard-rail centrale: una classificazione V2.2 incoerente non può generare alert."""
    livello = classificazione.get("livello", "WATCH")
    direzione = classificazione.get("direzione", "NEUTRO")
    trend_dir = classificazione.get("trend_direzione", "NEUTRO")
    setup_dir = classificazione.get("setup_direzione", "NEUTRO")
    momentum_dir = classificazione.get("momentum_direzione", "NEUTRO")
    alert_automatico = bool(classificazione.get("alert_automatico"))

    if livello == "SETUP" and (trend_dir == "NEUTRO" or setup_dir == "NEUTRO"):
        return False, "SETUP con Trend/Setup neutro"
    if livello == "SETUP" and trend_dir != setup_dir:
        return False, "SETUP con Trend/Setup discordanti"
    if livello == "FORTE":
        if direzione not in ("LONG", "SHORT"):
            return False, "FORTE senza direzione operativa"
        if trend_dir != direzione or setup_dir != direzione:
            return False, "FORTE con Trend/Setup discordanti"
        if momentum_dir != direzione:
            return False, "FORTE con Momentum discordante"
        if not alert_automatico:
            return False, "FORTE senza alert_automatico"
    return True, "OK"
