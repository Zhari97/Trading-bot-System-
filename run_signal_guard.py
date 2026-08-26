"""Entry point GitHub Actions con guard di qualita' sugli alert."""

import signal_engine
from signal_quality_guard import analizza_coppia_con_guard

signal_engine.analizza_coppia = analizza_coppia_con_guard

import segnale_crypto_binance

if __name__ == "__main__":
    segnale_crypto_binance.main()
