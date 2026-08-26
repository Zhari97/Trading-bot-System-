"""Adapter between historical candles and the production signal engine.

The live engine keeps its normal data acquisition path. This adapter bypasses
only the network fetch and feeds closed historical candles into the exact same
ContestoMercato, strategy modules, scoring and classification functions.
"""
from __future__ import annotations

from signal_engine import (
    ContestoMercato,
    tutte_le_strategie,
    calcola_categorie,
    classifica_segnale,
    determina_direzione,
)
from trade_plan import costruisci_trade_plan


def analyze_closed_candles(candles: list[dict]) -> dict | None:
    """Analyze the latest CLOSED candle with the production engine logic."""
    if len(candles) < 60:
        return None

    ctx = ContestoMercato(candles)
    # Live data normally contains a final forming candle, so ctx.i points to
    # len(candles)-2. Historical datasets contain only closed candles; move the
    # pointer to the latest closed candle without changing indicator formulas.
    ctx.i = len(candles) - 1

    risultati = tutte_le_strategie(ctx)
    categorie = calcola_categorie(risultati)
    classificazione = classifica_segnale(categorie, risultati)
    direzione, confluenza, conflitto = determina_direzione(risultati)

    analysis = {
        "pair": "HISTORICAL",
        "prezzo": ctx.chiusure[ctx.i],
        "ctx": ctx,
        "risultati": risultati,
        "categorie": categorie,
        "classificazione": classificazione,
        "direzione_dominante": direzione,
        "confluenza": confluenza,
        "conflitto": conflitto,
        "peso_long": categorie["peso_long"],
        "peso_short": categorie["peso_short"],
        "score": categorie["score"],
        "bias": "LONG" if categorie["score"] > 50 else "SHORT" if categorie["score"] < 50 else "NEUTRO",
    }

    plan = costruisci_trade_plan(analysis)
    if plan:
        analysis["trade_plan"] = plan
    return analysis


def historical_signal(candles: list[dict]) -> dict | None:
    """Return a compact signal record compatible with the replay harness."""
    analysis = analyze_closed_candles(candles)
    if not analysis:
        return None

    classification = analysis["classificazione"]
    if classification.get("livello") != "FORTE":
        return None

    plan = analysis.get("trade_plan")
    if not plan:
        return None

    return {
        "direction": plan["direction"],
        "entry": plan["entry"],
        "stop_loss": plan["stop_loss"],
        "take_profit": plan["take_profit"],
        "score": analysis["score"],
        "confluence": analysis["confluenza"],
        "level": classification["livello"],
        "entry_quality": plan["entry_quality"],
    }
