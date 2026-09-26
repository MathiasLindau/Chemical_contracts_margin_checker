import csv
import importlib.util
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "data" / "scripts" / "create_product_index.py"


def load_script():
    spec = importlib.util.spec_from_file_location("create_product_index", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ProductIndexTest(unittest.TestCase):

    def test_product_name_chooses_brent_maize_or_none(self):
        module = load_script()
        contracts = [
            {"product_name": "Ethanol"},
            {"product_name": "Ethanol"},
            {"product_name": "Benzene"},
            {"product_name": "Caustic Soda"},
        ]
        rows = {row["product_name"]: row for row in module.index_rows(contracts)}
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows["Ethanol"]["raw_material_instrument"], "MAIZE")
        self.assertEqual(rows["Benzene"]["raw_material_instrument"], "BRENT")
        self.assertEqual(rows["Caustic Soda"]["raw_material_instrument"], "UNMAPPED")
        self.assertTrue(all(row["energy_instrument"] == "GAS_EU" for row in rows.values()))

    def test_real_contracts_match_the_saved_map(self):
        module = load_script()
        root = Path(__file__).resolve().parents[1]
        with (root / "data" / "chemical_contracts.csv").open(encoding="utf-8", newline="") as handle:
            built = module.index_rows(list(csv.DictReader(handle)))
        with (root / "data" / "market" / "product_index_map.csv").open(encoding="utf-8", newline="") as handle:
            saved = list(csv.DictReader(handle))
        self.assertEqual(built, saved)
