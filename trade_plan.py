"""Piano d'ingresso informativo per i segnali del bot.

Non esegue ordini e non usa leva. Produce solo livelli indicativi per
valutare un eventuale trade manuale: allocazione massima 5% del conto,
TP iniziale fisso 2.5% e stop contenuto entro un limite configurabile.
"""

MAX_ACCOUNT_ALLOCATION = 0.05
FIXED_TP_PCT = 0.025
DEFAULT_SL_PCT = 0.01
MIN_SL_PCT = 0.005
MAX_SL_PCT = 0.02


def costruisci_trade_plan(analisi: dict) -> dict | None:
    classificazione = analisi.get("classificazione", {})
    direzione = classificazione.get("direzione")
    livello = classificazione.get("livello")

    # Per ora mostriamo un piano solo su segnali FORTE validi.
    # Il filtro RSI/quality guard può quindi bloccarlo prima.
    if livello != "FORTE" or direzione not in ("LONG", "SHORT"):
        return None

    prezzo = float(analisi["prezzo"])
    atr = float(analisi["ctx"].atr14[analisi["ctx"].i])
    atr_pct = atr / prezzo if prezzo else 0.0

    # Stop iniziale basato su volatilità, ma sempre piccolo e limitato.
    sl_pct = max(MIN_SL_PCT, min(DEFAULT_SL_PCT, atr_pct * 1.25))
    sl_pct = min(sl_pct, MAX_SL_PCT)

    if direzione == "LONG":
        stop_loss = prezzo * (1 - sl_pct)
        take_profit = prezzo * (1 + FIXED_TP_PCT)
    else:
        stop_loss = prezzo * (1 + sl_pct)
        take_profit = prezzo * (1 - FIXED_TP_PCT)

    return {
        "direction": direzione,
        "entry": prezzo,
        "take_profit": take_profit,
        "stop_loss": stop_loss,
        "tp_pct": FIXED_TP_PCT * 100,
        "sl_pct": sl_pct * 100,
        "max_account_allocation_pct": MAX_ACCOUNT_ALLOCATION * 100,
        "max_drawdown_account_pct": MAX_ACCOUNT_ALLOCATION * sl_pct * 100,
        "leverage": 1,
        "mode": "MANUAL_REVIEW_ONLY",
    }


def format_trade_plan(plan: dict | None) -> str:
    if not plan:
        return ""

    return (
        "\n\n💰 <b>PIANO INGRESSO (solo valutazione)</b>\n"
        f"Entry: <b>{plan['entry']:.8f}</b>\n"
        f"TP fisso: <b>{plan['take_profit']:.8f}</b> (+{plan['tp_pct']:.1f}%)\n"
        f"SL: <b>{plan['stop_loss']:.8f}</b> (-{plan['sl_pct']:.2f}% prezzo)\n"
        f"Allocazione max: <b>{plan['max_account_allocation_pct']:.1f}% del conto</b>\n"
        f"Perdita teorica max su capitale allocato: <b>~{plan['max_drawdown_account_pct']:.3f}% del conto</b>\n"
        "⚠️ Nessun ordine automatico / leva: verificare manualmente prima dell'ingresso."
    )
