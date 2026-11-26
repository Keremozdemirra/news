import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from aidaily import markets

ECB = """<?xml version="1.0"?><gesmes:Envelope xmlns:gesmes="http://www.gesmes.org/xml/2002-08-01" xmlns="http://www.ecb.int/vocabulary/2002-08-01/eurofxref">
<Cube><Cube time='2026-11-26'><Cube currency='USD' rate='1.1000'/><Cube currency='JPY' rate='165.00'/><Cube currency='GBP' rate='0.8800'/><Cube currency='CNY' rate='7.7000'/></Cube></Cube></gesmes:Envelope>"""
UST = """<feed xmlns="http://www.w3.org/2005/Atom" xmlns:m="m" xmlns:d="d"><entry><content><m:properties><d:NEW_DATE>2026-11-24T00:00:00</d:NEW_DATE>
<d:BC_2YEAR>4.60</d:BC_2YEAR><d:BC_10YEAR>4.90</d:BC_10YEAR><d:BC_30YEAR>5.20</d:BC_30YEAR></m:properties></content></entry>
<entry><content><m:properties><d:NEW_DATE>2026-11-25T00:00:00</d:NEW_DATE><d:BC_2YEAR>4.55</d:BC_2YEAR><d:BC_10YEAR>4.85</d:BC_10YEAR><d:BC_30YEAR>5.24</d:BC_30YEAR></m:properties></content></entry></feed>"""


def data():
    return {"fx": markets.parse_ecb(ECB), "ust": markets.parse_treasury(UST), "dfr": {"value": 2.5, "since": "2026-09-16"}}


class Markets(unittest.TestCase):
    def test_crosses_are_computed_from_the_ecb_rates_and_labelled(self):
        r = {x["k"]: x for x in markets.rows(data())}
        self.assertEqual(r["EUR/USD"]["v"], "1.1000")
        self.assertEqual(r["USD/JPY"]["v"], "150.00")
        self.assertEqual(r["GBP/USD"]["v"], "1.2500")
        self.assertEqual(r["USD/CNY"]["v"], "7.0000")
        self.assertEqual(r["USD/JPY"]["src"], "Calculated from ECB reference rates")
        self.assertEqual(r["US 10-year"]["v"], "4.85%")
        self.assertEqual(r["US 10-year"]["d"], "−0.05")
        self.assertEqual(r["US 10-year"]["date"], "25 Nov 2026")

    def test_no_oil_row_without_data_and_never_a_pending_row(self):
        html = markets.rates_box(data())
        self.assertNotIn("Brent", html)
        self.assertNotIn("Pending", html)
        self.assertIn("Source", markets.attribution(data()))

    def test_oil_rows_appear_with_the_eia_series_and_attribution(self):
        fake = {"response": {"data": [{"period": "2026-11-25", "series": "RBRTE", "value": "72.40"}, {"period": "2026-11-24", "series": "RBRTE", "value": "71.90"},
                                      {"period": "2026-11-25", "series": "RWTC", "value": "68.10"}]}}
        m = {**data(), "oil": markets.parse_eia(fake)}
        r = {x["k"]: x for x in markets.rows(m)}
        self.assertEqual(r["Brent spot"]["v"], "$72.40")
        self.assertEqual(r["Brent spot"]["d"], "+0.50")
        self.assertEqual(r["WTI spot"]["date"], "25 Nov 2026")
        self.assertIn("Source: U.S. Energy Information Administration.", markets.attribution(m))

    def test_load_drops_oil_without_a_key_and_keeps_last_good_blocks(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "markets.json"
            f.write_text(json.dumps({"ust": data()["ust"]}))
            fresh = {"fx": data()["fx"], "oil": {"brent": {"date": "2026-11-25", "value": 70.0, "prev": None}}}
            env = {k: v for k, v in os.environ.items() if k != "EIA_API_KEY"}
            with mock.patch.object(markets, "FILE", f), mock.patch.object(markets, "fetch", return_value=fresh), mock.patch.dict(os.environ, env, clear=True):
                m = markets.load(live=True)
                self.assertEqual(sorted(m), ["fetched", "fx", "ust"])  # last-good ust kept, fresh fx added, oil dropped without a key
                self.assertIn("oil", json.loads(f.read_text()))  # kept on disk for a build that has the key
                os.environ["EIA_API_KEY"] = "test-key"
                self.assertIn("oil", markets.load(live=True))

    def test_context_box_only_when_a_series_matches(self):
        p = {"headlines": ["ECB holds rates as inflation cools"], "dek": ""}
        self.assertIn("Euro-area deposit facility rate", markets.context_for(p, data()))
        self.assertIn("Source: ECB statistics.", markets.context_for(p, data()))
        us = {"headlines": ["Fed chair signals a pause"], "dek": ""}
        self.assertIn("US 10-year Treasury yield", markets.context_for(us, data()))
        self.assertEqual(markets.context_for({"headlines": ["SAP explores job cuts"], "dek": "Restructuring."}, data()), "")
        self.assertEqual(markets.context_for(p, None), "")
