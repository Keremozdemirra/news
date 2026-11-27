import io
import json
import os
import unittest
from unittest import mock

from aidaily import markets


def listing():
    def coin(sym, name, price, pct, tags=()):
        return {"symbol": sym, "name": name, "tags": list(tags), "quote": {"USD": {"price": price, "percent_change_24h": pct}}}
    return {"data": [coin("BTC", "Bitcoin", 91234.7, 1.234), coin("ETH", "Ethereum", 3012.2, -0.5),
                     coin("USDT", "Tether USDt", 1.0, 0.01, ["stablecoin"]), coin("XRP", "XRP", 2.4123, 3.0),
                     coin("BNB", "BNB", 890.1, 0.0), coin("WBTC", "Wrapped Bitcoin", 91000, 1.2, ["wrapped-tokens"]),
                     coin("SOL", "Solana", 180.22, -2.0), coin("DOGE", "Dogecoin", 0.31234, 5.0)]}


class Opener:
    def __init__(self, body=None, fail=False):
        self.body, self.fail, self.reqs = body, fail, []

    def __call__(self, req, timeout=None):
        self.reqs.append(req)
        if self.fail:
            raise OSError("down")
        return io.BytesIO(json.dumps(self.body).encode())


class Crypto(unittest.TestCase):
    def test_no_key_no_request(self):
        o = Opener(listing())
        with mock.patch.dict(os.environ, {"CMC_API_KEY": ""}):
            self.assertIsNone(markets.crypto(opener=o))
        self.assertEqual(o.reqs, [])

    def test_top_five_without_stablecoins_or_wrapped_tokens(self):
        o = Opener(listing())
        got = markets.crypto("k-secret", opener=o)
        self.assertEqual([c["sym"] for c in got["coins"]], ["BTC", "ETH", "XRP", "BNB", "SOL"])
        self.assertEqual(o.reqs[0].get_header("X-cmc_pro_api_key"), "k-secret")

    def test_failure_is_none_and_the_key_stays_out_of_the_log(self):
        with mock.patch("builtins.print") as p:
            self.assertIsNone(markets.crypto("k-secret", opener=Opener(fail=True)))
        self.assertNotIn("k-secret", str(p.call_args_list))

    def test_strip_carries_the_coins_and_the_credit_next_to_them(self):
        m = {"series": {}, "crypto": markets.crypto("k", opener=Opener(listing()))}
        s = markets.strip(m)
        self.assertIn("$91,235", s)
        self.assertIn("$2.41", s)
        self.assertIn("2.00%", s)
        self.assertIn('href="https://coinmarketcap.com/"', s)
        self.assertIn("Data provided by CoinMarketCap.com", s)
        self.assertLess(s.index("SOL"), s.index("Data provided by CoinMarketCap.com"))

    def test_no_coins_no_credit(self):
        self.assertNotIn("CoinMarketCap", markets.strip({"series": {}}))
        self.assertEqual(markets.crypto_section({"series": {}}), "")

    def test_prices_format_by_size(self):
        self.assertEqual(markets.coin_price(91234.5), "$91,234")
        self.assertEqual(markets.coin_price(180.224), "$180.22")
        self.assertEqual(markets.coin_price(0.31234), "$0.3123")


if __name__ == "__main__":
    unittest.main()
