"""Python port of the Label Checker's findSugars + splitIngredients (site: /tools/label-checker/).
The alias table is imported from the site build script, so the study and the tool use identical rules."""
import json
import sys
from pathlib import Path
import regex as re

# The site build script is the source of truth; aliases.json is its exported copy for everyone else.
try:
    sys.path.insert(0, r"C:/Users/devna/devnarsinghani-site-oct20")
    from build_site import SUGAR_ALIASES  # noqa: E402
except ImportError:
    SUGAR_ALIASES = [(a["name"], a["description"], a["patterns"], a["kind"])
                     for a in json.loads((Path(__file__).parent / "aliases.json").read_text(encoding="utf-8"))]

RULES = []
for i, (name, _desc, pats, kind) in enumerate(SUGAR_ALIASES):
    for p in pats:
        RULES.append((i, re.compile(r"(^|[^a-z0-9])(" + p.replace(" ", r"\s+") + r")(?![a-z])", re.I)))

NAMES = [a[0] for a in SUGAR_ALIASES]
KINDS = [a[3] for a in SUGAR_ALIASES]


def find_sugars(text):
    hits = []
    for i, rx in RULES:
        pos = 0
        while True:
            m = rx.search(text, pos)
            if not m:
                break
            start = m.start(2)
            end = m.end(2)
            hits.append((start, end, i))
            pos = end
    hits.sort(key=lambda h: (h[0], -(h[1] - h[0])))
    kept, last = [], -1
    low = text.lower()
    for start, end, i in hits:
        if start < last:
            continue
        word = low[start:end]
        after = low[end:end + 16]
        before = low[max(0, start - 24):start]
        if re.match(r"^[\s-]*free", after):
            continue
        # same skip rules as the site tool's findSugars, in the same order
        if re.search(r"no\s+added\s*$", before) or re.search(r"naturally\s+occur+ing\s*$", before):
            continue
        if re.match(r"^\s*(flavou?r|essence)", after):
            continue
        ob, cb = text.rfind("(", 0, start), text.rfind(")", 0, start)
        if ob > cb and re.search(r"flavou?r[a-z ]*[:\s]*$", text[max(0, ob - 40):ob], re.I):
            continue
        if start > 0 and text[start - 1] == "-" and end < len(text) and text[end] == "-":
            continue
        if re.match(r"^sugars?$", word):
            if re.match(r"^\s*alcohols?", after):
                continue
            if re.match(r"^[\s-]*cane[\s-]+(fibre|fiber|bagasse)", after):
                continue
        kept.append((start, end, i))
        last = end
    return kept


def top_items(text):
    """Top-level ingredient spans (start, end), split on , and ; outside brackets; leading 'Ingredients:' dropped."""
    start = 0
    m = re.match(r"^\s*ingredients?\s*(?:[:\-]|\n)", text, re.I)
    if m:
        start = m.end()
    items, depth, frm = [], 0, start
    for k in range(start, len(text) + 1):
        c = text[k] if k < len(text) else ","
        if c in "([{":
            depth += 1
        elif c in ")]}" and depth:
            depth -= 1
        elif c in ",;" and depth == 0:
            if text[frm:k].strip():
                items.append((frm, k))
            frm = k + 1
    return items


def analyse(text):
    """-> dict: distinct sugar alias groups, whether one is a top-3 ingredient (outside brackets), item count."""
    hits = find_sugars(text)
    sugar_hits = [h for h in hits if KINDS[h[2]] == "sugar"]
    groups = sorted({h[2] for h in sugar_hits})
    items = top_items(text)
    top3 = items[:3]

    def in_top3(h):
        for s, e in top3:
            if s <= h[0] < e:
                # inside a bracket of that item does not count
                seg = text[s:h[0]]
                if seg.count("(") + seg.count("[") > seg.count(")") + seg.count("]"):
                    return False
                return True
        return False

    return {
        "sugar_groups": groups,
        "n_sugar_names": len(groups),
        "sugar_in_top3": any(in_top3(h) for h in sugar_hits),
        "n_items": len(items),
        "has_maltodextrin": any(KINDS[h[2]] == "starch" for h in hits),
    }


if __name__ == "__main__":
    tests = {
        "Sugar, dextrose, acidity regulator, tea extract, lemon flavour": (2, True),
        "Oats, sugar-cane fibre, salt": (0, False),
        "Wheat flour, palm oil, masala [salt, sugar, spices], dextrose": (2, False),
        "Milk solids, unsweetened condensed milk, cocoa": (0, False),
        "Apple and lemon juice concentrate, water": (1, True),
        "No added sugar. Ingredients: dates, almonds": (0, False),
        "Sweetened condensed skimmed milk, cocoa": (1, True),
        "Ragi flour, khaand, salt": (1, True),
        "Yoghurt, gurgaon spice": (0, False),
        # false positives found by the 1 Oct audit
        "Milk, Fructose Oligo Saccharide, cardamom": (0, False),
        "Oats, Nature-Identical Flavouring substance (Honey), salt": (0, False),
        "Milk, sugar, artificial flavouring substances (kulfi, condensed milk, rose)": (1, True),
        "Milk, coconut pulp. Contains Naturally Occuring Sugars In Milk. NO ADDED SUCROSE.": (0, False),
        "Milk solids, cocoa. Registration No.: PR-10-JAM-05": (0, False),
        "Pasteurized Milk, Curd & Lemon Juice Concentrate": (0, False),
        "Water, apple and lemon juice concentrate": (1, True),
        "Wheat flour, honey flavour, salt": (0, False),
        "Wheat flour, honey, salt": (1, True),
    }
    bad = 0
    for t, (n, top) in tests.items():
        r = analyse(t)
        ok = r["n_sugar_names"] == n and r["sugar_in_top3"] == top
        bad += not ok
        print("OK " if ok else "BAD", t, "->", r["n_sugar_names"], r["sugar_in_top3"], [NAMES[g] for g in r["sugar_groups"]])
    print("failures:", bad)
