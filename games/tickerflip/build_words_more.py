#!/usr/bin/env python3
"""Widen the guess list: assets/data/words-more.txt. Run by hand: python3 build_words_more.py

words.txt (Hunspell en_US) misses plain words ("revenue") and knows no company. A guess is refused only when it
is not a word at all, so this adds, 4 to 7 letters each:
  1. Webster's Second (the public-domain /usr/share/dict/web2 that ships with BSD and macOS)
  2. one-word names and tickers of well-known companies and brands from Wikidata (CC0)
  3. a short hand list of business words too new for either
"""
import json, re, ssl, time, urllib.parse, urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
UA = {"User-Agent": "BoardreadGames/0.2 (https://boardread.news)", "Accept": "application/sparql-results+json"}
try:
    CTX = ssl.create_default_context(cafile="/etc/ssl/cert.pem")
except Exception:
    CTX = ssl.create_default_context()
HAND = """fintech crypto bitcoin altcoin iphone ipad android chatbot genai openai nvidia tesla spacex tiktok airbnb uber lyft
paypal stripe shopify netflix spotify zoom slack reddit meta google amazon apple alphabet oracle intel qualcomm broadcom arm asml
tsmc samsung huawei xiaomi tencent alibaba baidu byd nio rivian lucid porsche ferrari stellantis renault nissan toyota honda hyundai
boeing airbus ryanair lufthansa easyjet maersk walmart costco ikea nestle unilever danone loreal lvmh hermes kering zara inditex
adidas nike puma pfizer moderna novartis roche bayer sanofi astra glaxo merck lilly abbvie siemens bosch basf linde allianz axa
zurich hsbc barclays lloyds natwest ubs nomura citi chase goldman morgan wells visa amex klarna revolut monzo wise nasdaq nyse
ftse dax nikkei stoxx opec brent wti lng capex opex ebitda ebit forex repo spac etf reit saas ceo cfo coo cto gdp cpi ppi pmi
tariff tariffs selloff buyback buyout takeover spinoff startup unicorn layoff layoffs payroll payrolls upgrade bailout default
rouble ruble yuan renminbi rupee peso lira franc krona krone zloty dirham riyal shekel baht ringgit dong
copilot gemini claude llama grok mistral deepmind anthropic xai cursor figma canva notion atlassian adobe nvidia
telecom pharma biotech fintechs cleantech medtech proptech adtech edtech ecommerce esports blockchain stablecoin defi nft""".split()


def sparql(q):
    for i in range(4):
        try:
            r = urllib.request.Request("https://query.wikidata.org/sparql", data=urllib.parse.urlencode({"query": q}).encode(), headers=UA)
            with urllib.request.urlopen(r, timeout=120, context=CTX) as f:
                return json.load(f)["results"]["bindings"]
        except Exception:
            if i == 3:
                raise
            time.sleep(5 * (i + 1))


def main():
    have = set((HERE / "assets/data/words.txt").read_text().split())
    ok = re.compile(r"[a-z]{4,7}$")
    more = set()
    web2 = Path("/usr/share/dict/web2")
    if web2.exists():
        more |= {w for w in web2.read_text().split() if ok.match(w)}
    for cls in ("Q4830453", "Q891723", "Q6881511", "Q431289", "Q167037", "Q161726"):   # business, public company, enterprise, brand, corporation, multinational
        rows = sparql(f"""SELECT ?l ?t WHERE {{ ?x wdt:P31 wd:{cls}; wikibase:sitelinks ?s. FILTER(?s >= 12)
          ?x rdfs:label ?l. FILTER(lang(?l) = "en") OPTIONAL {{ ?x wdt:P249 ?t }} }}""")
        for b in rows:
            for text in (b["l"]["value"], b.get("t", {}).get("value", "")):
                for tok in re.split(r"[^A-Za-z]+", text):
                    if ok.match(tok.lower()):
                        more.add(tok.lower())
        print(cls, len(rows), flush=True)
        time.sleep(1)
    more |= {w for w in HAND if ok.match(w)}
    more -= have
    (HERE / "assets/data/words-more.txt").write_text("\n".join(sorted(more)) + "\n")
    print(len(more), "more words")


if __name__ == "__main__":
    main()
