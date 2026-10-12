"""The serving-size trick (study 11 candidate A, unpublished): what size of serving do Indian packs declare, and how far
does that serving sit from the per-100 g column the nutrition table is built on?

Inputs
  data/off_india.csv   (pull_csv.py, read 1 Oct 2026): every India number. Fields used: serving_size (the text on the
                       pack, "2 biscuits (16 g)"), serving_quantity (Open Food Facts' parse of it, g or ml),
                       product_quantity (net quantity parsed to g or ml), quantity (net quantity text),
                       sugars_100g, sodium_100g.
  data/off_multi.tsv   (pull_multi.py, read 6 Oct 2026): UK, US and France for the same categories, same rules.
                       Its India rows are printed only as a cross-check on the off_india figure.
Output: out/serving.json and out/serving_table.csv (every number with its count k and base n).
Category level only; no brands.

Categories = Open Food Facts tags, the same sets in both files (a product can sit in two, as in world.py):
  biscuits, chips (crisps, potato/corn/tortilla chips, extruded snacks), chocolate, soft drinks, breakfast cereals,
  instant noodles, ice cream, and namkeen (India only; other countries have too few).

What is dropped, and why (counts are in the output under "dropped"):
  1. no_serving: serving_quantity blank or 0. Most Indian packs on Open Food Facts have no serving typed in.
  2. placeholder_100: the serving text is exactly 100 g / 100 ml ("100 g", "100g", "1 portion (100 g)", "100.0g").
     Open Food Facts contributors (and some importers) write 100 g when the pack gives only the per-100 g column, so
     this value cannot be told apart from a real 100 g serving. 967 of 5,087 Indian servings read this way (19%); on
     packs under 100 g it is impossible on its face. Dropped everywhere; the medians with these rows kept are in the
     output under "sensitivity" so the reader can see the difference.
  3. tiny: under 3 g or ml. Tablets, capsules, drops, "1 g" stand-ins. Not a food serving.
  4. over_pack: the serving is bigger than the pack's own net quantity (more than 5% over). A typo (245,484 g) or a
     serving copied from another size of the same product.
  5. huge: over 500 g or ml. Whole bottles, cooked-dish weights ("1 serving (512 g)" for a noodle pot), kcal text.
Baby food and supplements are out (analyse.py's excluded buckets).

Measures per category and country
  median declared serving (g, or ml for soft drinks); n = packs left after the drops.
  under_30: share of solid-food packs whose declared serving is under 30 g (soft drinks: 200 ml or less).
  per-serving vs per-100 g: among packs with a sugar value, median sugar per 100 g, median sugar in one declared
  serving (= sugars_100g x serving / 100), and the median of (100 / serving), the factor between the two columns.
  Same for sodium (mg).
  single_serve: Indian packs with a net quantity under 60 g (chips, chocolate, biscuits, namkeen, all categories):
  how many declare a serving smaller than the pack itself (serving < 95% of net quantity), how many declare the
  whole pack, k of n.
Shares: pct = 100 * k / n rounded once here; a page rounds again from k and n, never from the pct.
Other countries are shown only on 100 or more packs (world.py's MIN_N); India needs 50 for a share, 30 for a median.
Run: python -I serving.py  (about 40 s; off_multi.tsv is 1.3 GB)"""
import csv
import json
import re
import statistics as st
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from analyse import bucket, num  # noqa: E402

csv.field_size_limit(2**31 - 1)
OUT = HERE / "out"
MIN_N, MIN_INDIA_SHARE, MIN_INDIA_MEDIAN = 100, 50, 30

C = {"en:india": "India", "en:united-kingdom": "UK", "en:united-states": "US", "en:france": "France"}
CATS = {
    "biscuits": {"en:biscuits", "en:cookies"},
    "chips": {"en:crisps", "en:potato-crisps", "en:potato-chips", "en:corn-chips", "en:extruded-snacks", "en:tortilla-chips"},
    "chocolate": {"en:chocolates", "en:chocolate-candies", "en:milk-chocolates", "en:dark-chocolates", "en:chocolate-bars"},
    "soft_drinks": {"en:sodas", "en:carbonated-drinks", "en:soft-drinks", "en:colas", "en:energy-drinks"},
    "cereals": {"en:breakfast-cereals", "en:mueslis", "en:cereal-flakes", "en:granolas", "en:corn-flakes"},
    "instant_noodles": {"en:instant-noodles"},
    "ice_cream": {"en:ice-creams", "en:ice-creams-and-sorbets", "en:frozen-desserts"},
    "namkeen": {"en:namkeen", "en:indian-snacks", "en:bhujia", "en:salty-snacks", "en:savoury-snacks"},
}
LIQUID = {"soft_drinks"}
SINGLE_SERVE_CATS = ("chips", "chocolate", "biscuits", "namkeen")
PLACEHOLDER_RE = re.compile(r"^\s*(?:1\s*(?:portion|serving)\s*\()?\s*100(?:[.,]0+)?\s*(?:g|gm|gms|grams?|ml)\s*\)?\s*\.?\s*$", re.I)
TINY, HUGE, PACK_FUDGE = 3, 500, 1.05
SINGLE_SERVE_MAX = 60


