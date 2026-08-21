"""
Motore segnali crypto — architettura modulare.

Ogni strategia è una funzione indipendente ("modulo") che riceve i dati
di mercato già calcolati e restituisce un voto: LONG, SHORT o NEUTRO,
più una spiegazione testuale.

Il campo "attivo" di ogni modulo decide se il suo voto può generare
un vero alert su Telegram (True) oppure se lavora solo "in ombra":
calcola e scrive il risultato nei log di GitHub Actions, ma non manda
nessun messaggio (False) — utile per osservare un nuovo modulo per
qualche giorno prima di fidarsi del suo voto.

Al momento c'è un solo modulo attivo (EMA cross + RSI + candela di
conferma + filtro di trend), identico alla versione precedente:
il comportamento visibile del bot non cambia rispetto a prima.
I moduli successivi (MACD, Bollinger, struttura del trend, S/R,
Wyckoff-lite) verranno aggiunti qui uno alla volta, partendo tutti
in modalità "in ombra".
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
PAIR = os.environ.get("PAIR", "XBTUSD")
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

        # indice dell'ultima candela CHIUSA (l'ultima potrebbe essere in formazione)
        self.i = len(candele) - 2

    def abbastanza_dati(self) -> bool:
        return len(self.chiusure) >= 65  # margine oltre EMA50 + RSI14 + MACD + Bollinger


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


# Elenco dei moduli attualmente registrati.
MODULI_STRATEGIA = [
    strategia_ema_rsi_conferma,
    strategia_macd,
    strategia_bollinger,
    strategia_struttura_trend,
    strategia_supporti_resistenze,
    strategia_wyckoff_lite,
]


# ============================================================
# INVIO TELEGRAM
# ============================================================

def invia_telegram(testo: str) -> None:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        log.error("TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID non impostati, salto invio.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": testo, "parse_mode": "HTML"}
    r = requests.post(url, json=payload, timeout=10)
    if not r.ok:
        log.error("Errore invio Telegram: %s", r.text)


# ============================================================
# MAIN
# ============================================================

def main():
    if MODALITA_TEST:
        invia_telegram(
            "🧪 <b>Messaggio di TEST</b>\n"
            "Se leggi questo, il collegamento GitHub Actions -> Telegram funziona.\n"
            f"Coppia configurata: {PAIR}, Timeframe: {INTERVAL_MIN}m"
        )
        log.info("Messaggio di test inviato.")
        return

    candele = scarica_candele_ohlc(PAIR, INTERVAL_MIN)
    ctx = ContestoMercato(candele)

    if not ctx.abbastanza_dati():
        log.warning("Non abbastanza dati per calcolare i segnali.")
        return

    prezzo = ctx.chiusure[ctx.i]
    log.info(
        "=== %s | prezzo=%.5f EMA9=%.5f EMA21=%.5f EMA50=%.5f RSI=%.1f ===",
        PAIR, prezzo, ctx.ema9[ctx.i], ctx.ema21[ctx.i], ctx.ema50[ctx.i], ctx.rsi14[ctx.i],
    )

    for modulo in MODULI_STRATEGIA:
        risultato = modulo(ctx)
        etichetta_modalita = "ATTIVO" if risultato["attivo"] else "in ombra (non manda alert)"
        log.info(
            "Modulo [%s] (%s) -> voto=%s | motivo: %s",
            risultato["nome"], etichetta_modalita, risultato["voto"], risultato["motivo"],
        )

        if risultato["attivo"] and risultato["voto"] != "NEUTRO":
            emoji = "🟢" if risultato["voto"] == "LONG" else "🔴"
            invia_telegram(
                f"{emoji} <b>Segnale {risultato['voto']}</b>\n"
                f"Coppia: <b>{PAIR}</b> (Kraken)\n"
                f"Prezzo: {prezzo:.5f}\n"
                f"RSI: {ctx.rsi14[ctx.i]:.1f}\n"
                f"Modulo: {risultato['nome']}\n"
                f"Motivo: {risultato['motivo']}\n"
                f"Timeframe: {INTERVAL_MIN}m"
            )


if __name__ == "__main__":
    main()
