import csv
import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "data" / "scripts" / "create_contract_data.py"


def load_script():
    spec = importlib.util.spec_from_file_location("create_contract_data", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ContractDataTest(unittest.TestCase):

    def test_markdown_contracts_match_the_saved_table(self):
        module = load_script()
        files = module.contract_files(ROOT / "data" / "contracts")
        parsed = {row["contract_id"]: row for row in (module.parse_contract(path) for path in files)}
        with (ROOT / "data" / "chemical_contracts.csv").open(encoding="utf-8", newline="") as handle:
            saved = list(csv.DictReader(handle))
        self.assertEqual(len(parsed), len(saved))
        number_fields = [
            "base_price",
            "energy_adder_percentage",
            "raw_material_adder_percentage",
            "min_monthly_volume_tons",
            "max_monthly_volume_tons",
            "max_transport_duration_days",
            "payment_terms_days",
            "min_shelf_life_days",
            "demurrage_days_included",
            "breach_penalty_amount",
        ]
        for row in saved:
            got = parsed[row["contract_id"]]
            self.assertEqual(got["customer_name"], row["customer_name"])
            self.assertEqual(got["product_name"], row["product_name"])
            self.assertEqual(got["currency"], row["currency"])
            for field in number_fields:
                self.assertEqual(float(got[field]), float(row[field]), row["contract_id"] + " " + field)