def clean(r):
    """-> (serving g/ml or None, reason) after the drop rules. product_quantity is used for the over_pack rule."""
    s = num(r.get("serving_quantity"))
    if not s or s <= 0:
        return None, "no_serving"
    if PLACEHOLDER_RE.match(r.get("serving_size") or ""):
        return None, "placeholder_100"
    if s < TINY:
        return None, "tiny"
    pq = num(r.get("product_quantity"))
    if pq and pq > 0 and s > pq * PACK_FUDGE:
        return None, "over_pack"
    if s > HUGE:
        return None, "huge"
    return s, "kept"


def groups(cats):
    cset = set((cats or "").split(","))
    return [g for g, tags in CATS.items() if cset & tags]


def selftest():
    for s in ["100 g", "100g", "100.0g", "1 portion (100 g)", "1 serving (100 g)", "100 ml", "1 portion (100 ml)", "100 g."]:
        assert PLACEHOLDER_RE.match(s), s
    for s in ["2 biscuits (16 g)", "30 g", "100 g (2 biscuits)", "1 pack (100 g) 3 servings", "1000 g", "10 g"]:
        assert not PLACEHOLDER_RE.match(s), s
    assert clean({"serving_quantity": "100", "serving_size": "1 portion (100 g)", "product_quantity": "22"}) == (None, "placeholder_100")
    assert clean({"serving_quantity": "100", "serving_size": "1 pack (100 g)", "product_quantity": "22"}) == (None, "over_pack")
    assert clean({"serving_quantity": "16", "serving_size": "2 biscuits (16 g)", "product_quantity": "120"}) == (16.0, "kept")
    assert clean({"serving_quantity": "1", "serving_size": "1g", "product_quantity": "250"}) == (None, "tiny")
    assert clean({"serving_quantity": "512", "serving_size": "1 serving (512 g)", "product_quantity": ""}) == (None, "huge")
    assert clean({"serving_quantity": "", "serving_size": "", "product_quantity": "120"}) == (None, "no_serving")
    assert groups("en:snacks,en:biscuits,en:chocolates") == ["biscuits", "chocolate"]
    print("serving selftest OK")


def med(xs, nd=1):
    return round(st.median(xs), nd) if xs else None


def share(k, n):
    return {"k": k, "n": n, "pct": round(100 * k / n, 1) if n else None}


def shown(country, n, median=False):
    if country == "India":
        return n >= (MIN_INDIA_MEDIAN if median else MIN_INDIA_SHARE)
    return n >= MIN_N


