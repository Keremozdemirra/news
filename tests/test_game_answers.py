"""No valid answer may be unknown: the Topfloor answer lists and the Tickerflip word list, tried with awkward names.

A name on the left must be recognised and mean the entry whose label contains the text on the right. The made-up
names at the end of each list must stay unknown. The same guesses are then run through js/match.js under node, when
node is installed, so the player's device and this file agree.
"""
import json, shutil, subprocess, sys, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOP = ROOT / "games" / "topfloor"
sys.path.insert(0, str(TOP))
import names  # noqa: E402

KNOWN = {
    "bank": {"Bayerische Bank": "BayernLB", "BayernLB": "BayernLB", "bayern lb": "BayernLB", "Bayerische Landesbank": "BayernLB",
             "Société Générale": "Société Générale", "societe generale": "Société Générale", "SocGen": "Société Générale",
             "Deutsche Bank AG": "Deutsche Bank", "Deutshce Bank": "Deutsche Bank", "HSBC Holdings plc": "HSBC", "JP Morgan": "JPMorgan",
             "J.P. Morgan & Co": "JPMorgan", "Ziraat Bankası": "Ziraat", "Is Bankasi": "İşbank", "LBBW": "Baden-Württemberg",
             "Landesbank Baden-Wuerttemberg": "Baden-Württemberg", "Lehman Brothers": "Lehman", "Crédit Agricole": "Agricole", "Commerzbank": "Commerzbank"},
    "central-bank": {"Fed": "Federal Reserve", "ECB": "European Central Bank", "Bundesbank": "German Federal Bank", "TCMB": "Turkey",
                     "Türkiye Cumhuriyet Merkez Bankası": "Turkey", "BoJ": "Japan", "Banque de France": "France", "Riksbank": "Riksbank"},
    "carmaker": {"Tesla": "Tesla", "Tesla, Inc.": "Tesla", "BMW": "BMW", "Bayerische Motoren Werke": "BMW", "VW": "Volkswagen", "Mercedes": "Mercedes",
                 "Škoda": "Škoda", "Skoda Auto": "Škoda", "Citroen": "Citroën", "Rolls Royce": "Rolls-Royce", "Togg": "Togg", "Ferrari": "Ferrari", "Tofas": "Tofaş"},
    "airline": {"THY": "Turkish Airlines", "Türk Hava Yolları": "Turkish Airlines", "Luftansa": "Lufthansa", "LH": "Lufthansa", "easy jet": "easyJet",
                "British Airways": "British Airways", "Pan Am": "Pan Am", "KLM": "KLM", "Qantas": "Qantas", "Pegasus": "Pegasus"},
    "exchange": {"NYSE": "New York Stock Exchange", "BIST": "Borsa Istanbul", "Borsa İstanbul": "Borsa Istanbul", "Frankfurter Wertpapierbörse": "Frankfurt",
                 "Deutsche Boerse": "Deutsche Börse", "LSE": "London Stock Exchange", "Nasdaq": "Nasdaq"},
    "currency": {"TL": "Turkish lira", "Türk lirası": "Turkish lira", "USD": "United States dollar", "dollar": "dollar", "EUR": "euro", "D-Mark": "Deutsche Mark",
                 "zloty": "złoty", "pound": "pound", "yen": "yen", "Swiss franc": "Swiss franc"},
    "crypto": {"BTC": "Bitcoin", "ether": "Ethereum", "doge": "Dogecoin", "USDT": "Tether", "Solana": "Solana"},
    "supermarket": {"Kaufland": "Kaufland", "Şok": "Şok", "Sok": "Şok", "BİM": "BIM", "Aldi Süd": "Aldi", "ALDI Sued": "Aldi", "Walmart": "Walmart",
                    "Sainsburys": "Sainsbury", "Migros": "Migros", "Rewe": "REWE", "Carrefour": "Carrefour", "Costco": "Costco"},
    "index": {"S&P 500": "S&P 500", "S and P 500": "S&P 500", "SP500": "S&P 500", "Dow Jones": "Dow Jones", "nikkei": "Nikkei", "FTSE 100": "FTSE 100",
              "BIST 100": "BIST 100", "Euro Stoxx 50": "STOXX 50", "DAX": "DAX"},
    "fast-food": {"McDonalds": "McDonald's", "mc donalds": "McDonald's", "Kentucky Fried Chicken": "KFC", "Dominos Pizza": "Domino's", "Wendy's": "Wendy's",
                  "In-N-Out": "In-N-Out", "Burger King": "Burger King"},
    "publisher": {"EA": "Electronic Arts", "Activision Blizzard": "Activision Blizzard", "Take-Two": "Take-Two", "Take Two Interactive": "Take-Two",
                  "SEGA": "Sega", "Bandai Namco": "Bandai Namco", "Nintendo": "Nintendo", "Ubisoft": "Ubisoft"},
    "brewery": {"Efes": "Efes", "Anadolu Efes": "Efes", "Tuborg": "Tuborg", "Hofbräu München": "Hofbräuhaus", "Hofbrau": "Hofbräuhaus", "Becks": "Beck's",
                "Augustiner-Bräu": "Augustiner", "Heineken": "Heineken", "Pilsner Urquell": "Prazdroj", "Guinness": "Guinness"},
}
UNKNOWN = {"bank": ["xyzzy bank", "pizza", "qq"], "carmaker": ["spoon motors"], "airline": ["banana air"], "supermarket": ["banana mart"],
           "currency": ["flurbo"], "brewery": ["zzyzx brewing"], "exchange": ["narnia stock exchange"], "central-bank": ["Bank of Narnia"]}

