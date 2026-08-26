import unittest

from segnale_crypto_binance import alert_duplicato, firma_alert


class TestAlertGate(unittest.TestCase):
    def _analysis(self, score=18.4, confluence=100.0, trend=20.9, momentum=0.0, setup=25.6):
        return {
            "score": score,
            "confluenza": confluence,
            "categorie": {
                "trend": trend,
                "momentum": momentum,
                "setup": setup,
            },
            "classificazione": {
                "livello": "FORTE",
                "direzione": "SHORT",
                "trend_direzione": "SHORT",
                "setup_direzione": "SHORT",
                "momentum_direzione": "SHORT",
                "controtrend": False,
            },
        }

    def test_same_setup_is_duplicate(self):
        analysis = self._analysis()
        previous = {
            "classification": "FORTE",
            "direction": "SHORT",
            "counter_trend": False,
            "score": 18.4,
            "confluence": 100.0,
            "categories": {
                "trend": 20.9,
                "momentum": 0.0,
                "setup": 25.6,
            },
        }
        self.assertEqual(firma_alert(analysis), firma_alert(analysis))
        self.assertTrue(alert_duplicato(analysis, previous))

    def test_score_small_change_is_still_duplicate(self):
        analysis = self._analysis(score=18.4)
        previous = {
            "classification": "FORTE",
            "direction": "SHORT",
            "counter_trend": False,
            "score": 18.1,
            "confluence": 100.0,
            "categories": {
                "trend": 20.9,
                "momentum": 0.0,
                "setup": 25.6,
            },
        }
        self.assertTrue(alert_duplicato(analysis, previous))

    def test_material_score_change_is_new_alert(self):
        analysis = self._analysis(score=18.4)
        previous = {
            "classification": "FORTE",
            "direction": "SHORT",
            "counter_trend": False,
            "score": 25.4,
            "confluence": 100.0,
            "categories": {
                "trend": 27.0,
                "momentum": 5.0,
                "setup": 30.0,
            },
        }
        self.assertFalse(alert_duplicato(analysis, previous))

    def test_direction_change_is_new_alert(self):
        analysis = self._analysis()
        previous = {
            "classification": "FORTE",
            "direction": "LONG",
            "counter_trend": False,
            "score": 18.4,
            "confluence": 100.0,
            "categories": {
                "trend": 20.9,
                "momentum": 0.0,
                "setup": 25.6,
            },
        }
        self.assertFalse(alert_duplicato(analysis, previous))


if __name__ == "__main__":
    unittest.main()
