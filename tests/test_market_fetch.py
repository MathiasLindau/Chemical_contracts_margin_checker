import unittest

from src.margin_checker.market_fetch import (
    month_code_to_date,
    parse_ecb_csv,
    raw_instrument,
    recent,
)


class MonthCodeTest(unittest.TestCase):

    def test_world_bank_month(self):
        self.assertEqual(month_code_to_date("2026M08"), "2026-08-01")

    def test_rejects_daily_stamp(self):
        with self.assertRaises(ValueError):
            month_code_to_date("2026-08-01")


class EcbParseTest(unittest.TestCase):

    def test_reads_observation(self):
        text = (
            "KEY,TIME_PERIOD,OBS_VALUE\n"
            "EXR.D.USD.EUR.SP00.A,2026-09-25,1.1403\n"
        )
        rows = parse_ecb_csv(text)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["instrument"], "EURUSD")
        self.assertEqual(rows[0]["value"], 1.1403)
        self.assertEqual(rows[0]["frequency"], "daily")
        self.assertEqual(rows[0]["unit"], "USD/EUR")


class ProductFamilyTest(unittest.TestCase):

    def test_known_families(self):
        self.assertEqual(raw_instrument("Polyethylene"), "BRENT")
        self.assertEqual(raw_instrument("Ethanol"), "MAIZE")
        self.assertEqual(raw_instrument("Silica Sand"), "UNMAPPED")


class RecentWindowTest(unittest.TestCase):

    def test_keeps_last_per_instrument(self):
        rows = [
            {"instrument": "BRENT", "as_of_date": "2026-06-01"},
            {"instrument": "BRENT", "as_of_date": "2026-07-01"},
            {"instrument": "BRENT", "as_of_date": "2026-08-01"},
            {"instrument": "MAIZE", "as_of_date": "2026-08-01"},
        ]
        kept = recent(rows, 2)
        brent = [row["as_of_date"] for row in kept if row["instrument"] == "BRENT"]
        self.assertEqual(brent, ["2026-07-01", "2026-08-01"])
