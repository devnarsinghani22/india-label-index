"""Millet on the front, what on the back? Packaged foods with a millet word in the name (India Label Index, 17 October 2026).

Which products: every Open Food Facts India row (data/off_india.csv, one row per barcode) whose product name or generic
name carries a millet word (MILLET_RE: millet, ragi, nachni, jowar, bajra, sorghum, foxtail, kodo, kutki, barnyard,
proso, korra, navane, varagu, samak, kangni, siridhanya, shree anna and the like) and whose ingredient list the English
matchers can read (fats.english_list). Every one of those lists was read by hand; millet_labels.csv holds the verdicts,
and the script fails if a candidate is missing from it or it holds a code that is no longer a candidate.
  verdict  food        = a packaged food that sells itself on a millet word
           staple      = a plain grain, a plain flour or flour blend, or a grain-and-salt powder cooked like a flour
           supplement  = protein or supplement powder (left out, as in every Index study)
           unreadable  = the list's first item cannot be read
           duplicate:X = the same list as barcode X (counted once)
  first    = the first ingredient by weight, water ignored (a grain blend counts as its first named grain):
             millet, wheat (atta, maida, semolina), oats, sugar (any sugar name, jaggery included), corn, peanut
  millet_pct = the share of millet the label prints: the sum of the printed millet percentages, or a printed
             "millets (X%)" group. Blank when any millet in the list carries no percentage.
Photos of the front and the list were checked for the two rows quoted on their own (a ragi-named wafer, a ragi malt).
Measures, each with its count k and base n (round once, from k / n): the first ingredient; how many print the millet
share and its median; how many are half millet or more; a sugar listed (outside brackets) before the first millet
word; any added sugar
(sugar.py, the Label Checker rules); palm and hydrogenated fats (fats.py).
Category level only: brand names are never output (millet_labels.csv holds barcodes and plain product types).
Caveat: Open Food Facts is crowd-entered, not a random sample of what India buys; 49 foods is a small base.
Output: out/millet.json, out/millet_audit.txt. Run: python -I millet.py"""
import csv
import json
import re
import statistics as st
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from sugar import KINDS, find_sugars  # noqa: E402
from fats import HYDRO_RE, PALM_RE, english_list  # noqa: E402

csv.field_size_limit(2**31 - 1)
SRC = HERE / "data" / "off_india.csv"
LABELS = HERE / "millet_labels.csv"
OUT = HERE / "out"

MILLET_RE = re.compile(
    r"\b(millets?|ragi|nachni|nachani|jowar|jwar|jawar|bajra|bajri|sorghum|foxtail|kodo|kutki|barnyard|proso|korra|"
    r"navane|varagu|thinai|kambu|cholam|samak|sanwa|kangni|siridhanya|siri\s*dhanya|shree\s*anna|shri\s*anna|"
    r"brown\s*top)\b", re.I)
FIRSTS = ("millet", "wheat", "oats", "sugar", "corn", "peanut")


def candidates():
    seen, out = set(), {}
    with SRC.open(encoding="utf-8") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            code = row.get("code")
            if not code or code in seen:
                continue
            seen.add(code)
            name = (row.get("product_name") or "") + " | " + (row.get("generic_name") or "")
            if not MILLET_RE.search(name):
                continue
            ing = (row.get("ingredients_text") or row.get("ingredients_text_en") or "").strip()
            if english_list(ing):
                out[code] = ing
    return out


def depth_at(text, pos):
    d = 0
    for c in text[:pos]:
        if c in "([{":
            d += 1
        elif c in ")]}" and d:
            d -= 1
    return d


def sugar_before_millet(ing):
    """True when a sugar name (Label Checker rules) is an ingredient in its own right (outside brackets, so not the
    sugar inside a chocolate or a seasoning) and comes before the first millet word in the list."""
    m = MILLET_RE.search(ing)
    sugars = [h for h in find_sugars(ing) if KINDS[h[2]] == "sugar" and depth_at(ing, h[0]) == 0]
    return bool(sugars) and m is not None and sugars[0][0] < m.start()


def kn(k, n):
    return {"k": k, "n": n, "pct": round(100 * k / n, 1) if n else None}


def main():
    cands = candidates()
    labels = {r["code"]: r for r in csv.DictReader(LABELS.open(encoding="utf-8"))}
    missing, extra = sorted(set(cands) - set(labels)), sorted(set(labels) - set(cands))
    assert not missing and not extra, f"audit out of step with the data: missing {missing}, extra {extra}"
    for r in labels.values():
        if r["verdict"].startswith("duplicate:"):
            assert r["verdict"].split(":", 1)[1] in labels, r["code"]
        if r["verdict"] == "food":
            assert r["first"] in FIRSTS, (r["code"], r["first"])

    verdicts = Counter(r["verdict"].split(":")[0] for r in labels.values())
    foods = [r for r in labels.values() if r["verdict"] == "food"]
    n = len(foods)
    first = Counter(r["first"] for r in foods)
    printed = sorted(float(r["millet_pct"]) for r in foods if r["millet_pct"])
    half = sum(1 for p in printed if p >= 50)
    sb = [r["code"] for r in foods if sugar_before_millet(cands[r["code"]])]
    any_sugar = sum(1 for r in foods if any(KINDS[h[2]] == "sugar" for h in find_sugars(cands[r["code"]])))
    palm = sum(1 for r in foods if PALM_RE.search(cands[r["code"]]))
    hydro = sum(1 for r in foods if HYDRO_RE.search(cands[r["code"]]))
    not_first = n - first["millet"]

    res = {
        "source": "Open Food Facts India rows (data/off_india.csv, pulled 1 October 2026), hand-audited 17 October 2026",
        "candidates_with_english_list": len(cands),
        "verdicts": dict(verdicts),
        "foods": n,
        "first_ingredient": {k: kn(first[k], n) for k in FIRSTS},
        "millet_not_first": kn(not_first, n),
        "millet_pct_printed": kn(len(printed), n),
        "millet_pct_not_printed": kn(n - len(printed), n),
        "millet_pct_median": st.median(printed) if printed else None,
        "millet_pct_min": printed[0] if printed else None,
        "millet_pct_max": printed[-1] if printed else None,
        "half_millet_or_more": kn(half, len(printed)),
        "under_half_millet": kn(len(printed) - half, len(printed)),
        "sugar_named_before_first_millet": kn(len(sb), n),
        "any_added_sugar": kn(any_sugar, n),
        "palm": kn(palm, n),
        "hydrogenated_or_interesterified": kn(hydro, n),
        "examples": {
            "ragi_named_wafer": "a choco wafer sold as 'ragi bites': millets 16.7% with ragi 0.4%; atta leads the flours",
            "ragi_malt": "a malt drink mix printing '25% ragi' on the front lists sugar first, ragi 25% second",
        },
    }
    OUT.mkdir(exist_ok=True)
    (OUT / "millet.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    with (OUT / "millet_audit.txt").open("w", encoding="utf-8") as f:
        for r in sorted(foods, key=lambda r: (r["first"], r["code"])):
            f.write(f"{r['code']}\t{r['first']}\t{r['millet_pct'] or '-'}\t{'SUGAR<MILLET' if r['code'] in sb else ''}\n"
                    f"\t{r['note']}\n\t{cands[r['code']][:300]}\n")
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
