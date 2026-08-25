"""Motore centrale del bot crypto.

Contiene acquisizione dati, indicatori, strategie e scoring condivisi da
GitHub Actions e dal server Telegram. Nessun token viene hardcodato.
"""


import os
import logging
import requests

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
    """Restituisce una lista di dict con open/high/low/close per ogni candela."""
    params = {"pair": pair, "interval": interval_min}
    r = requests.get(KRAKEN_OHLC_URL, params=params, timeout=15)
    r.raise_for_status()
    dati = r.json()
    if dati.get("error"):
        raise RuntimeError(f"Errore API Kraken: {dati['error']}")
    risultato = dati["result"]
    chiave_coppia = next(k for k in risultato.keys() if k != "last")
    candele_raw = risultato[chiave_coppia]
    candele = [
        {
            "open": float(c[1]),
            "high": float(c[2]),
            "low": float(c[3]),
            "close": float(c[4]),
            "volume": float(c[6]),
        }
        for c in candele_raw
    ]
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
        "attivo": True,  # <-- questo modulo può generare alert reali
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

    # Conferma leggera: l'istogramma deve essere coerente con la direzione
    # (cioè si sta already muovendo nella stessa direzione dell'incrocio)
    istogramma_in_crescita = ctx.macd_istogramma[i] > ctx.macd_istogramma[i - 1]
    istogramma_in_calo = ctx.macd_istogramma[i] < ctx.macd_istogramma[i - 1]

    if incrocio_rialzista and istogramma_in_crescita:
        voto, motivo = "LONG", "MACD incrocia sopra la linea segnale, istogramma in crescita"
    elif incrocio_ribassista and istogramma_in_calo:
        voto, motivo = "SHORT", "MACD incrocia sotto la linea segnale, istogramma in calo"
    else:
        voto, motivo = "NEUTRO", "Nessun incrocio MACD rilevante"

    return {
        "nome": "MACD 12/26/9",
        "voto": voto,
        "motivo": motivo,
        "attivo": False,  # <-- in ombra: solo log, nessun alert Telegram
    }


def strategia_bollinger(ctx: ContestoMercato) -> dict:
    """Modulo Bollinger Bands: mean reversion. Se il minimo della candela
    tocca/supera la banda inferiore ma la chiusura rientra dentro le bande,
    è un possibile rimbalzo verso l'alto (LONG). Speculare per SHORT.
    IN OMBRA per ora."""
    i = ctx.i
    c = ctx.candele[i]

    tocco_inferiore = c["low"] <= ctx.bb_inferiore[i]
    chiusura_rientrata_su = c["close"] > ctx.bb_inferiore[i]

    tocco_superiore = c["high"] >= ctx.bb_superiore[i]
    chiusura_rientrata_giu = c["close"] < ctx.bb_superiore[i]

    if tocco_inferiore and chiusura_rientrata_su:
        voto, motivo = "LONG", "Prezzo ha toccato la banda inferiore ed è rientrato (mean reversion)"
    elif tocco_superiore and chiusura_rientrata_giu:
        voto, motivo = "SHORT", "Prezzo ha toccato la banda superiore ed è rientrato (mean reversion)"
    else:
        voto, motivo = "NEUTRO", "Nessun tocco/rientro sulle bande"

    return {"nome": "Bollinger Bands 20,2", "voto": voto, "motivo": motivo, "attivo": False}


def strategia_struttura_trend(ctx: ContestoMercato) -> dict:
    """Modulo struttura del trend: confronta massimi e minimi tra le
    ultime 10 candele chiuse e le 10 precedenti. Massimi e minimi
    entrambi crescenti = struttura rialzista (higher highs/higher lows);
    entrambi calanti = struttura ribassista. Approssimazione semplice
    della price action classica. IN OMBRA per ora."""
    i = ctx.i
    finestra = 10
    if i - (2 * finestra) < 0:
        return {"nome": "Struttura trend (HH/HL)", "voto": "NEUTRO",
                "motivo": "Dati insufficienti per la finestra scelta", "attivo": False}

    recenti = ctx.candele[i - finestra + 1: i + 1]
    precedenti = ctx.candele[i - 2 * finestra + 1: i - finestra + 1]

    max_recente = max(c["high"] for c in recenti)
    max_precedente = max(c["high"] for c in precedenti)
    min_recente = min(c["low"] for c in recenti)
    min_precedente = min(c["low"] for c in precedenti)

    struttura_rialzista = max_recente > max_precedente and min_recente > min_precedente
    struttura_ribassista = max_recente < max_precedente and min_recente < min_precedente

    if struttura_rialzista:
        voto, motivo = "LONG", "Massimi e minimi crescenti (higher highs / higher lows)"
    elif struttura_ribassista:
        voto, motivo = "SHORT", "Massimi e minimi calanti (lower highs / lower lows)"
    else:
        voto, motivo = "NEUTRO", "Struttura non chiaramente direzionale"

    return {"nome": "Struttura trend (HH/HL)", "voto": voto, "motivo": motivo, "attivo": False}


