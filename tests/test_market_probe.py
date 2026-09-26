import tempfile
import unittest
from pathlib import Path

from src.margin_checker.market_probe import pink_sheet_table, write_row


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

    def test_appends_one_row_without_a_header(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "api_price.csv"
            path.write_text("", encoding="utf-8")
            write_row(path, ["2026-09-25", "1.1403", "2026-09-25"])
            write_row(path, ["2026-09-26", "1.1400", "2026-09-25"])
            lines = path.read_text(encoding="utf-8").splitlines()
        self.assertEqual(lines, [
            "2026-09-25,1.1403,2026-09-25",
            "2026-09-26,1.1400,2026-09-25",
        ])

    def test_second_run_on_the_same_day_replaces_the_row(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "api_price.csv"
            write_row(path, ["2026-09-26", "1.1403", "2026-09-25"])
            write_row(path, ["2026-09-26", "1.1410", "2026-09-25"])
            self.assertEqual(
                path.read_text(encoding="utf-8").splitlines(),
                ["2026-09-26,1.1410,2026-09-25"],
            )
