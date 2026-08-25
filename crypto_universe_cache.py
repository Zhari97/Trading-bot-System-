"""Cache leggero della discovery crypto per GitHub Actions.

Riduce le chiamate a CoinGecko + Kraken: la discovery Top N viene aggiornata
al massimo una volta per CACHE_TTL_SECONDS. Il file e' pensato per essere
persistito con actions/cache nel workflow; se la cache non esiste o e' scaduta,
si torna alla discovery normale con fallback integrato.
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path

from market_universe import DEFAULT_CRYPTO_PAIRS, discover_crypto_pairs

log = logging.getLogger("crypto_universe_cache")

CACHE_PATH = Path(os.environ.get("CRYPTO_UNIVERSE_CACHE", ".cache/crypto_universe.json"))
CACHE_TTL_SECONDS = max(300, int(os.environ.get("CRYPTO_UNIVERSE_CACHE_TTL", "3600")))


def _read_cache() -> list[str] | None:
    try:
        if not CACHE_PATH.exists():
            return None
        payload = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        created_at = float(payload.get("created_at", 0))
        pairs = payload.get("pairs")
        if not isinstance(pairs, list) or not pairs:
            return None
        if time.time() - created_at >= CACHE_TTL_SECONDS:
            log.info("Crypto universe cache scaduta.")
            return None
        result = [str(pair).strip().upper() for pair in pairs if str(pair).strip()]
        return result or None
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        log.warning("Cache crypto non leggibile: %s", exc)
        return None


def _write_cache(pairs: list[str]) -> None:
    try:
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        payload = {"created_at": time.time(), "pairs": pairs}
        temp_path = CACHE_PATH.with_suffix(".tmp")
        temp_path.write_text(json.dumps(payload), encoding="utf-8")
        temp_path.replace(CACHE_PATH)
    except OSError as exc:
        log.warning("Impossibile salvare cache crypto: %s", exc)


def get_cached_crypto_pairs(limit: int = 10) -> list[str]:
    """Restituisce la discovery cached; usa API solo quando necessario."""
    cached = _read_cache()
    if cached:
        log.info("Crypto universe cache HIT: %s", ", ".join(cached))
        return cached[:limit]

    pairs = discover_crypto_pairs(limit=limit, fallback=DEFAULT_CRYPTO_PAIRS)
    if pairs:
        _write_cache(pairs)
        log.info("Crypto universe cache MISS -> discovery eseguita e salvata.")
    return pairs[:limit]


if __name__ == "__main__":
    print(",".join(get_cached_crypto_pairs(limit=10)))
