import unittest

try:
    import pandas as pd
except ImportError:
    pd = None

from src.margin_checker.daily_prices import attach_daily_prices


class DailyPriceJoinTest(unittest.TestCase):

    def setUp(self):
        if pd is None:
            self.skipTest("pandas is not installed")

    def test_adds_the_daily_price_without_replacing_the_base_price(self):
        contracts = pd.DataFrame([
            {"contract_id": "CON-2023-0003", "base_price": 1100, "product_name": "Ethanol"},
            {"contract_id": "CON-2023-0001", "base_price": 1200, "product_name": "Polyethylene"},
        ])
        prices = pd.DataFrame([
            {
                "contract_id": "CON-2023-0003",
                "base_price": 1194.85,
                "indicative_price_per_ton": 1194.85,
                "financing_per_ton": 7.62,
                "customer_name": "BioChem Innovations",
            }
        ])
        joined = attach_daily_prices(contracts, prices)
        ethanol = joined.loc[joined["contract_id"] == "CON-2023-0003"].iloc[0]
        other = joined.loc[joined["contract_id"] == "CON-2023-0001"].iloc[0]
        self.assertEqual(ethanol["base_price"], 1100)
        self.assertEqual(ethanol["indicative_price_per_ton"], 1194.85)
        self.assertTrue(pd.isna(other["indicative_price_per_ton"]))
        self.assertNotIn("customer_name", joined.columns)
