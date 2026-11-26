import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from aidaily import markets

ECB = """<?xml version="1.0"?><gesmes:Envelope xmlns:gesmes="http://www.gesmes.org/xml/2002-08-01" xmlns="http://www.ecb.int/vocabulary/2002-08-01/eurofxref">
<Cube><Cube time='2026-11-26'><Cube currency='USD' rate='1.1000'/><Cube currency='JPY' rate='165.00'/><Cube currency='GBP' rate='0.8800'/><Cube currency='CNY' rate='7.7000'/></Cube>
<Cube time='2026-11-25'><Cube currency='USD' rate='1.0900'/><Cube currency='JPY' rate='163.50'/><Cube currency='GBP' rate='0.8800'/><Cube currency='CNY' rate='7.7000'/></Cube></Cube></gesmes:Envelope>"""
UST = """<feed xmlns="http://www.w3.org/2005/Atom" xmlns:m="m" xmlns:d="d"><entry><content><m:properties><d:NEW_DATE>2026-11-24T00:00:00</d:NEW_DATE>
<d:BC_2YEAR>4.60</d:BC_2YEAR><d:BC_10YEAR>4.90</d:BC_10YEAR><d:BC_30YEAR>5.20</d:BC_30YEAR></m:properties></content></entry>
<entry><content><m:properties><d:NEW_DATE>2026-11-25T00:00:00</d:NEW_DATE><d:BC_2YEAR>4.55</d:BC_2YEAR><d:BC_10YEAR>4.85</d:BC_10YEAR><d:BC_30YEAR>5.24</d:BC_30YEAR></m:properties></content></entry></feed>"""
EIA = {"response": {"data": [{"period": "2026-11-25", "series": "RBRTE", "value": "72.40"}, {"period": "2026-11-24", "series": "RBRTE", "value": "71.90"},
                             {"period": "2026-11-25", "series": "RWTC", "value": "68.10"}, {"period": "2026-11-24", "series": "RWTC", "value": "68.50"},
                             {"period": "2026-11-23", "series": "EMM_EPMR_PTE_NUS_DPG", "value": "3.071"}, {"period": "2026-11-16", "series": "EMM_EPMR_PTE_NUS_DPG", "value": "3.050"}]}}


def data(with_eia=False):
    series = {k: [list(x) for x in v] for k, v in markets.parse_ecb_hist(ECB).items()}
    rows = markets.parse_treasury(UST)
    series["ust10"] = [[r["date"], r["10YEAR"]] for r in rows]
    series["ust2"] = [[r["date"], r["2YEAR"]] for r in rows]
    if with_eia:
        by = markets.parse_eia(EIA)
        for key, spec in markets.SERIES.items():
            if spec[5] in by:
                series[key] = [list(x) for x in by[spec[5]]]
    return {"series": series, "curve": rows[-2:], "dfr": {"value": 2.5, "since": "2026-09-16"}}


class Markets(unittest.TestCase):
    def test_crosses_are_computed_from_the_ecb_rates_and_changes_use_the_previous_day(self):
        r = {x["k"]: x for x in markets.rows(data(), markets.RAIL)}
        self.assertEqual(r["EUR/USD"]["v"], "1.1000")
        self.assertEqual(r["USD/JPY"]["v"], "150.00")
        self.assertEqual(r["GBP/USD"]["v"], "1.2500")
        self.assertEqual(r["USD/JPY"]["src"], "Calculated from ECB reference rates")
        self.assertIn("up", r["EUR/USD"]["chg"])  # 1.09 -> 1.10
        self.assertIn("chg up", r["EUR/USD"]["chg"])
        self.assertIn("chg down", r["US 10-year"]["chg"])  # 4.90 -> 4.85
        self.assertEqual(r["US 10-year"]["date"], "25 Nov 2026")

    def test_no_energy_rows_without_data_and_never_a_pending_row(self):
        html = markets.rates_box(data()) + markets.strip(data()) + markets.cards(data())
        for word in ("Brent", "WTI", "gasoline", "Pending"):
            self.assertNotIn(word, html)
        self.assertIn("Sources: ECB statistics; U.S. Department of the Treasury.", markets.attribution(data()))

    def test_energy_rows_appear_in_order_with_sparkline_arrow_and_attribution(self):
        m = data(True)
        order = [r["k"] for r in markets.rows(m, markets.RAIL)]
        self.assertEqual(order, ["EUR/USD", "USD/JPY", "GBP/USD", "Brent", "WTI", "US gasoline", "US 10-year"])
        box = markets.rates_box(m)
        self.assertIn("<svg class=\"spark\"", box)
        self.assertIn("▲", box)
        self.assertIn("▼", box)  # WTI fell
        self.assertIn("$72.40", box)
        self.assertIn("U.S. Energy Information Administration", markets.attribution(m))
        strip = markets.strip(m)
        self.assertIn("US gasoline", strip)
        self.assertNotIn("WTI", strip)  # the strip carries five series only
        self.assertNotIn("USD/CNY", markets.rates_box(m))  # on the numbers page only
        self.assertIn("What it is.", markets.cards(m))

    def test_load_drops_eia_series_without_a_key_and_keeps_last_good_blocks(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "markets.json"
            old = data(True)
            f.write_text(json.dumps({"series": {k: v for k, v in old["series"].items() if k.startswith("ust")}}))
            fresh = {"series": {k: v for k, v in old["series"].items() if k in ("eurusd", "brent")}}
            env = {k: v for k, v in os.environ.items() if k != "EIA_API_KEY"}
            with mock.patch.object(markets, "FILE", f), mock.patch.object(markets, "fetch", return_value=fresh), mock.patch.dict(os.environ, env, clear=True):
                m = markets.load(live=True)
                self.assertEqual(sorted(m["series"]), ["eurusd", "ust10", "ust2"])  # last-good yields kept, fresh rate added, Brent dropped
                self.assertIn("brent", json.loads(f.read_text())["series"])  # kept on disk for a build that has the key
                os.environ["EIA_API_KEY"] = "test-key"
                self.assertIn("brent", markets.load(live=True)["series"])

    def test_context_box_only_when_a_series_matches(self):
        m = data(True)
        p = {"headlines": ["ECB holds rates as inflation cools"], "dek": ""}
        self.assertIn("Euro-area deposit facility rate", markets.context_for(p, m))
        self.assertIn("Source: ECB statistics.", markets.context_for(p, m))
        self.assertIn("US 10-year", markets.context_for({"headlines": ["Fed chair signals a pause"], "dek": ""}, m))
        self.assertIn("Brent", markets.context_for({"headlines": ["Oil jumps as OPEC cuts output"], "dek": ""}, m))
        self.assertEqual(markets.context_for({"headlines": ["SAP explores job cuts"], "dek": "Restructuring."}, m), "")
        self.assertEqual(markets.context_for(p, None), "")
