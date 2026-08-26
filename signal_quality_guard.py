"""Guard di qualita' applicato prima dell'invio degli alert automatici.

Non modifica lo score del motore. Interviene solo quando una classificazione
FORTE e' associata a un RSI estremamente esteso, situazione in cui vogliamo
osservare il setup invece di forzare un nuovo alert operativo.
"""

from signal_engine import analizza_coppia as _analizza_coppia

RSI_LONG_EXTREME = 80.0
RSI_SHORT_EXTREME = 20.0


def analizza_coppia_con_guard(pair: str):
    analisi = _analizza_coppia(pair)
    classificazione = analisi["classificazione"]
    rsi = float(analisi["ctx"].rsi14[analisi["ctx"].i])
    direzione = classificazione.get("direzione")

    if classificazione.get("livello") == "FORTE":
        if direzione == "SHORT" and rsi <= RSI_SHORT_EXTREME:
            classificazione["livello"] = "SETUP"
            classificazione["alert_automatico"] = False
            classificazione["motivo"] = (
                f"Setup SHORT forte ma RSI estremamente scarico ({rsi:.1f}): "
                "rischio di ingresso tardivo, si osserva senza alert automatico."
            )
        elif direzione == "LONG" and rsi >= RSI_LONG_EXTREME:
            classificazione["livello"] = "SETUP"
            classificazione["alert_automatico"] = False
            classificazione["motivo"] = (
                f"Setup LONG forte ma RSI estremamente tirato ({rsi:.1f}): "
                "rischio di ingresso tardivo, si osserva senza alert automatico."
            )

    return analisi


# Il runner importa analizza_coppia da signal_engine: sostituiamo il riferimento
# prima che venga importato il runner, mantenendo invariato il motore centrale.
