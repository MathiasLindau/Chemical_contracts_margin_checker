import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "data" / "scripts" / "calculate_contract_price.py"


def load_script():
    spec = importlib.util.spec_from_file_location("calculate_contract_price", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def tables():
    index_rows = [
        {"instrument": "GAS_EU", "baseline_value": "20.18"},
        {"instrument": "BRENT", "baseline_value": "83.1"},
        {"instrument": "MAIZE", "baseline_value": "302.8"},
    ]
    api_row = {
        "pulled_on_date": "2026-09-26",
        "usd_for_one_eur": "1.1403",
        "eu_natural_gas_usd_per_mmbtu": "21.11",
        "brent_crude_usd_per_barrel": "90.9",
        "maize_usd_per_metric_ton": "224",
        "sofr_percent_per_year": "3.88",
        "euribor_3m_percent_per_year": "2.5131429",
    }
    product_map = {
        "Ethanol": {"raw_material_instrument": "MAIZE"},
        "Caustic Soda": {"raw_material_instrument": "UNMAPPED"},
        "Benzene": {"raw_material_instrument": "BRENT"},
    }
    return index_rows, api_row, product_map


class ContractPriceTest(unittest.TestCase):

    def setUp(self):
        self.module = load_script()
        self.index_rows, self.api_row, self.product_map = tables()

    def price(self, **contract):
        return self.module.price_one(
            contract, self.product_map, self.index_rows, self.api_row, 975.0, 150.0
        )

    def test_maize_product_reads_maize_sofr_and_converts_the_trip(self):
        row = self.price(
            contract_id="CON-2023-0003",
            customer_name="BioChem Innovations",
            product_name="Ethanol",
            currency="USD",
            base_price="1100",
            energy_adder_percentage="4",
            raw_material_adder_percentage="6",
            payment_terms_days="60",
        )
        self.assertEqual(row["raw_rule"], "api")
        self.assertEqual(row["raw_instrument"], "MAIZE")
        self.assertEqual(row["energy_rule"], "api")
        self.assertEqual(row["rate_instrument"], "SOFR")
        self.assertEqual(row["indicative_price_per_ton"], "1194.85")
        self.assertEqual(row["financing_per_ton"], "7.62")
        self.assertEqual(row["logistics_amount"], "1111.79")
        self.assertEqual(row["logistics_currency"], "USD")
        self.assertEqual(row["demurrage_amount"], "0.00")
        self.assertEqual(row["calculation_rule"], "energy_api+raw_api+rate_api+logistics_fixed")

    def test_unmapped_product_keeps_the_raw_percent_at_the_2023_index(self):
        row = self.price(
            contract_id="C-1",
            customer_name="A",
            product_name="Caustic Soda",
            currency="EUR",
            base_price="1000",
            energy_adder_percentage="10",
            raw_material_adder_percentage="5",
            payment_terms_days="30",
        )
        self.assertEqual(row["raw_rule"], "static")
        self.assertEqual(row["raw_instrument"], "NONE")
        self.assertEqual(row["raw_ratio"], "1.000000")
        self.assertEqual(row["raw_amount"], "50.00")
        self.assertNotEqual(row["energy_ratio"], "1.000000")
        self.assertEqual(row["rate_instrument"], "EURIBOR_3M")
        self.assertEqual(row["logistics_amount"], "975.00")
        self.assertEqual(row["logistics_currency"], "EUR")
        self.assertEqual(row["calculation_rule"], "energy_api+raw_static+rate_api+logistics_fixed")

    def test_gbp_contract_does_not_read_an_interest_rate(self):
        row = self.price(
            contract_id="C-2",
            customer_name="B",
            product_name="Benzene",
            currency="GBP",
            base_price="800",
            energy_adder_percentage="3",
            raw_material_adder_percentage="7",
            payment_terms_days="45",
        )
        self.assertEqual(row["raw_rule"], "api")
        self.assertEqual(row["raw_instrument"], "BRENT")
        self.assertEqual(row["rate_rule"], "static")
        self.assertEqual(row["rate_instrument"], "NONE")
        self.assertEqual(row["financing_per_ton"], "0.00")
        self.assertEqual(row["fx_rule"], "static")
        self.assertEqual(row["logistics_currency"], "EUR")
        self.assertEqual(row["calculation_rule"], "energy_api+raw_api+rate_static+logistics_fixed")
