"""Definizione dell'universo strumenti del Trading System.

Questa prima versione separa la scoperta degli strumenti dalla logica di
segnale. Crypto viene scoperta dinamicamente (Top N per market cap,
stablecoin escluse) e mappata su coppie disponibili su Kraken.

Indici, metalli e forex sono definiti come universo preparatorio: in questa
fase NON vengono ancora passati al signal engine, così il comportamento degli
alert esistenti resta invariato.
"""

from __future__ import annotations

import logging
import os
from typing import Iterable

import requests

log = logging.getLogger("market_universe")

COINGECKO_MARKETS_URL = "https://api.coingecko.com/api/v3/coins/markets"
KRAKEN_ASSET_PAIRS_URL = "https://api.kraken.com/0/public/AssetPairs"

DEFAULT_CRYPTO_PAIRS = ["XBTUSD", "ETHUSD", "SOLUSD"]
CRYPTO_TOP_N = max(1, int(os.environ.get("CRYPTO_TOP_N", "10")))
DYNAMIC_CRYPTO_UNIVERSE = os.environ.get("DYNAMIC_CRYPTO_UNIVERSE", "1") == "1"

STABLECOIN_SYMBOLS = {
    "usdt", "usdc", "usde", "dai", "usds", "fdusd", "usdd", "tusd",
    "usdp", "pyusd", "frax", "lusd", "crvusd", "susd", "gusd", "eurc",
}

# Alias necessari per allineare i simboli CoinGecko con quelli usati da Kraken.
KRAKEN_BASE_ALIASES = {
    "btc": "xbt",
    "doge": "xdg",
}

# Universo preparatorio: non attivato dal signal engine in questa fase.
INDEX_INSTRUMENTS = [
    {"nome": "SPX", "mercato": "index", "provider_symbol": "SPX"},
    {"nome": "NDX", "mercato": "index", "provider_symbol": "NDX"},
    {"nome": "DJI", "mercato": "index", "provider_symbol": "DJI"},
    {"nome": "DAX", "mercato": "index", "provider_symbol": "DAX"},
    {"nome": "FTSE", "mercato": "index", "provider_symbol": "FTSE"},
    {"nome": "NIKKEI", "mercato": "index", "provider_symbol": "NIKKEI"},
    {"nome": "CAC", "mercato": "index", "provider_symbol": "CAC"},
    {"nome": "STOXX50", "mercato": "index", "provider_symbol": "STOXX50"},
]

METAL_INSTRUMENTS = [
    {"nome": "XAU/USD", "mercato": "metal", "provider_symbol": "XAU/USD"},
    {"nome": "XAG/USD", "mercato": "metal", "provider_symbol": "XAG/USD"},
    {"nome": "XPT/USD", "mercato": "metal", "provider_symbol": "XPT/USD"},
    {"nome": "XPD/USD", "mercato": "metal", "provider_symbol": "XPD/USD"},
]

FOREX_INSTRUMENTS = [
    {"nome": "EUR/USD", "mercato": "forex", "provider_symbol": "EUR/USD"},
    {"nome": "GBP/USD", "mercato": "forex", "provider_symbol": "GBP/USD"},
    {"nome": "USD/JPY", "mercato": "forex", "provider_symbol": "USD/JPY"},
    {"nome": "USD/CHF", "mercato": "forex", "provider_symbol": "USD/CHF"},
    {"nome": "AUD/USD", "mercato": "forex", "provider_symbol": "AUD/USD"},
    {"nome": "USD/CAD", "mercato": "forex", "provider_symbol": "USD/CAD"},
    {"nome": "NZD/USD", "mercato": "forex", "provider_symbol": "NZD/USD"},
    {"nome": "EUR/GBP", "mercato": "forex", "provider_symbol": "EUR/GBP"},
    {"nome": "EUR/JPY", "mercato": "forex", "provider_symbol": "EUR/JPY"},
    {"nome": "GBP/JPY", "mercato": "forex", "provider_symbol": "GBP/JPY"},
    {"nome": "EUR/CHF", "mercato": "forex", "provider_symbol": "EUR/CHF"},
    {"nome": "GBP/CHF", "mercato": "forex", "provider_symbol": "GBP/CHF"},
    {"nome": "AUD/JPY", "mercato": "forex", "provider_symbol": "AUD/JPY"},
    {"nome": "CAD/JPY", "mercato": "forex", "provider_symbol": "CAD/JPY"},
    {"nome": "NZD/JPY", "mercato": "forex", "provider_symbol": "NZD/JPY"},
]