def strategia_supporti_resistenze(ctx: ContestoMercato) -> dict:
    """Modulo rottura supporti/resistenze: se la chiusura attuale
    supera il massimo delle ultime N candele precedenti (escludendola),
    è una rottura di resistenza (LONG). Speculare per il supporto (SHORT).
    IN OMBRA per ora."""
    i = ctx.i
    finestra = 20
    if i - finestra < 0:
        return {"nome": "Rottura S/R", "voto": "NEUTRO",
                "motivo": "Dati insufficienti per la finestra scelta", "attivo": False}

    precedenti = ctx.candele[i - finestra: i]
    resistenza = max(c["high"] for c in precedenti)
    supporto = min(c["low"] for c in precedenti)
    chiusura = ctx.candele[i]["close"]

    if chiusura > resistenza:
        voto, motivo = "LONG", f"Rottura sopra la resistenza delle ultime {finestra} candele"
    elif chiusura < supporto:
        voto, motivo = "SHORT", f"Rottura sotto il supporto delle ultime {finestra} candele"
    else:
        voto, motivo = "NEUTRO", "Prezzo ancora dentro il range recente"

    return {"nome": "Rottura S/R", "voto": voto, "motivo": motivo, "attivo": False}


def strategia_wyckoff_lite(ctx: ContestoMercato) -> dict:
    """Modulo Wyckoff-lite — APPROSSIMAZIONE dichiarata, non il vero
    metodo Wyckoff (che richiede lettura discrezionale su più timeframe).
    Cerca: range laterale stretto (compressione) nelle candele precedenti
    + rottura recente accompagnata da volume sopra la media = possibile
    "spring" (falso movimento ribassista poi ripresa, LONG) o "upthrust"
    (falso movimento rialzista poi ripresa, SHORT). Voto SEMPRE più debole
    degli altri moduli. IN OMBRA per ora."""
    i = ctx.i
    finestra = 15
    if i - finestra - 1 < 0:
        return {"nome": "Wyckoff-lite (approssimato)", "voto": "NEUTRO",
                "motivo": "Dati insufficienti", "attivo": False}

    range_precedente = ctx.candele[i - finestra: i]
    ampiezza_media = sum(c["high"] - c["low"] for c in range_precedente) / finestra
    volumi = [c["volume"] for c in range_precedente]
    volume_medio = sum(volumi) / len(volumi)

    candela_attuale = ctx.candele[i]
    ampiezza_attuale = candela_attuale["high"] - candela_attuale["low"]
    volume_attuale = candela_attuale["volume"]

    range_era_compresso = ampiezza_media > 0 and all(
        (c["high"] - c["low"]) < ampiezza_media * 1.3 for c in range_precedente[-5:]
    )
    rottura_con_volume = volume_attuale > volume_medio * 1.5 and ampiezza_attuale > ampiezza_media

    minimo_range = min(c["low"] for c in range_precedente)
    massimo_range = max(c["high"] for c in range_precedente)

    spring = (
        range_era_compresso and rottura_con_volume
        and candela_attuale["low"] < minimo_range
        and candela_attuale["close"] > minimo_range
    )
    upthrust = (
        range_era_compresso and rottura_con_volume
        and candela_attuale["high"] > massimo_range
        and candela_attuale["close"] < massimo_range
    )

    if spring:
        voto, motivo = "LONG", "Possibile 'spring' (falso breakdown + volume + rientro) — approssimato"
    elif upthrust:
        voto, motivo = "SHORT", "Possibile 'upthrust' (falso breakout + volume + rientro) — approssimato"
    else:
        voto, motivo = "NEUTRO", "Nessun pattern spring/upthrust rilevato"

    return {"nome": "Wyckoff-lite (approssimato)", "voto": voto, "motivo": motivo, "attivo": False}


