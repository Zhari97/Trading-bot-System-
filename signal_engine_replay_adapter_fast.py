"""Fast bridge to production modules with research-only continuous scoring."""
from __future__ import annotations

from signal_engine import (
    ContestoMercato,
    tutte_le_strategie,
    calcola_categorie as production_categories,
    classifica_segnale,
    determina_direzione,
)
from research_scoring import continuous_categories
from trade_plan import costruisci_trade_plan


def analyze_context_at(ctx: ContestoMercato, i: int) -> dict | None:
    if i < 60 or i >= len(ctx.candele):
        return None
    ctx.i = i
    risultati = tutte_le_strategie(ctx)

    # Keep production direction/evidence available for comparison, but use
    # continuous research categories for historical signal classification.
    prod = production_categories(risultati)
    categorie = continuous_categories(ctx, risultati)
    categorie["peso_long"] = prod["peso_long"]
    categorie["peso_short"] = prod["peso_short"]
    categorie["totale_pesi"] = prod["totale_pesi"]
    categorie["score"] = (
        categorie["trend"] * 0.45
        + categorie["momentum"] * 0.20
        + categorie["setup"] * 0.35
    )

    classificazione = classifica_segnale(categorie, risultati)
    direzione, confluenza, conflitto = determina_direzione(risultati)
    analysis = {
        "pair": "HISTORICAL",
        "prezzo": ctx.chiusure[i],
        "ctx": ctx,
        "risultati": risultati,
        "categorie": categorie,
        "production_categories": prod,
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
