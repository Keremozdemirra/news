"""Peer groups for the company quiz: companies of the same kind and roughly the same weight.

A quiz option has to be a fair guess. "Guess the company" once offered SAP, Australian Open, 1Password and OpenAI:
a tournament is not a company, and a password manager is no peer of a software giant. Each group below holds
companies a reader would accept as alternatives to one another: same sector, same order of size, all real and
currently trading or operating under that name (checked 2026-11-27). A company outside every group gets no quiz.

ALIASES ties names that point at one owner, so a quiz never offers Google beside Alphabet or Instagram beside Meta:
either would be a second right answer.
"""
import re
import unicodedata

GROUPS = {
    "frontier AI labs": ["OpenAI", "Anthropic", "Google DeepMind", "xAI", "Mistral", "Cohere", "DeepSeek", "Moonshot AI"],
    "AI startups": ["ElevenLabs", "Perplexity", "Character.AI", "Hugging Face", "Runway", "Synthesia", "Anysphere",
                    "Harvey", "Glean", "Scale AI", "Midjourney", "Stability AI", "Suno", "Lovable"],
    "big tech": ["Apple", "Microsoft", "Alphabet", "Google", "Amazon", "Meta", "Netflix", "Tesla"],
    "chipmakers": ["Nvidia", "AMD", "Intel", "Qualcomm", "Broadcom", "TSMC", "Arm", "Micron", "Samsung Electronics",
                   "SK Hynix", "Marvell"],
    "chip equipment": ["ASML", "Applied Materials", "Lam Research", "KLA", "Tokyo Electron"],
    "enterprise software": ["SAP", "Oracle", "Salesforce", "Adobe", "ServiceNow", "Workday", "IBM", "Intuit"],
    "cloud and data": ["Snowflake", "Databricks", "Palantir", "Datadog", "MongoDB", "Cloudflare", "CoreWeave"],
    "cybersecurity": ["CrowdStrike", "Palo Alto Networks", "Fortinet", "Zscaler", "Okta", "1Password", "Wiz",
                      "SentinelOne"],
    "AI servers and hardware": ["Supermicro", "Dell", "HPE", "Lenovo", "Foxconn", "Cisco"],
    "consumer apps": ["Uber", "Airbnb", "DoorDash", "Spotify", "Snap", "Pinterest", "Reddit", "Lyft", "Duolingo"],
    "social networks": ["Meta", "TikTok", "Snap", "Pinterest", "Reddit", "X", "Discord"],
    "fintech": ["Stripe", "Revolut", "Klarna", "PayPal", "Block", "Adyen", "Robinhood", "Coinbase", "Chime", "Wise"],
    "card networks": ["Visa", "Mastercard", "American Express"],
    "US banks": ["JPMorgan Chase", "Goldman Sachs", "Morgan Stanley", "Bank of America", "Citigroup", "Wells Fargo"],
    "European banks": ["HSBC", "Barclays", "UBS", "Deutsche Bank", "BNP Paribas", "Santander", "ING", "Lloyds",
                       "Société Générale", "UniCredit", "Commerzbank"],
    "asset managers": ["BlackRock", "Vanguard", "Blackstone", "KKR", "Apollo", "Carlyle", "Fidelity", "State Street"],
    "automakers": ["Volkswagen", "Toyota", "General Motors", "Ford", "Stellantis", "BMW", "Mercedes-Benz", "Hyundai",
                   "Honda", "Renault", "Nissan"],
    "EV makers": ["Tesla", "BYD", "Rivian", "Lucid", "Nio", "Xpeng", "Polestar", "Li Auto"],
    "airlines": ["Lufthansa", "Air France-KLM", "IAG", "Ryanair", "easyJet", "Delta", "United Airlines",
                 "American Airlines", "Emirates", "Norse Atlantic", "Wizz Air", "Southwest"],
    "plane makers": ["Boeing", "Airbus", "Embraer", "Bombardier"],
    "defence": ["Lockheed Martin", "RTX", "Northrop Grumman", "General Dynamics", "BAE Systems", "Rheinmetall",
                "Thales", "Leonardo", "Saab", "Anduril"],
    "space": ["SpaceX", "Blue Origin", "Rocket Lab", "Arianespace", "Eutelsat", "SES", "AST SpaceMobile"],
    "oil and gas": ["ExxonMobil", "Chevron", "Shell", "BP", "TotalEnergies", "Equinor", "Eni", "Saudi Aramco",
                    "ConocoPhillips"],
    "utilities": ["NextEra Energy", "Iberdrola", "Enel", "EDF", "E.ON", "RWE", "Engie", "Orsted"],
    "pharma": ["Pfizer", "Novo Nordisk", "Eli Lilly", "Roche", "Novartis", "AstraZeneca", "Merck", "Sanofi", "GSK",
               "Bayer", "Johnson & Johnson", "AbbVie", "Moderna"],
    "retail": ["Walmart", "Target", "Costco", "Amazon", "Tesco", "Carrefour", "Aldi", "Lidl", "Kroger", "Home Depot"],
    "fashion": ["Nike", "Adidas", "Puma", "Inditex", "H&M", "Uniqlo", "Lululemon", "Shein", "Zalando"],
    "luxury": ["LVMH", "Hermès", "Kering", "Richemont", "Prada", "Burberry", "Chanel", "Moncler"],
    "consumer goods": ["Procter & Gamble", "Unilever", "Nestlé", "PepsiCo", "Coca-Cola", "L'Oréal", "Danone",
                       "Colgate-Palmolive", "Kraft Heinz", "Mondelez"],
    "restaurants": ["McDonald's", "Starbucks", "Chipotle", "Yum Brands", "Restaurant Brands International", "Domino's",
                    "Denny's", "Wendy's"],
    "tobacco and drinks": ["Altria", "Philip Morris", "British American Tobacco", "Diageo", "AB InBev", "Heineken",
                           "Pernod Ricard"],
    "media and streaming": ["Disney", "Netflix", "Warner Bros. Discovery", "Paramount", "Comcast", "Sony", "Spotify"],
    "games": ["Nintendo", "Sony", "Microsoft", "Electronic Arts", "Take-Two", "Ubisoft", "Roblox", "Epic Games",
              "Tencent"],
    "telecoms": ["Verizon", "AT&T", "T-Mobile", "Deutsche Telekom", "Vodafone", "Orange", "Telefónica", "BT"],
    "Chinese tech": ["Alibaba", "Tencent", "Baidu", "JD.com", "ByteDance", "Xiaomi", "Huawei", "PDD Holdings",
                     "Meituan"],
    "consulting and audit": ["McKinsey", "Boston Consulting Group", "Bain", "Accenture", "Deloitte", "PwC", "EY",
                             "KPMG"],
    "shipping and logistics": ["Maersk", "DHL", "UPS", "FedEx", "Hapag-Lloyd", "MSC", "CMA CGM"],
    "crypto": ["Coinbase", "Binance", "Kraken", "Tether", "Circle", "Gemini", "OKX"],
}