def strategia_atr_breakout(ctx: ContestoMercato) -> dict:
    """Modulo ATR Breakout: rileva candele con range anomalo rispetto
    alla volatilita recente (movimento 'esplosivo'), con chiusura decisa
    vicino a un estremo della candela. Diverso dagli altri moduli perche
    non guarda la direzione media, ma l'ampiezza del movimento. IN OMBRA."""
    i = ctx.i
    c = ctx.candele[i]
    range_candela = c["high"] - c["low"]
    if range_candela <= 0 or ctx.atr14[i] <= 0:
        return {"nome": "ATR Breakout", "voto": "NEUTRO", "motivo": "Dati insufficienti", "attivo": False}

    range_anomalo = range_candela > ctx.atr14[i] * 1.5
    posizione_chiusura = (c["close"] - c["low"]) / range_candela  # 0=minimo, 1=massimo

    if range_anomalo and posizione_chiusura > 0.7 and is_rialzista(c):
        voto, motivo = "LONG", "Candela con range anomalo, chiusura vicina al massimo"
    elif range_anomalo and posizione_chiusura < 0.3 and is_ribassista(c):
        voto, motivo = "SHORT", "Candela con range anomalo, chiusura vicina al minimo"
    else:
        voto, motivo = "NEUTRO", "Nessun breakout di volatilita rilevante"

    return {"nome": "ATR Breakout", "voto": voto, "motivo": motivo, "attivo": False}


def strategia_fibonacci(ctx: ContestoMercato) -> dict:
    """Modulo Fibonacci Retracement: individua l'ultimo swing high/low
    (50 candele), calcola i livelli 50%/61.8% e controlla se il prezzo
    sta rimbalzando li con una candela di conferma. IN OMBRA."""
    i = ctx.i
    if i < 51:
        return {"nome": "Fibonacci 50/61.8", "voto": "NEUTRO", "motivo": "Dati insufficienti", "attivo": False}

    swing = trova_swing_high_low(ctx.candele, i, lookback=50)
    massimo, minimo = swing["massimo"], swing["minimo"]
    ampiezza = massimo - minimo
    if ampiezza <= 0:
        return {"nome": "Fibonacci 50/61.8", "voto": "NEUTRO", "motivo": "Range piatto", "attivo": False}

    c = ctx.candele[i]
    tolleranza = ampiezza * 0.05  # 5% dell'ampiezza dello swing

    # Se il minimo e' piu recente del massimo: swing ribassista -> livelli di
    # possibile rimbalzo LONG. Altrimenti swing rialzista -> livelli SHORT.
    swing_ribassista = swing["idx_minimo"] > swing["idx_massimo"]

    if swing_ribassista:
        livello_50 = minimo + 0.5 * ampiezza
        livello_618 = minimo + 0.382 * ampiezza  # simmetrico dal basso
        vicino_livello = (abs(c["close"] - livello_50) < tolleranza
                           or abs(c["close"] - livello_618) < tolleranza)
        conferma = conferma_rialzista(ctx.candele, i)
        if vicino_livello and conferma:
            voto, motivo = "LONG", "Rimbalzo su livello Fibonacci 50%/61.8% con conferma"
        else:
            voto, motivo = "NEUTRO", "Nessun rimbalzo confermato sui livelli Fibonacci"
    else:
        livello_50 = massimo - 0.5 * ampiezza
        livello_618 = massimo - 0.382 * ampiezza
        vicino_livello = (abs(c["close"] - livello_50) < tolleranza
                           or abs(c["close"] - livello_618) < tolleranza)
        conferma = conferma_ribassista(ctx.candele, i)
        if vicino_livello and conferma:
            voto, motivo = "SHORT", "Ritracciamento su livello Fibonacci 50%/61.8% con conferma"
        else:
            voto, motivo = "NEUTRO", "Nessun ritracciamento confermato sui livelli Fibonacci"

    return {"nome": "Fibonacci 50/61.8", "voto": voto, "motivo": motivo, "attivo": False}


