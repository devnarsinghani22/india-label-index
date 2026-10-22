"""Study 14 candidate (UNPUBLISHED): FSSAI's warning test judged per serving instead of per 100 g / 100 ml.

Why: the All India Food Processors' Association told the Supreme Court (reported ~10 Sep 2026) that the limits should
be judged per serving, not per 100 g / 100 ml. This runs that what-if on the published study 3 foods.

Base: the published study 3 set (`python -I fssai.py`, no arguments): 665 non-staple foods with an English ingredient
list and sugar, fat and salt values. Same rows, same matchers, same rules, through fssai.score() unchanged.
Serving: the serving the pack or the contributor typed into Open Food Facts, parsed to g or ml, after serving.py's
drop rules (no serving, exactly-100 g/ml placeholders, under 3 g, bigger than the pack, over 500 g). A food with no
usable serving cannot be tested per serving and is counted under 'dropped'.
Per-serving test: the same ICMR-NIN numbers (solids 3 g added sugar, 4.2 g added fat, 625 mg salt; liquids 2 g,
1.5 g, 175 mg) applied to the amount in ONE declared serving. Done by scaling each row's limits by 100 / serving and
calling fssai.score(); recount() scales the nutrients instead and must agree on every row (the script fails if not).
The limits were set per 100 g / 100 ml, so this is a what-if, like the Chile study.
Triggers: the current single-nutrient plan (any 1 high, FSSAI affidavit 23 Sep 2026) and the dropped 2-nutrient plan.
Output: out/per_serving.json + out/per_serving_table.csv (every share with its k and n). Category level; no brands.
Run: python -I per_serving.py   (about 30 s)
"""
import csv
import json
import statistics as st
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import fssai  # noqa: E402
from analyse import ADDED_SUGAR_RELEVANT_EXCLUDE, bucket, num  # noqa: E402
from serving import clean  # noqa: E402
from sugar import KINDS, find_sugars  # noqa: E402

csv.field_size_limit(2**31 - 1)
OUT = HERE / "out"
SOL, LIQ = fssai.SOLID, fssai.LIQUID
NOW = {"type": "any", "n": 1}   # current plan: any one nutrient high (23 Sep 2026)
OLD = {"type": "any", "n": 2}   # dropped plan: two or more high
MIN_CAT = 30                    # same floor as fssai.py's category table
PUBLISHED = {"tested": 665, "any1": 474, "two_plus": 272}   # study 3 page, 1 Oct 2026


def scaled(th, s):
    """Per-100 limits -> the per-100 value at which ONE serving of s g/ml reaches the limit."""
    return {k: v * 100 / s for k, v in th.items()}


def recount(r, s):
    """Independent check: put the nutrients in one serving and compare with the unscaled limits."""
    ing = r["ingredients_text"].strip()
    sug, fat = num(r.get("sugars_100g")), num(r.get("fat_100g"))
    salt = num(r.get("salt_100g"))
    if salt is None:
        salt = num(r.get("sodium_100g")) * 2.5
    add = num(r.get("added-sugars_100g"))
    if add is not None and 0 <= add <= sug + 0.5:
        sugar = add
    else:
        sugar = sug if any(KINDS[i] == "sugar" for _, _, i in find_sugars(ing)) else 0.0
    th = LIQ if fssai.is_liquid(r.get("categories_tags", "")) else SOL
    k = s / 100
    high = []
    if sugar * k >= th["sugar"]:
        high.append("sugar")
    if fssai.FAT_RE.search(ing) and fat * k >= th["fat"]:
        high.append("fat")
    if fssai.SALT_RE.search(ing) and salt * 1000 * k >= th["salt_mg"]:
        high.append("salt")
    return high


def share(k, n):
    return {"k": k, "n": n, "pct": round(100 * k / n, 1) if n else None}


def med(xs):
    return round(st.median(xs), 1) if xs else None