# A kind of thing is not a name: the industry and product routes bring these in, extras.json "drop" takes them out.
KINDS = {"supermarket": ["supermarket", "hypermarket"], "bank": ["investment bank", "banking services"], "brewery": ["brewery", "brewing", "homebrewing"],
         "carmaker": ["automobile manufacturer", "automotive industry", "kit car"], "publisher": ["video game publisher", "video game developer"],
         "fast-food": ["fast casual restaurant"], "crypto": ["decentralized finance"]}
for _pid, _c in KINDS.items():
    UNKNOWN.setdefault(_pid, []).extend(_c)


def entries(pid):
    return json.loads((TOP / "assets" / "data" / "lists" / f"{pid}.json").read_text())["entries"]


class TopfloorAnswers(unittest.TestCase):
    def test_every_prompt_has_a_list_and_it_is_not_thin(self):
        from build_lists import POOL
        for pid, _, _ in POOL:
            self.assertGreaterEqual(len(entries(pid)), 150, pid)
            self.assertIn(pid, KNOWN, f"{pid} has no tricky names in this test")

    def test_awkward_spellings_of_real_answers_are_recognised(self):
        for pid, cases in KNOWN.items():
            e = entries(pid)
            for guess, want in cases.items():
                i = names.find(e, pid, guess)
                self.assertIsNotNone(i, f"{pid}: {guess!r} is a real answer and was not recognised")
                self.assertIn(want.lower(), e[i][0].lower(), f"{pid}: {guess!r} was read as {e[i][0]!r}")

    def test_made_up_answers_stay_unknown(self):
        for pid, cases in UNKNOWN.items():
            e = entries(pid)
            for guess in cases:
                self.assertIsNone(names.find(e, pid, guess), f"{pid}: {guess!r}")

    def test_folding(self):
        self.assertEqual(names.variants("Müller & Söhne GmbH"), ["mullersohnegmbh", "mullersohne", "muellersoehnegmbh", "muellersoehne"])
        self.assertEqual(names.variants("Bayern LB"), names.variants("BayernLB"))
        self.assertEqual(names.variants("McDonald’s"), names.variants("mcdonalds"))
        self.assertEqual(names.core("bayerische landesbank", "bank"), names.core("bayerische bank", "bank"))
        self.assertTrue(names.dl1("lufthansa", "luftansa") and names.dl1("deutsche", "deutshce") and not names.dl1("abcd", "abxy"))

    def test_a_typo_is_forgiven_only_on_a_long_name(self):
        e = entries("crypto")
        self.assertIsNotNone(names.find(e, "crypto", "Etherium"))
        self.assertIsNone(names.find(e, "crypto", "xtc"))          # three letters: one letter off BTC is another word

    def test_todays_puzzle_points_at_lists_that_exist(self):
        d = json.loads((TOP / "assets" / "data" / "today.json").read_text())
        self.assertEqual(len(d["prompts"]), 7)
        self.assertEqual(sorted(d["match"]["legal"]), sorted(names.LEGAL))
        for p in d["prompts"]:
            self.assertTrue("entries" in p or (TOP / p["list"]).exists(), p["id"])

    @unittest.skipUnless(shutil.which("node"), "node is not installed")
    def test_the_players_device_agrees(self):
        cases = [[pid, g] for pid, c in KNOWN.items() for g in c] + [[pid, g] for pid, c in UNKNOWN.items() for g in c]
        js = """
import { readFileSync } from 'node:fs';
import { matcher } from '%s/js/match.js';
const rules = JSON.parse(readFileSync('%s/assets/data/today.json')).match, gen = %s, out = [], ms = {};
for (const [pid, g] of %s) {
  const e = JSON.parse(readFileSync(`%s/assets/data/lists/${pid}.json`)).entries;
  ms[pid] ??= matcher(e, gen[pid].split(' ').filter(Boolean), rules);
  const i = ms[pid](g); out.push(i === null ? null : e[i][0]);
}
console.log(JSON.stringify(out));""" % (TOP, TOP, json.dumps(names.GENERIC), json.dumps(cases), TOP)
        r = subprocess.run(["node", "--input-type=module", "-e", js], capture_output=True, text=True, timeout=120)
        self.assertEqual(r.returncode, 0, r.stderr[-400:])
        got = json.loads(r.stdout)
        for (pid, g), label in zip(cases, got):
            i = names.find(entries(pid), pid, g)
            self.assertEqual(label, None if i is None else entries(pid)[i][0], f"{pid}: {g!r} differs between names.py and match.js")


class TickerflipWords(unittest.TestCase):
    def test_plain_business_words_and_company_names_are_valid_guesses(self):
        d = ROOT / "games" / "tickerflip" / "assets" / "data"
        words = set((d / "words.txt").read_text().split()) | set((d / "words-more.txt").read_text().split())
        for w in "revenue shares stocks tariff merger equity fintech crypto nvidia tesla openai iphone layoffs buyback startup profit yields bonds google amazon toyota boeing airbus".split():
            self.assertIn(w, words, w)
        self.assertNotIn("zzzzz", words)


if __name__ == "__main__":
    unittest.main()