def summarise(recs, country):
    """recs: list of dicts with s (serving), sugar, sodium (per 100), liquid flag."""
    n = len(recs)
    s = [p["s"] for p in recs]
    liquid = recs[0]["liquid"] if recs else False
    under = sum(p["s"] <= 200 for p in recs) if liquid else sum(p["s"] < 30 for p in recs)
    sug = [p for p in recs if p["sugar"] is not None]
    sod = [p for p in recs if p["sodium"] is not None]
    out = {"n": n, "unit": "ml" if liquid else "g",
           "median_serving": med(s), "q1_serving": med(sorted(s)[: max(1, n // 2)]) if n else None,
           "q3_serving": med(sorted(s)[n - max(1, n // 2):]) if n else None,
           "shown_median": shown(country, n, median=True),
           ("at_most_200ml" if liquid else "under_30g"): dict(share(under, n), shown=shown(country, n)),
           "sugar": {"n": len(sug), "median_per_100": med([p["sugar"] for p in sug]),
                     "median_per_serving": med([p["sugar"] * p["s"] / 100 for p in sug]),
                     "median_factor_100_over_serving": med([100 / p["s"] for p in sug]),
                     "shown": shown(country, len(sug), median=True)},
           "sodium_mg": {"n": len(sod), "median_per_100": med([p["sodium"] * 1000 for p in sod], 0),
                         "median_per_serving": med([p["sodium"] * 1000 * p["s"] / 100 for p in sod], 0),
                         "shown": shown(country, len(sod), median=True)}}
    return out


def read(path, want_countries, india_only_fields=False):
    """Yield (countries, groups, record) for rows in the wanted countries that sit in one of the categories."""
    with path.open(encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f, delimiter="\t"):
            cs = [C[t] for t in (r.get("countries_tags") or "").split(",") if t in C and C[t] in want_countries]
            if not cs:
                continue
            b = bucket(r.get("categories_tags", ""))
            if b and b.startswith("excluded"):
                continue
            yield cs, groups(r.get("categories_tags")), r, b


def main():
    selftest()
    acc = defaultdict(lambda: defaultdict(list))        # acc[group][country] -> kept records
    acc_sens = defaultdict(lambda: defaultdict(list))   # same, placeholder rows kept (sensitivity)
    dropped = defaultdict(Counter)                      # dropped[(country, group)][reason]
    single = defaultdict(lambda: Counter())             # single[(group)] -> counters (India)
    india_all = Counter()                               # India, every category: how servings were read
    seen_codes = set()

    def record(r, s):
        sug = num(r.get("sugars_100g"))
        sod = num(r.get("sodium_100g"))
        return {"s": s, "sugar": sug if sug is not None and 0 <= sug <= 100 else None,
                "sodium": sod if sod is not None and 0 <= sod <= 40 else None}

    # India from off_india.csv (one row per barcode)
    for cs, gs, r, b in read(HERE / "data" / "off_india.csv", {"India"}):
        code = r.get("code")
        if not code or code in seen_codes:
            continue
        seen_codes.add(code)
        s, why = clean(r)
        india_all[why] += 1
        pq = num(r.get("product_quantity"))
        # single-serve test, every non-excluded food and the four snack groups
        if pq and 0 < pq < SINGLE_SERVE_MAX and s is not None:
            for g in ["all_foods"] + [g for g in gs if g in SINGLE_SERVE_CATS]:
                single[g]["n"] += 1
                if s < pq * 0.95:
                    single[g]["serving_smaller_than_pack"] += 1
                elif s <= pq * PACK_FUDGE:
                    single[g]["serving_is_the_pack"] += 1
        for g in gs:
            dropped[("India", g)][why] += 1
            if s is not None:
                rec = record(r, s)
                rec["liquid"] = g in LIQUID
                acc[g]["India"].append(rec)
                acc_sens[g]["India"].append(rec)
            elif why == "placeholder_100":
                rec = record(r, 100.0)
                rec["liquid"] = g in LIQUID
                acc_sens[g]["India"].append(rec)

    # UK, US, France (and India as a cross-check) from off_multi.tsv
    multi_india = defaultdict(list)
    for cs, gs, r, b in read(HERE / "data" / "off_multi.tsv", {"UK", "US", "France", "India"}):
        if not gs:
            continue
        s, why = clean(r)
        for c in cs:
            for g in gs:
                if c == "India":
                    if s is not None:
                        multi_india[g].append(s)
                    continue
                dropped[(c, g)][why] += 1
                if s is not None:
                    rec = record(r, s)
                    rec["liquid"] = g in LIQUID
                    acc[g][c].append(rec)
                    acc_sens[g][c].append(rec)
                elif why == "placeholder_100":
                    rec = record(r, 100.0)
                    rec["liquid"] = g in LIQUID
                    acc_sens[g][c].append(rec)

    out = {"source": "Open Food Facts (https://world.openfoodfacts.org/), ODbL. off_india.csv read 1 Oct 2026 (India); "
                     "off_multi.tsv read 6 Oct 2026 (UK, US, France).",
           "note": "Declared serving = the serving the pack (or the contributor) typed into Open Food Facts, parsed by Open Food "
                   "Facts to g or ml. Volunteers fill the database, so no country's packs are a random sample. Servings that read "
                   "exactly 100 g / 100 ml are dropped as placeholders (see 'dropped'); medians with them kept are under "
                   "'sensitivity'. Shares: k of n, pct = 100*k/n.",
           "rules": {"placeholder_100": "serving text is exactly 100 g or 100 ml, with or without '1 portion ()'",
                     "tiny": f"under {TINY} g or ml", "over_pack": f"serving more than {int((PACK_FUDGE - 1) * 100)}% above the net quantity",
                     "huge": f"over {HUGE} g or ml", "single_serve_pack": f"net quantity under {SINGLE_SERVE_MAX} g"},
           "min_n": {"other_countries": MIN_N, "india_share": MIN_INDIA_SHARE, "india_median": MIN_INDIA_MEDIAN},
           "india_all_foods_serving_fields": dict(india_all),
           "categories": {}, "sensitivity_with_placeholders": {}, "dropped": {}, "single_serve_india": {},
           "india_multi_snapshot_median": {}}
    for g in CATS:
        out["categories"][g] = {c: summarise(v, c) for c, v in sorted(acc[g].items(), key=lambda kv: -len(kv[1])) if v}
        out["sensitivity_with_placeholders"][g] = {c: {"n": len(v), "median_serving": med([p["s"] for p in v])}
                                                   for c, v in acc_sens[g].items() if v}
        out["dropped"][g] = {c: dict(cnt) for (c, gg), cnt in dropped.items() if gg == g}
        if multi_india.get(g):
            out["india_multi_snapshot_median"][g] = {"n": len(multi_india[g]), "median_serving": med(multi_india[g])}
    for g, cnt in single.items():
        n = cnt["n"]
        out["single_serve_india"][g] = {"n": n,
                                        "serving_smaller_than_pack": dict(share(cnt["serving_smaller_than_pack"], n), shown=shown("India", n)),
                                        "serving_is_the_pack": dict(share(cnt["serving_is_the_pack"], n), shown=shown("India", n))}

    OUT.mkdir(exist_ok=True)
    (OUT / "serving.json").write_text(json.dumps(out, indent=1), encoding="utf-8")

    table = []
    for g, byc in out["categories"].items():
        for c, v in byc.items():
            table.append({"measure": "median_serving", "group": g, "country": c, "count": "", "n": v["n"], "value": v["median_serving"],
                          "unit": v["unit"] + " (median)", "shown": v["shown_median"]})
            key = "at_most_200ml" if g in LIQUID else "under_30g"
            table.append({"measure": key, "group": g, "country": c, "count": v[key]["k"], "n": v[key]["n"], "value": v[key]["pct"],
                          "unit": "%", "shown": v[key]["shown"]})
            for nutr, unit in (("sugar", "g"), ("sodium_mg", "mg")):
                for m in ("median_per_100", "median_per_serving"):
                    table.append({"measure": f"{nutr}_{m}", "group": g, "country": c, "count": "", "n": v[nutr]["n"],
                                  "value": v[nutr][m], "unit": unit + " (median)", "shown": v[nutr]["shown"]})
            table.append({"measure": "factor_100_over_serving", "group": g, "country": c, "count": "", "n": v["sugar"]["n"],
                          "value": v["sugar"]["median_factor_100_over_serving"], "unit": "times (median)", "shown": v["sugar"]["shown"]})
        for c, v in out["sensitivity_with_placeholders"][g].items():
            table.append({"measure": "median_serving_with_placeholders", "group": g, "country": c, "count": "", "n": v["n"],
                          "value": v["median_serving"], "unit": "g or ml (median)", "shown": shown(c, v["n"], True)})
        for c, cnt in out["dropped"][g].items():
            for why, k in cnt.items():
                table.append({"measure": "dropped_" + why, "group": g, "country": c, "count": k, "n": sum(cnt.values()), "value": "",
                              "unit": "packs", "shown": True})
    for g, v in out["single_serve_india"].items():
        for key in ("serving_smaller_than_pack", "serving_is_the_pack"):
            table.append({"measure": "single_serve_" + key, "group": g, "country": "India", "count": v[key]["k"], "n": v["n"],
                          "value": v[key]["pct"], "unit": "%", "shown": v[key]["shown"]})
    with (OUT / "serving_table.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["measure", "group", "country", "count", "n", "value", "unit", "shown"])
        w.writeheader()
        w.writerows(table)

    print("India, every food with a serving field:", dict(india_all))
    for g, byc in out["categories"].items():
        cells = []
        for c, v in byc.items():
            key = "at_most_200ml" if g in LIQUID else "under_30g"
            cells.append(f"{c} {v['median_serving']}{v['unit']} (n={v['n']}){'' if v['shown_median'] else '*'} "
                         f"{key} {v[key]['k']}/{v[key]['n']}")
        print(f"{g:16} " + " | ".join(cells))
        iv = byc.get("India")
        if iv:
            print(f"{'':16} India sugar/100 {iv['sugar']['median_per_100']} vs per serving {iv['sugar']['median_per_serving']} "
                  f"(n={iv['sugar']['n']}), factor {iv['sugar']['median_factor_100_over_serving']}; sodium mg/100 "
                  f"{iv['sodium_mg']['median_per_100']} vs per serving {iv['sodium_mg']['median_per_serving']} (n={iv['sodium_mg']['n']})")
        print(f"{'':16} with placeholders: " + ", ".join(f"{c} {v['median_serving']} (n={v['n']})" for c, v in out["sensitivity_with_placeholders"][g].items())
              + (f"; off_multi India {out['india_multi_snapshot_median'][g]}" if g in out["india_multi_snapshot_median"] else ""))
        print(f"{'':16} dropped India: {out['dropped'][g].get('India')}")
    print("single-serve India (net under 60 g):", json.dumps(out["single_serve_india"]))


if __name__ == "__main__":
    main()
