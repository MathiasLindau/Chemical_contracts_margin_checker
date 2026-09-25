import unittest

from src.margin_checker.market_refresh import indicative_price, rate_instrument, raw_instrument


class MapTest(unittest.TestCase):

    def test_ethanol_uses_maize_and_usd_rate(self):
        self.assertEqual(raw_instrument("Ethanol"), "MAIZE")
        self.assertEqual(rate_instrument("USD"), "SOFR")
        self.assertEqual(rate_instrument("EUR"), "EURIBOR_3M")

    def test_unmapped_product_has_no_raw_index(self):
        self.assertEqual(raw_instrument("Silica Sand"), "UNMAPPED")


class IndicativePriceTest(unittest.TestCase):

    def test_adders_scale_with_the_market_move(self):
        # base 1100, energy 4%, raw 6%
        # gas 20 -> 21 is +5%, maize 300 -> 224 is about -25%
        price = indicative_price(1100, 4, 6, gas_now=21, gas_base=20, raw_now=224, raw_base=300)
        energy = 0.04 * (21 / 20)
        raw = 0.06 * (224 / 300)
        self.assertAlmostEqual(price, 1100 * (1 + energy + raw))
