import json
import re
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
        self.assertNotIn("US gasoline", strip)  # a weekly US retail price is not a headline market
        self.assertLess(strip.index("EUR/USD"), strip.index("Brent"))
        self.assertLess(strip.index("Brent"), strip.index("US 10-year"))
        self.assertNotIn("USD/CNY", markets.rates_box(m))  # on the numbers page only
        self.assertIn("What it is.", markets.cards(m))

    def test_load_keeps_last_good_blocks_and_does_not_replace_a_series_with_older_data(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "markets.json"
            old = data(True)
            f.write_text(json.dumps({"series": {k: v for k, v in old["series"].items() if k.startswith("ust") or k == "brent"}}))
            older = [["2026-11-01", 70.0], ["2026-11-02", 71.0]]
            fresh = {"series": {"eurusd": old["series"]["eurusd"], "brent": older, "wti": old["series"]["wti"]}}
            with mock.patch.object(markets, "FILE", f), mock.patch.object(markets, "fetch", return_value=fresh):
                m = markets.load(live=True)
                self.assertEqual(sorted(m["series"]), ["brent", "eurusd", "ust10", "ust2", "wti"])  # no key needed for energy rows
                self.assertEqual(m["series"]["brent"][-1][0], "2026-11-25")  # the older fresh copy did not replace the kept one
                self.assertIn("wti", json.loads(f.read_text())["series"])
                stamp = json.loads(f.read_text())["fetched"]
                with mock.patch.object(markets, "fetch", return_value=fresh):
                    markets.load(live=True)
                self.assertEqual(json.loads(f.read_text())["fetched"], stamp)  # nothing moved: the file is left as it was

    def test_dnav_pages_parse_to_dated_values(self):
        fx = Path(__file__).parent / "fixtures"
        for sid, name, last in (("RBRTE", "eia_rbrte_d.html", ("2026-11-24", 91.8)), ("RWTC", "eia_rwtc_d.html", ("2026-11-24", 82.24)),
                                ("RNGWHHD", "eia_rngwhhd_d.html", ("2026-11-24", 3.3)), ("EMM_EPMR_PTE_NUS_DPG", "eia_gasoline_w.html", ("2026-11-23", 3.642))):
            pts = markets.parse_dnav((fx / name).read_text(), markets.DNAV[sid][1])
            self.assertEqual(pts[-1], last, sid)
            self.assertEqual(pts, sorted(pts))
        brent = dict(markets.parse_dnav((fx / "eia_rbrte_d.html").read_text(), "daily"))
        self.assertEqual([brent[d] for d in ("2026-11-16", "2026-11-17", "2026-11-18", "2026-11-19", "2026-11-20")], [92.90, 92.94, 92.88, 95.17, 92.76])
        self.assertIn("2025-12-29", brent)  # a week that runs over the new year is dated from its Monday
        self.assertIn("2026-01-02", brent)
        self.assertEqual(dict(markets.parse_dnav((fx / "eia_gasoline_w.html").read_text(), "weekly"))["2025-12-29"], 2.811)

    def test_fetch_falls_back_to_dnav_when_the_api_fails_and_has_no_key_path(self):
        fx = Path(__file__).parent / "fixtures"
        pages = {"RBRTED.htm": "eia_rbrte_d.html", "RWTCD.htm": "eia_rwtc_d.html", "RNGWHHDD.htm": "eia_rngwhhd_d.html", "NUS_DPG&f=W": "eia_gasoline_w.html"}

        def get(url, timeout=20, retry_curl=True):
            if "api.eia.gov" in url:
                raise OSError("504")
            for k, v in pages.items():
                if url.endswith(k):
                    return (fx / v).read_text()
            raise OSError("not reachable in the test")
        for env in ({}, {"EIA_API_KEY": "test-key"}):
            with mock.patch.object(markets, "_get", get), mock.patch.dict(os.environ, env):
                got = markets.fetch()["series"]
            self.assertEqual({k: got[k][-1] for k in ("brent", "wti", "henryhub", "gasoline")},
                             {"brent": ["2026-11-24", 91.8], "wti": ["2026-11-24", 82.24], "henryhub": ["2026-11-24", 3.3], "gasoline": ["2026-11-23", 3.642]})

    def test_context_box_only_when_a_series_matches(self):
        m = data(True)
        p = {"headlines": ["ECB holds rates as inflation cools"], "dek": ""}
        self.assertIn("Euro-area deposit facility rate", markets.context_for(p, m))
        self.assertIn("Source: ECB statistics.", markets.context_for(p, m))
        self.assertIn("US 10-year", markets.context_for({"headlines": ["Fed chair signals a pause"], "dek": ""}, m))
        self.assertIn("Brent", markets.context_for({"headlines": ["Oil jumps as OPEC cuts output"], "dek": ""}, m))
        self.assertEqual(markets.context_for({"headlines": ["SAP explores job cuts"], "dek": "Restructuring."}, m), "")
        self.assertEqual(markets.context_for(p, None), "")


FIXTURES = Path(__file__).parent / "fixtures"


class Metals(unittest.TestCase):
    def pink(self):
        return markets.parse_pink((FIXTURES / "pink_sheet_mini.xlsx").read_bytes())

    def test_pink_sheet_parses_by_header_name_and_skips_unpublished_cells(self):
        got = self.pink()
        self.assertEqual(set(got), set(markets.METALS))
        self.assertEqual(got["gold"][-1], ("2026-10-01", 4105.0))
        self.assertEqual(got["aluminium"][-1], ("2026-10-01", 3061.0))
        self.assertEqual(got["ironore"][-1], ("2026-10-01", 90.8))
        self.assertEqual(len(got["tin"]), 13)  # one "…" cell left out, not read as zero
        self.assertEqual(got["gold"], sorted(got["gold"]))

    def test_the_download_link_is_read_from_the_page_not_hard_coded(self):
        page = '<a href="https://thedocs.worldbank.org/en/doc/abc123-0050012026/related/CMO-Historical-Data-Monthly.xlsx">Monthly</a>'
        self.assertTrue(markets.WB_LINK.search(page).group(0).endswith("CMO-Historical-Data-Monthly.xlsx"))
        with mock.patch.object(markets, "_get", return_value=page), mock.patch.object(markets, "_get_bytes", return_value=(FIXTURES / "pink_sheet_mini.xlsx").read_bytes()) as g:
            self.assertIn("copper", markets.pink())
        self.assertIn("abc123", g.call_args[0][0])
        with mock.patch.object(markets, "_get", return_value="<html>moved</html>"), self.assertRaises(ValueError):
            markets.pink()

    def test_metals_are_labelled_as_monthly_averages_with_thousands_separators(self):
        m = data()
        m["series"].update({k: [list(x) for x in v] for k, v in self.pink().items()})
        r = {x["k"]: x for x in markets.rows(m, markets.METALS)}
        self.assertEqual(r["Gold"]["v"], "$4,105")
        self.assertEqual(r["Gold"]["date"], "Oct 2026 avg")
        self.assertEqual(r["Silver"]["v"], "$57.00")
        self.assertIn("chg down", r["Gold"]["chg"])  # 4319 -> 4105
        html = markets.cards(m, markets.METALS)
        self.assertIn("Oct 2026 avg", html)
        self.assertIn("monthly averages", html)
        self.assertIn("World Bank, Commodity Price Data (The Pink Sheet), CC BY 4.0", html)
        self.assertNotIn("Series date 1 ", html)

    def test_metals_stay_out_of_the_rail_and_the_other_attribution(self):
        m = data(True)
        m["series"].update({k: [list(x) for x in v] for k, v in self.pink().items()})
        self.assertNotIn("Gold", markets.rates_box(m))
        self.assertNotIn("World Bank", markets.attribution(m))
        self.assertNotIn("Gold", markets.cards(m))

    def test_the_strip_puts_gold_third_and_marks_monthly_averages(self):
        m = data(True)
        m["series"].update({k: [list(x) for x in v] for k, v in self.pink().items()})
        strip = markets.strip(m)
        labels = re.findall(r'<span class="sl">([^<]+)</span>', strip)
        self.assertEqual(labels[:3], ["EUR/USD", "Brent", "Gold"])
        self.assertIn('$4,105</b> <small class="sd">Oct avg</small>', strip)
        self.assertNotIn("avg", strip.split("Gold")[0])  # daily series carry no month tag
        self.assertIn('href="/numbers/"', strip)  # the CC BY credit for the Pink Sheet is one link away

    def test_a_failed_pink_sheet_keeps_the_last_good_metals(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "m.json"
            f.write_text(json.dumps({"series": {"gold": [["2026-10-01", 4105.0]]}}))
            with mock.patch.object(markets, "FILE", f), mock.patch.object(markets, "fetch", return_value={}):
                self.assertEqual(markets.load()["series"]["gold"][-1][1], 4105.0)
