import csv
import importlib.util
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "data" / "scripts" / "create_logistics_price.py"


def load_script():
    spec = importlib.util.spec_from_file_location("create_logistics_price", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class LogisticsPriceTest(unittest.TestCase):

    def test_writes_a_full_two_year_road_tariff(self):
        module = load_script()
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "logistics_price.csv"
            module.write_tariff(path)
            with path.open(encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
        by_item = {row["item"]: row for row in rows}
        self.assertEqual(by_item["road_bulk_ftl"]["price"], "1.95")
        self.assertEqual(by_item["road_bulk_ftl"]["unit"], "EUR per km")
        self.assertEqual(by_item["road_bulk_ftl_reference_trip"]["price"], "975.00")
        self.assertEqual(by_item["demurrage_bulk_container"]["price"], "150")
        self.assertEqual(by_item["demurrage_bulk_container"]["unit"], "EUR per container per day")
        for row in rows:
            self.assertTrue(all(value.strip() for value in row.values()))
            self.assertEqual(row["valid_from"], "2026-01-01")
            self.assertEqual(row["valid_to"], "2027-12-31")
            self.assertEqual(row["currency"], "EUR")