def _normalized_base(value: str) -> str:
    value = value.lower().strip()
    value = value.replace("/", "")
    if value.startswith(("x", "z")) and len(value) > 3:
        value = value[1:]
    return value


def _kraken_alias(symbol: str) -> str:
    symbol = symbol.lower().strip()
    return KRAKEN_BASE_ALIASES.get(symbol, symbol)


def _fetch_kraken_usd_pairs(timeout: int = 10) -> dict[str, str]:
    """Restituisce {base_normalizzato: altname} per coppie USD attive."""
    response = requests.get(KRAKEN_ASSET_PAIRS_URL, timeout=timeout)
    response.raise_for_status()
    payload = response.json()
    if payload.get("error"):
        raise RuntimeError(f"Errore API Kraken AssetPairs: {payload['error']}")

    pairs: dict[str, str] = {}
    for key, item in payload.get("result", {}).items():
        if not isinstance(item, dict):
            continue
        altname = str(item.get("altname") or key).upper()
        quote = str(item.get("quote") or "").upper()
        status = str(item.get("status") or "online").lower()
        if status not in {"online", ""}:
            continue
        if not altname.endswith("USD") and quote not in {"ZUSD", "USD"}:
            continue
        base = str(item.get("base") or "")
        if not base:
            continue
        pairs[_normalized_base(base)] = altname
    return pairs


def _fetch_top_crypto_symbols(limit: int, timeout: int = 10) -> list[str]:
    params = {
        "vs_currency": "usd",
        "order": "market_cap_desc",
        "per_page": max(30, limit * 3),
        "page": 1,
        "sparkline": "false",
    }
    response = requests.get(COINGECKO_MARKETS_URL, params=params, timeout=timeout)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, list):
        raise RuntimeError("Risposta CoinGecko non valida")

    symbols: list[str] = []
    for coin in payload:
        symbol = str(coin.get("symbol") or "").lower().strip()
        if not symbol or symbol in STABLECOIN_SYMBOLS:
            continue
        if symbol not in symbols:
            symbols.append(symbol)
        if len(symbols) >= limit:
            break
    return symbols


def discover_crypto_pairs(
    limit: int = CRYPTO_TOP_N,
    fallback: Iterable[str] = DEFAULT_CRYPTO_PAIRS,
) -> list[str]:
    """Scopre le top crypto non-stable e le mappa su Kraken.

    In caso di errore di rete/rate limit restituisce il fallback, evitando di
    bloccare il bot. Un eventuale override esplicito PAIRS continua ad avere
    priorita' sul discovery dinamico.
    """
    fallback_list = [str(x).strip().upper() for x in fallback if str(x).strip()]
    if not DYNAMIC_CRYPTO_UNIVERSE:
        return fallback_list

    try:
        symbols = _fetch_top_crypto_symbols(limit)
        kraken_pairs = _fetch_kraken_usd_pairs()
        result: list[str] = []
        for symbol in symbols:
            base = _kraken_alias(symbol)
            pair = kraken_pairs.get(_normalized_base(base))
            if pair and pair not in result:
                result.append(pair)
            if len(result) >= limit:
                break

        if not result:
            raise RuntimeError("nessuna top crypto disponibile su Kraken")

        log.info("Universo crypto dinamico: %s", ", ".join(result))
        return result
    except Exception as exc:
        log.warning(
            "Discovery crypto dinamico non disponibile (%s): uso fallback %s",
            exc,
            ", ".join(fallback_list),
        )
        return fallback_list


def build_prepared_universe(crypto_pairs: Iterable[str]) -> list[dict]:
    """Costruisce l'universo completo preparato per le prossime fasi."""
    crypto = [
        {"nome": pair, "mercato": "crypto", "provider_symbol": pair}
        for pair in crypto_pairs
    ]
    return crypto + INDEX_INSTRUMENTS + METAL_INSTRUMENTS + FOREX_INSTRUMENTS