def strategia_ichimoku(ctx: ContestoMercato) -> dict:
    """Modulo Ichimoku semplificato (APPROSSIMATO: senza il forward-shift
    classico di 26 periodi, per semplicita di calcolo). Guarda se il prezzo
    e' sopra/sotto la 'nuvola' (Senkou A/B) e se Tenkan e' sopra/sotto Kijun.
    IN OMBRA."""
    i = ctx.i
    if i < 52:
        return {"nome": "Ichimoku (approssimato)", "voto": "NEUTRO", "motivo": "Dati insufficienti", "attivo": False}

    prezzo = ctx.chiusure[i]
    nuvola_sup = max(ctx.senkou_a[i], ctx.senkou_b[i])
    nuvola_inf = min(ctx.senkou_a[i], ctx.senkou_b[i])

    sopra_nuvola = prezzo > nuvola_sup
    sotto_nuvola = prezzo < nuvola_inf
    tenkan_su_kijun = ctx.tenkan[i] > ctx.kijun[i]
    tenkan_sotto_kijun = ctx.tenkan[i] < ctx.kijun[i]

    if sopra_nuvola and tenkan_su_kijun:
        voto, motivo = "LONG", "Prezzo sopra la nuvola, Tenkan sopra Kijun"
    elif sotto_nuvola and tenkan_sotto_kijun:
        voto, motivo = "SHORT", "Prezzo sotto la nuvola, Tenkan sotto Kijun"
    else:
        voto, motivo = "NEUTRO", "Prezzo dentro la nuvola o segnali contrastanti"

    return {"nome": "Ichimoku (approssimato)", "voto": voto, "motivo": motivo, "attivo": False}


# Elenco dei moduli attualmente registrati.
MODULI_STRATEGIA = [
    strategia_ema_rsi_conferma,
    strategia_macd,
    strategia_bollinger,
    strategia_struttura_trend,
    strategia_supporti_resistenze,
    strategia_wyckoff_lite,
    strategia_atr_breakout,
    strategia_fibonacci,
    strategia_ichimoku,
]

# ============================================================
# SCORING / CONFLUENZA V2
# ============================================================

# I pesi dei singoli moduli restano a 100 complessivi. Servono a stabilire
# quanto pesa ogni voto dentro la propria categoria.
PESI_MODULI = {
    "EMA9/21 + RSI + conferma": 18,
    "MACD 12/26/9": 12,
    "Bollinger Bands 20,2": 8,
    "Struttura trend (HH/HL)": 15,
    "Rottura S/R": 12,
    "Wyckoff-lite (approssimato)": 8,
    "ATR Breakout": 10,
    "Fibonacci 50/61.8": 7,
    "Ichimoku (approssimato)": 10,
}

# Il punteggio finale non tratta tutti i moduli come equivalenti.
# Prima leggiamo il mercato in tre blocchi: trend, momentum e setup.
PESI_CATEGORIE = {
    "trend": 45,
    "momentum": 20,
    "setup": 35,
}

CATEGORIE_MODULI = {
    "EMA9/21 + RSI + conferma": "trend",
    "MACD 12/26/9": "momentum",
    "Bollinger Bands 20,2": "setup",
    "Struttura trend (HH/HL)": "trend",
    "Rottura S/R": "setup",
    "Wyckoff-lite (approssimato)": "setup",
    "ATR Breakout": "setup",
    "Fibonacci 50/61.8": "setup",
    "Ichimoku (approssimato)": "trend",
}


def _direzione(voto: str) -> int:
    if voto == "LONG":
        return 1
    if voto == "SHORT":
        return -1
    return 0