ALIASES = [
    {"alphabet", "google", "google deepmind", "deepmind", "youtube", "waymo"},
    {"meta", "facebook", "instagram", "whatsapp", "threads"},
    {"microsoft", "github", "linkedin", "xbox"},
    {"amazon", "aws", "whole foods", "zoox"},
    {"x", "xai", "twitter", "spacex", "tesla"},  # one owner: a quiz must not set them against each other
    {"bytedance", "tiktok"},
    {"jpmorgan chase", "jpmorgan", "chase"},
    {"air france-klm", "air france", "klm"},
    {"iag", "british airways", "iberia", "aer lingus", "vueling"},
    {"lvmh", "dior", "louis vuitton", "tiffany", "sephora"},
    {"kering", "gucci", "saint laurent", "balenciaga"},
    {"inditex", "zara"},
    {"uniqlo", "fast retailing"},
    {"block", "square", "cash app", "afterpay"},
    {"stellantis", "fiat", "chrysler", "peugeot", "jeep"},
    {"volkswagen", "audi", "porsche", "skoda", "seat"},
    {"renault", "nissan"},
    {"sony", "playstation"},
    {"disney", "espn", "hulu", "marvel", "pixar"},
    {"comcast", "nbcuniversal", "sky"},
    {"aldi", "lidl"},  # distinct owners, one name in many readers' heads; never offered together
    {"anysphere", "cursor"},
    {"rtx", "raytheon", "pratt & whitney", "collins aerospace"},
    {"warner bros. discovery", "hbo", "cnn"},
]


def norm(name):
    """Lower case, no accents, no legal form, single spaces: "Nestlé S.A." and "nestle" compare equal."""
    flat = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode().lower()
    flat = re.sub(r"\b(inc|corp|corporation|plc|ag|se|sa|s\.a|nv|ltd|llc|co|group|holdings)\b\.?", " ", flat)
    return " ".join(re.sub(r"[^a-z0-9&'.+-]+", " ", flat).split()).strip(" .")


def _family(name):
    n = norm(name)
    for fam in ALIASES:
        if n in fam:
            return fam
    return {n}


def related(a, b):
    """The same company, or two names under one owner."""
    return norm(a) == norm(b) or norm(b) in _family(a)


def groups_of(name):
    n = norm(name)
    return [g for g, members in GROUPS.items() if n in {norm(m) for m in members}]


def peers(name):
    """Companies a reader would accept in place of `name`, from its groups in table order, never `name` itself or
    anything under the same owner. [] when the company is in no group."""
    out = []
    for g in groups_of(name):
        for m in GROUPS[g]:
            if not related(name, m) and not any(related(m, o) for o in out):
                out.append(m)
    return out
