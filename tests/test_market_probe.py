import unittest

from src.margin_checker.market_probe import pink_sheet_table


class PinkSheetTableTest(unittest.TestCase):

    def test_finds_header_and_newest_month(self):
        rows = [
            ("title", None),
            (None, None),
            (None, None),
            ("Updated on September 02, 2026", None),
            (None, "Crude oil, Brent", "Maize"),
            ("2026M07", 80, 200),
            ("2026M08", 90.9, 224),
            (None, None, None),
        ]
        labels, last, updated = pink_sheet_table(rows)
        self.assertEqual(labels[1], "Crude oil, Brent")
        self.assertEqual(last[0], "2026M08")
        self.assertIn("September", updated)

    def test_missing_header(self):
        with self.assertRaises(RuntimeError):
            pink_sheet_table([("no prices",)])
