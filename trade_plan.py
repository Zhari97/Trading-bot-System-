"""Piano d'ingresso informativo per i segnali del bot.

Non esegue ordini e non usa leva. Produce livelli indicativi per una
valutazione manuale: allocazione massima 5% del conto, TP iniziale fisso 5%
e stop contenuto in funzione della volatilita'.
"""

MAX_ACCOUNT_ALLOCATION = 0.05
FIXED_TP_PCT = 0.05
DEFAULT_SL_PCT = 0.01
MIN_SL_PCT = 0.005
MAX_SL_PCT = 0.02
ENTRY_ZONE_PCT = 0.0025


def costruisci_trade_plan(analisi: dict) -> dict | None:
    classificazione = analisi.get("classificazione", {})
    direzione = classificazione.get("direzione")
    livello = classificazione.get("livello")

    if livello != "FORTE" or direzione not in ("LONG", "SHORT"):
        return None

    prezzo = float(analisi["prezzo"])
    ctx = analisi["ctx"]
    atr = float(ctx.atr14[ctx.i])
    atr_pct = atr / prezzo if prezzo else 0.0
    ema21 = float(ctx.ema21[ctx.i])

    sl_pct = max(MIN_SL_PCT, min(DEFAULT_SL_PCT, atr_pct * 1.25))
    sl_pct = min(sl_pct, MAX_SL_PCT)

    # Entry zone stretta: serve per distinguere un prezzo ancora accettabile
    # da un ingresso già troppo distante dal livello del segnale.
    if direzione == "LONG":
        entry_low = prezzo * (1 - ENTRY_ZONE_PCT)
        entry_high = prezzo * (1 + ENTRY_ZONE_PCT)
        stop_loss = prezzo * (1 - sl_pct)
        take_profit = prezzo * (1 + FIXED_TP_PCT)
        ema_distance_pct = (prezzo - ema21) / prezzo * 100 if prezzo else 0.0
    else:
        entry_low = prezzo * (1 - ENTRY_ZONE_PCT)
        entry_high = prezzo * (1 + ENTRY_ZONE_PCT)
        stop_loss = prezzo * (1 + sl_pct)
        take_profit = prezzo * (1 - FIXED_TP_PCT)
        ema_distance_pct = (ema21 - prezzo) / prezzo * 100 if prezzo else 0.0

    trend = float(analisi["categorie"]["trend"])
    momentum = float(analisi["categorie"]["momentum"])

    # Qualita' ingresso: allineamento Trend/Momentum + distanza dall'EMA21.
    if trend >= 75 or trend <= 25:
        trend_ok = True
    else:
        trend_ok = False
    if momentum >= 65 or momentum <= 35:
        momentum_ok = True
    else:
        momentum_ok = False

    aligned = (
        (direzione == "LONG" and trend > 55 and momentum > 55)
        or (direzione == "SHORT" and trend < 45 and momentum < 45)
    )
    not_too_far = abs(ema_distance_pct) <= 2.0

    if aligned and trend_ok and momentum_ok and not_too_far:
        entry_quality = "OTTIMA"
    elif aligned and not_too_far:
        entry_quality = "ACCETTABILE"
    else:
        entry_quality = "TARDIVA"

    risk_pct = sl_pct * 100
    reward_pct = FIXED_TP_PCT * 100
    rr = reward_pct / risk_pct if risk_pct else 0.0

    return {
        "direction": direzione,
        "entry": prezzo,
        "entry_zone_low": entry_low,
        "entry_zone_high": entry_high,
        "take_profit": take_profit,
        "stop_loss": stop_loss,
        "tp_pct": reward_pct,
        "sl_pct": risk_pct,
        "risk_reward": rr,
        "entry_quality": entry_quality,
        "ema21_distance_pct": ema_distance_pct,
        "max_account_allocation_pct": MAX_ACCOUNT_ALLOCATION * 100,
        "max_drawdown_account_pct": MAX_ACCOUNT_ALLOCATION * sl_pct * 100,
        "leverage": 1,
        "mode": "MANUAL_REVIEW_ONLY",
    }


def format_trade_plan(plan: dict | None) -> str:
    if not plan:
        return ""

    quality_emoji = {
        "OTTIMA": "🟢",
        "ACCETTABILE": "🟡",
        "TARDIVA": "🔴",
    }.get(plan["entry_quality"], "⚪")

    return (
        "\n\n💰 <b>PIANO INGRESSO (solo valutazione)</b>\n"
        f"Entry: <b>{plan['entry']:.8f}</b>\n"
        f"Zona: <b>{plan['entry_zone_low']:.8f} — {plan['entry_zone_high']:.8f}</b>\n"
        f"TP fisso: <b>{plan['take_profit']:.8f}</b> (+{plan['tp_pct']:.1f}%)\n"
        f"SL: <b>{plan['stop_loss']:.8f}</b> ({plan['sl_pct']:.2f}% prezzo)\n"
        f"R:R: <b>1:{plan['risk_reward']:.2f}</b>\n"
        f"Qualita' ingresso: {quality_emoji} <b>{plan['entry_quality']}</b>\n"
        f"Allocazione max: <b>{plan['max_account_allocation_pct']:.1f}% del conto</b>\n"
        f"Drawdown teorico sul conto: <b>~{plan['max_drawdown_account_pct']:.3f}%</b>\n"
        "⚠️ Nessun ordine automatico / leva: verificare manualmente prima dell'ingresso."
    )