def main():
    rows = csv.DictReader((HERE / "data" / "off_india.csv").open(encoding="utf-8"), delimiter="\t")
    base, recs, dropped = 0, [], Counter()
    ph = {"n": 0, "now": 0, "old": 0}   # exactly-100 g/ml placeholders: if real, per serving == per 100 g
    base_now = base_old = 0
    mismatch = []
    for r in rows:
        p = fssai.score(r, SOL, LIQ, NOW, False)
        if p is None or p["cat"] in ADDED_SUGAR_RELEVANT_EXCLUDE:
            continue
        base += 1
        base_now += bool(p["high"])
        base_old += len(p["high"]) >= 2
        s, why = clean(r)
        if s is None:
            dropped[why] += 1
            if why == "placeholder_100":
                ph["n"] += 1
                ph["now"] += bool(p["high"])
                ph["old"] += len(p["high"]) >= 2
            continue
        liquid = fssai.is_liquid(r.get("categories_tags", ""))
        q = fssai.score(r, scaled(SOL, s), scaled(LIQ, s), NOW, False)
        rc = recount(r, s)
        if sorted(q["high"]) != sorted(rc):
            mismatch.append((r.get("code"), s, q["high"], rc))
        recs.append({"cat": p["cat"], "liquid": liquid, "s": s, "h100": p["high"], "hs": q["high"]})

    # the base must be the published study 3 set, or every comparison below is off
    got = {"tested": base, "any1": base_now, "two_plus": base_old}
    assert got == PUBLISHED, f"base drifted from the published study 3 set: {got} vs {PUBLISHED}"
    assert not mismatch, f"scaled limits and recount disagree on {len(mismatch)} rows: {mismatch[:5]}"
    assert len(recs) + sum(dropped.values()) == base

    def block(ps):
        n = len(ps)
        if not n:
            return {"n": 0}
        out = {"n": n,
               "median_serving": med([p["s"] for p in ps]),
               "serving_under_100": share(sum(p["s"] < 100 for p in ps), n),
               "serving_over_100": share(sum(p["s"] > 100 for p in ps), n)}
        for tag, need in (("now_any1", 1), ("old_2plus", 2)):
            a = [len(p["h100"]) >= need for p in ps]
            b = [len(p["hs"]) >= need for p in ps]
            out[tag] = {"per_100": share(sum(a), n), "per_serving": share(sum(b), n),
                        "lost": sum(x and not y for x, y in zip(a, b)),
                        "gained": sum(y and not x for x, y in zip(a, b))}
        out["by_nutrient"] = {k: {"per_100": share(sum(k in p["h100"] for p in ps), n),
                                  "per_serving": share(sum(k in p["hs"] for p in ps), n)}
                              for k in fssai.NUTS}
        return out

    by_cat = defaultdict(list)
    for p in recs:
        if p["cat"]:   # like fssai.py: foods with no category bucket count in 'all' only
            by_cat[p["cat"]].append(p)
    res = {
        "source": "Open Food Facts (https://world.openfoodfacts.org/), ODbL; off_india.csv read 1 Oct 2026.",
        "rules": "ICMR-NIN DGI 2024 Table 15.1 limits as cited by FSSAI (affidavit 28 Aug 2026), applied once per 100 g / "
                 "100 ml (as published) and once to one declared serving (what-if). now_any1 = current single-nutrient "
                 "plan (23 Sep 2026); old_2plus = the dropped 2-nutrient plan.",
        "caveats": ["The limits were set per 100 g / 100 ml; a per-serving test is a what-if.",
                    "The serving is what the pack or the Open Food Facts contributor typed; servings reading exactly "
                    "100 g / 100 ml are dropped as placeholders.",
                    "Volunteers fill Open Food Facts, so the foods are not a random sample.",
                    "FSSAI's plan is a proposal, not law; the Supreme Court order is reserved.",
                    "Fat is total fat when a fat or oil is listed (upper estimate), as in study 3."],
        "base": {"tested_per_100": base, "with_usable_serving": len(recs), "dropped": dict(dropped),
                 "now_any1_all_665": share(base_now, base), "old_2plus_all_665": share(base_old, base)},
        "all": block(recs),
        "solids": block([p for p in recs if not p["liquid"]]),
        "liquids": block([p for p in recs if p["liquid"]]),
        "categories": {k: block(v) for k, v in sorted(by_cat.items(), key=lambda kv: -len(kv[1])) if len(v) >= MIN_CAT},
        "categories_under_min": {k: len(v) for k, v in by_cat.items() if len(v) < MIN_CAT},
    }
    a = res["all"]
    n2 = a["n"] + ph["n"]
    res["sensitivity_placeholders_as_real_100"] = {
        "n": n2, "placeholders": ph["n"],
        "now_any1": {"per_100": share(a["now_any1"]["per_100"]["k"] + ph["now"], n2),
                     "per_serving": share(a["now_any1"]["per_serving"]["k"] + ph["now"], n2)},
        "old_2plus": {"per_100": share(a["old_2plus"]["per_100"]["k"] + ph["old"], n2),
                      "per_serving": share(a["old_2plus"]["per_serving"]["k"] + ph["old"], n2)}}
    OUT.mkdir(exist_ok=True)
    (OUT / "per_serving.json").write_text(json.dumps(res, indent=1), encoding="utf-8")

    table = []
    groups = [("all", res["all"]), ("solids", res["solids"]), ("liquids", res["liquids"])] + list(res["categories"].items())
    for g, b in groups:
        table.append({"measure": "median_serving", "group": g, "count": "", "n": b["n"], "value": b["median_serving"],
                      "unit": "ml" if g == "liquids" else "g or ml"})
        for key in ("serving_under_100", "serving_over_100"):
            table.append({"measure": key, "group": g, "count": b[key]["k"], "n": b[key]["n"], "value": b[key]["pct"], "unit": "%"})
        for tag in ("now_any1", "old_2plus"):
            for col in ("per_100", "per_serving"):
                c = b[tag][col]
                table.append({"measure": f"{tag}_warned_{col}", "group": g, "count": c["k"], "n": c["n"], "value": c["pct"], "unit": "%"})
            for col in ("lost", "gained"):
                table.append({"measure": f"{tag}_{col}", "group": g, "count": b[tag][col], "n": b["n"], "value": "", "unit": "foods"})
        for k, v in b["by_nutrient"].items():
            for col in ("per_100", "per_serving"):
                table.append({"measure": f"high_{k}_{col}", "group": g, "count": v[col]["k"], "n": v[col]["n"],
                              "value": v[col]["pct"], "unit": "%"})
    with (OUT / "per_serving_table.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["measure", "group", "count", "n", "value", "unit"])
        w.writeheader()
        w.writerows(table)

    print("base:", json.dumps(res["base"]))
    for g, b in groups:
        now, old = b["now_any1"], b["old_2plus"]
        print(f"{g[:30]:30} n={b['n']:4} median serving {b['median_serving']} | now: per100 {now['per_100']['k']} "
              f"per serving {now['per_serving']['k']} (lost {now['lost']}, gained {now['gained']}) | 2+: per100 "
              f"{old['per_100']['k']} per serving {old['per_serving']['k']} | under 100: {b['serving_under_100']['k']}")
    print("categories under", MIN_CAT, res["categories_under_min"])
    print("placeholders as real 100 g:", json.dumps(res["sensitivity_placeholders_as_real_100"]))
    print("wrote out/per_serving.json, out/per_serving_table.csv")


if __name__ == "__main__":
    main()
