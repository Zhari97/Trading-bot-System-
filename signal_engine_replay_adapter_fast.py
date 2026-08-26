"""Fast bridge to the production signal engine for historical replay."""
from __future__ import annotations

from signal_engine import (
    ContestoMercato,
    tutte_le_strategie,
    calcola_categorie,
    classifica_segnale,
    determina_direzione,
)
from trade_plan import costruisci_trade_plan


def analyze_context_at(ctx: ContestoMercato, i: int) -> dict | None:
    if i < 60 or i >= len(ctx.candele):
        return None
    ctx.i = i
    risultati = tutte_le_strategie(ctx)
    categorie = calcola_categorie(risultati)
    classificazione = classifica_segnale(categorie, risultati)
    direzione, confluenza, conflitto = determina_direzione(risultati)
    analysis = {
        "pair": "HISTORICAL",
        "prezzo": ctx.chiusure[i],
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
