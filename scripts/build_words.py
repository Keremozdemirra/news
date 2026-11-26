"""Builds assets-site/words.txt, the English words the daily word game accepts as guesses.

Source: the en_US Hunspell dictionary derived from SCOWL (http://wordlist.sourceforge.net, Kevin Atkinson, permissive
licence, notice in assets-site/words-NOTICE.txt). Its suffix rules are expanded here, so plurals and -ed/-ing forms
are included, then the list is cut to lowercase letters-only words of 4 to 7 letters, the lengths the game uses.
The game adds every word of the site's own articles on top, so a company name in the news is never rejected.

  python3 scripts/build_words.py en_US.dic en_US.aff
"""
import re
import sys
from pathlib import Path

dic, aff = (Path(a).read_text(encoding="utf-8").splitlines() for a in sys.argv[1:3])
rules = {}  # flag -> [(strip, add, condition)]
for line in aff:
    m = re.match(r"SFX\s+(\S)\s+(\S+)\s+(\S+)\s+(\S+)", line)
    if m and m.group(2) != "Y" and m.group(2) != "N":
        flag, strip, add, cond = m.groups()
        add = add.split("/")[0]
        rules.setdefault(flag, []).append((("" if strip == "0" else strip), ("" if add == "0" else add), re.compile(cond + "$")))
words = set()
for line in dic[1:]:
    stem, _, flags = line.partition("/")
    if not stem.islower() or not stem.isalpha():
        continue
    words.add(stem)
    for f in flags.split()[0] if flags else "":
        for strip, add, cond in rules.get(f, ()):
            if cond.search(stem) and stem.endswith(strip):
                words.add(stem[:len(stem) - len(strip)] + add)
out = sorted(w for w in words if re.fullmatch(r"[a-z]{4,7}", w))
dest = Path(__file__).resolve().parent.parent / "assets-site" / "words.txt"
dest.write_text("\n".join(out) + "\n")
print(len(out), "words ->", dest)