def calcola_score(risultati):
    """Calcola score V2, categorie e confluenza.

    50 = neutro.
    Le categorie sono pesate Trend 45%, Momentum 20%, Setup 35%.
    Un modulo NEUTRO non aggiunge direzione, ma il suo peso resta nel
    denominatore della categoria: questo rende lo score più conservativo.
    """
    categorie = {}
    peso_long = 0.0
    peso_short = 0.0
    segnali_direzionali = []

    for categoria in PESI_CATEGORIE:
        moduli_categoria = [
            r for r in risultati
            if CATEGORIE_MODULI.get(r["nome"]) == categoria
        ]
        peso_categoria = sum(PESI_MODULI.get(r["nome"], 0) for r in moduli_categoria)
        contributo = sum(
            PESI_MODULI.get(r["nome"], 0) * _direzione(r["voto"])
            for r in moduli_categoria
        )

        if peso_categoria:
            score_categoria = 50 + 50 * (contributo / peso_categoria)
        else:
            score_categoria = 50.0

        score_categoria = round(max(0.0, min(100.0, score_categoria)), 1)
        categorie[categoria] = score_categoria

    for risultato in risultati:
        peso = PESI_MODULI.get(risultato["nome"], 0)
        if risultato["voto"] == "LONG":
            peso_long += peso
            segnali_direzionali.append(risultato)
        elif risultato["voto"] == "SHORT":
            peso_short += peso
            segnali_direzionali.append(risultato)

    score = sum(
        categorie[nome] * (peso / 100)
        for nome, peso in PESI_CATEGORIE.items()
    )
    score = round(max(0.0, min(100.0, score)), 1)

    conflitto = peso_long > 0 and peso_short > 0
    peso_direzionale = peso_long + peso_short

    if peso_direzionale <= 0:
        confluenza = 0.0
        direzione_dominante = "NEUTRO"
    elif peso_long >= peso_short:
        confluenza = round(100 * peso_long / peso_direzionale, 1)
        direzione_dominante = "LONG"
    else:
        confluenza = round(100 * peso_short / peso_direzionale, 1)
        direzione_dominante = "SHORT"

    return {
        "score": score,
        "peso_long": round(peso_long, 1),
        "peso_short": round(peso_short, 1),
        "categorie": categorie,
        "conflitto": conflitto,
        "confluenza": confluenza,
        "direzione_dominante": direzione_dominante,
        "segnali_direzionali": len(segnali_direzionali),
    }


def etichetta_score(score: float) -> str:
    if score >= 80:
        return "LONG FORTE"
    if score >= 60:
        return "LONG"
    if score <= 20:
        return "SHORT FORTE"
    if score <= 40:
        return "SHORT"
    return "NEUTRO"


def etichetta_categoria(score: float) -> str:
    if score >= 65:
        return "RIALZISTA"
    if score <= 35:
        return "RIBASSISTA"
    return "NEUTRALE"


def analizza_coppia(pair: str):
    """Scarica i dati una volta e restituisce analisi + score V2 condivisibili."""
    candele = scarica_candele_ohlc(pair, INTERVAL_MIN)
    ctx = ContestoMercato(candele)
    if not ctx.abbastanza_dati():
        raise RuntimeError(f"[{pair}] dati insufficienti")

    risultati = []
    for modulo in MODULI_STRATEGIA:
        risultato = modulo(ctx)
        risultati.append(risultato)

    scoring = calcola_score(risultati)
    score = scoring["score"]

    return {
        "pair": pair,
        "ctx": ctx,
        "prezzo": ctx.chiusure[ctx.i],
        "rsi": ctx.rsi14[ctx.i],
        "risultati": risultati,
        "score": score,
        "bias": etichetta_score(score),
        **scoring,
    }


def formato_score_telegram(analisi: dict) -> str:
    """Riepilogo compatto V2 pronto per Telegram."""
    categorie = analisi["categorie"]
    conflitto = "⚠️ CONFLITTO" if analisi["conflitto"] else "✅ CONFLUENZA"
    return (
        f"📊 <b>Score {analisi['pair']}</b>\n"
        f"Prezzo: <b>{analisi['prezzo']:.5f}</b>\n"
        f"Score: <b>{analisi['score']:.1f}/100</b> — {analisi['bias']}\n"
        f"Trend: {categorie['trend']:.1f}/100 ({etichetta_categoria(categorie['trend'])})\n"
        f"Momentum: {categorie['momentum']:.1f}/100 ({etichetta_categoria(categorie['momentum'])})\n"
        f"Setup: {categorie['setup']:.1f}/100 ({etichetta_categoria(categorie['setup'])})\n"
        f"Confluenza: {conflitto}\n"
        f"Direzione dominante: {analisi['direzione_dominante']} ({analisi['confluenza']:.1f}%)\n"
        f"RSI: {analisi['rsi']:.1f}\n"
        f"Timeframe: {INTERVAL_MIN}m"
    )
