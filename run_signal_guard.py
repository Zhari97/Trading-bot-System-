"""Entry point GitHub Actions con guard di qualita' sugli alert."""

import signal_engine
from signal_quality_guard import analizza_coppia_con_guard

signal_engine.analizza_coppia = analizza_coppia_con_guard

import segnale_crypto_binance
from trade_plan import costruisci_trade_plan, format_trade_plan

# Aggiunge il piano d'ingresso al report Telegram senza modificare
# il motore centrale o introdurre esecuzione automatica degli ordini.
_report_base = segnale_crypto_binance.costruisci_report


def costruisci_report_con_trade_plan(pair: str, analisi: dict) -> str:
    report = _report_base(pair, analisi)
    return report + format_trade_plan(costruisci_trade_plan(analisi))


segnale_crypto_binance.costruisci_report = costruisci_report_con_trade_plan


if __name__ == "__main__":
    segnale_crypto_binance.main()
