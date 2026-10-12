"""Sugar and salt across borders (India Label Index, study 9).

The same food categories in Open Food Facts, India against 15 other countries, on sugar and salt. Study 5 (world.py)
compared palm oil, saturated fat and additive counts on the same snapshot; this script adds the two nutrients it left out.

Input: data/off_multi.tsv (pull_multi.py: India + 15 other countries, one snapshot, read 6 Oct 2026). Rows with the same
barcode are counted once (first row kept). Baby food and supplements are left out everywhere (analyse.py's excluded
buckets). Brand tags, used only for the India brand-spread check, come from data/off_india.csv by barcode and are never
written out.

Measures (every one stored as count k and base n, or median with k values of n packs; pages round from the counts)
  a. median total sugar, g per 100 g (per 100 ml for soft drinks and flavoured milk, as entered on Open Food Facts), by
     category and country. k = packs with a usable value, n = every pack in the category for that country.
     A value is usable when 0 <= sugar <= 100, it does not carry more energy than the pack's own energy figure
     (sugar x 4 kcal <= energy + 10, when energy is given) and it is under the category's cap (SUGAR_CAP, set from the
     top-30 audit: a 95 g biscuit, a 100 g soda or a 65 g yoghurt is a mis-tag, a syrup, a powder or a coating).
     Products tagged as the wrong kind of thing (cake mixes under cakes, cocoa powders under chocolate, syrups under
     sodas, meringues under biscuits, yoghurt coatings under yoghurt, dried fruit under chips) are dropped by tag first.
     For soft drinks the share with under 0.5 g (zero-sugar) and the median among the rest are given as well.
  b. share of English ingredient lists naming an added sugar in the first 3 ingredients (sugar.analyse, the Label
     Checker's alias rules; a list reads as English by fats.english_list), by category and country. English-label
     countries only.
  c. median salt, g per 100 g (salt_100g, else sodium x 2.5), for chips, instant noodles, biscuits, sauces, ketchup,
     cereals and namkeen. Usable when 0 <= salt <= SALT_CAP for the category (salt above the cap is sodium in mg typed
     as grams: 3,000 g ketchup, 4,800 g noodles).
  d. share of English lists with 2 or more distinct sugar names (and with any added sugar), by category and country,
     plus every non-staple food with an English list ("all_foods").
Cells with fewer than MIN_K (20) packs behind them are output but flagged ok=False and must not be used in a headline.
India vs UK gap check: the India cell recomputed without the single largest brand (brand_key, world.py).

Output: out/sugar_world.json, out/sugar_world_table.csv, out/sugar_world_audit.txt (rules, drop counts, the top 30 raw
sugar and salt values per category with what happened to each). Category level only; no brand is ever written.
Run: python -I sugar_world.py   (about 4 minutes; the repo's warnings.py shadows the stdlib, hence -I)"""
import csv
import json
import statistics as st
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from analyse import ADDED_SUGAR_RELEVANT_EXCLUDE, bucket, num  # noqa: E402
from fats import english_list  # noqa: E402
from sugar import analyse as sugar_analyse  # noqa: E402
from world import C, CRISPS, ENGLISH, brand_key, countries, share  # noqa: E402

csv.field_size_limit(2**31 - 1)
MIN_K = 20
ENERGY_SLACK = 10          # kcal; sugar x 4 may exceed the energy figure by this much (rounding on the label)
FOCUS = ["India", "UK", "US", "France", "Germany", "Australia"]

# One entry per category: Open Food Facts tags that put a product in it, tags that take it out again (the wrong kind
# of product under the same heading), the sugar and salt caps (g per 100 g or 100 ml) and whether it is a drink.
# Caps were set after reading the 30 highest raw values per category (out/sugar_world_audit.txt lists them).
_POWDER = {"en:beverage-preparations", "en:dehydrated-beverages", "en:dried-products", "en:dried-products-to-be-rehydrated",
           "en:instant-beverages", "en:powdered-drinks", "en:cocoa-and-chocolate-powders", "en:chocolate-powders"}
_SUPP = {"en:dietary-supplements", "en:bodybuilding-supplements", "en:meal-replacements", "en:weight-loss-milkshakes"}
CATS = {
    "biscuits": dict(label="Biscuits", tags={"en:biscuits", "en:cookies"}, drop={"en:meringues", "en:candies"}, sugar_cap=80, salt_cap=10),
    "breakfast_cereals": dict(label="Breakfast cereals", tags={"en:breakfast-cereals"},
                              drop={"en:cereal-bars", "en:bars", "en:syrups", "en:chocolates"}, sugar_cap=75, salt_cap=10),
    "chocolate": dict(label="Chocolate", tags={"en:chocolates"},
                      drop=_POWDER | {"en:beverages-and-beverages-preparations", "en:dairy-drinks", "en:breakfast-cereals", "en:spreads",
                                      "en:sweet-spreads", "en:biscuits", "en:sprinkles", "en:food-decorations", "en:cooking-helpers", "en:sweeteners"},
                      sugar_cap=80, salt_cap=5),
    "soft_drinks": dict(label="Soft drinks", tags={"en:sodas"},
                        drop=_POWDER | {"en:syrups", "en:flavoured-syrups", "en:candies", "en:concentrates", "en:alcoholic-beverages",
                                        "en:carbonated-waters", "en:waters"}, sugar_cap=25, salt_cap=2, liquid=True),
    "flavoured_milk": dict(label="Flavoured milk", tags={"en:flavoured-milks"},
                           drop=_POWDER | _SUPP | {"en:chocolates", "en:chocolate-candies", "en:sugars", "en:sweeteners", "en:milk-powders"},
                           sugar_cap=30, salt_cap=3, liquid=True),
    "ketchup": dict(label="Ketchup", tags={"en:ketchup", "en:tomato-ketchup"}, drop=set(), sugar_cap=50, salt_cap=10),
    "sauces": dict(label="Sauces (all kinds)", tags={"en:sauces"},
                   drop={"en:dehydrated-sauces", "en:dried-products", "en:dried-products-to-be-rehydrated", "en:sauce-mixes", "en:spice-mix",
                         "en:spices", "en:syrups", "en:maple-syrups", "en:jams", "en:marmalades", "en:fruit-and-vegetable-preserves",
                         "en:candies", "en:sweet-spreads", "en:soup-base", "en:food-additives"}, sugar_cap=90, salt_cap=25),
    "yoghurt": dict(label="Yoghurt", tags={"en:yogurts"},
                    drop={"en:candies", "en:confectioneries", "en:dried-products", "en:dehydrated-beverages", "en:biscuits", "en:cheeses",
                          "en:meats-and-their-products", "en:butters", "en:margarines", "en:non-food-products", "en:fats"},
                    sugar_cap=30, salt_cap=5),
    "cakes": dict(label="Cakes", tags={"en:cakes"},
                  drop={"en:cake-mixes", "en:baking-mixes", "en:dessert-mixes", "en:cooking-helpers", "en:pastry-helpers", "en:candies",
                        "en:marshmallows"} | _SUPP, sugar_cap=80, salt_cap=10),
    "ice_cream": dict(label="Ice cream", tags={"en:ice-creams"},
                      drop={"en:candies", "en:caramels", "en:ice-cream-mix", "en:ice-cream-cones", "en:dried-products", "en:dehydrated-beverages",
                            "en:pastries", "en:mochi"}, sugar_cap=60, salt_cap=5),
    "chips": dict(label="Chips", tags=set(CRISPS),
                  drop={"en:dried-fruits", "en:popcorn", "en:biscuits", "en:candies", "en:spices", "en:spice-mix"}, sugar_cap=40, salt_cap=10),
    "namkeen": dict(label="Namkeen", tags={"en:namkeen", "en:indian-snacks", "en:bhujia"}, drop={"en:biscuits", "en:breads"},
                    sugar_cap=40, salt_cap=10),
    "instant_noodles": dict(label="Instant noodles", tags={"en:instant-noodles"}, drop=set(), sugar_cap=40, salt_cap=20),
}
SALT_CATS = ["chips", "instant_noodles", "biscuits", "sauces", "ketchup", "breakfast_cereals", "namkeen"]


def nutrient(r):
    """(sugar, salt, kcal) as floats or None. Salt = salt_100g, else sodium_100g x 2.5."""
    sugar = num(r.get("sugars_100g"))
    salt = num(r.get("salt_100g"))
    if salt is None:
        na = num(r.get("sodium_100g"))
        salt = na * 2.5 if na is not None else None
    return sugar, salt, num(r.get("energy-kcal_100g"))


def sugar_reason(sugar, kcal, cap):
    """None when the value is usable, else why it is not."""
    if sugar is None:
        return "missing"
    if sugar < 0 or sugar > 100:
        return "out_of_range"
    if kcal is not None and sugar * 4 > kcal + ENERGY_SLACK:
        return "exceeds_energy"
    if sugar > cap:
        return "above_cap"
    return None


def salt_reason(salt, cap):
    if salt is None:
        return "missing"
    if salt < 0 or salt > cap:
        return "above_cap" if salt >= 0 else "out_of_range"
    return None


def groups_for(cset):
    """Categories a product falls in, and categories it was pulled out of by a drop tag."""
    hit, dropped = [], []
    for g, spec in CATS.items():
        if cset & spec["tags"]:
            (dropped if cset & spec["drop"] else hit).append(g)
    return hit, dropped


def med(xs):
    return round(st.median(xs), 1) if xs else None


def selftest():
    assert nutrient({"sugars_100g": "12", "salt_100g": "", "sodium_100g": "0.4", "energy-kcal_100g": "x"}) == (12.0, 1.0, None)
    assert nutrient({"sugars_100g": "", "salt_100g": "1.2", "sodium_100g": "9", "energy-kcal_100g": "100"}) == (None, 1.2, 100.0)
    assert sugar_reason(28, 480, 80) is None and sugar_reason(95, 380, 80) == "above_cap"
    assert sugar_reason(92, 36, 25) == "exceeds_energy" and sugar_reason(150.9, 503, 80) == "out_of_range"
    assert sugar_reason(10, None, 25) is None and sugar_reason(None, 400, 80) == "missing"
    assert salt_reason(3000, 10) == "above_cap" and salt_reason(1.5, 10) is None and salt_reason(-1, 10) == "out_of_range"
    assert groups_for({"en:biscuits", "en:meringues"}) == ([], ["biscuits"])
    assert groups_for({"en:sodas", "en:syrups"}) == ([], ["soft_drinks"])
    assert groups_for({"en:crisps", "en:namkeen"}) == (["chips", "namkeen"], [])
    assert groups_for({"en:cakes", "en:cake-mixes", "en:dessert-mixes"}) == ([], ["cakes"])
    assert groups_for({"en:flavoured-milks", "en:dairy-drinks"}) == (["flavoured_milk"], [])
    assert bucket("en:baby-foods,en:breakfast-cereals") == "excluded_baby"
    a = sugar_analyse("Refined wheat flour, sugar, palm oil, invert syrup, salt")
    assert a["sugar_in_top3"] and a["n_sugar_names"] == 2
    assert countries("en:india,en:united-kingdom") == ["India", "UK"]
    print("sugar_world selftest OK")


def main():
    selftest()
    vals = defaultdict(lambda: defaultdict(list))      # vals[(measure, cat)][country] -> numbers or booleans
    n_cat = defaultdict(Counter)                        # n_cat[cat][country] -> every pack in the category
    excl = defaultdict(Counter)                         # excl[(measure, cat)][(country, reason)] -> count
    tagdrop = defaultdict(Counter)                      # tagdrop[cat][country] -> pulled out by a drop tag
    top = defaultdict(list)                             # top[(measure, cat)] -> candidate rows for the audit's top 30
    india_rows = defaultdict(dict)                      # india_rows[cat][code] -> {"sugar", "top3"} for the brand check
    seen = set()
    rows = dup = baby = 0
    with (HERE / "data" / "off_multi.tsv").open(encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f, delimiter="\t"):
            rows += 1
            cs = countries(r.get("countries_tags"))
            if not cs:
                continue
            code = r.get("code") or ""
            if code in seen:
                dup += 1
                continue
            seen.add(code)
            cats = r.get("categories_tags") or ""
            b = bucket(cats)
            if b == "excluded_baby":
                baby += 1
                continue
            cset = set(cats.split(","))
            groups, dropped = groups_for(cset)
            txt = r.get("ingredients_text") or ""
            eng_cs = [c for c in cs if c in ENGLISH]
            staple = b in ADDED_SUGAR_RELEVANT_EXCLUDE
            need_text = bool(eng_cs) and (groups or not staple)
            if not groups and not dropped and not need_text:
                continue
            for g in dropped:
                for c in cs:
                    tagdrop[g][c] += 1
            sugar, salt, kcal = nutrient(r)
            a = sugar_analyse(txt) if need_text and english_list(txt) else None
            for g in groups:
                spec = CATS[g]
                sr = sugar_reason(sugar, kcal, spec["sugar_cap"])
                lr = salt_reason(salt, spec["salt_cap"]) if g in SALT_CATS else "not_measured"
                for c in cs:
                    n_cat[g][c] += 1
                    if sr is None:
                        vals[("sugar", g)][c].append(sugar)
                    else:
                        excl[("sugar", g)][(c, sr)] += 1
                    if lr is None:
                        vals[("salt", g)][c].append(salt)
                    elif lr != "not_measured":
                        excl[("salt", g)][(c, lr)] += 1
                    if a is not None and c in ENGLISH:
                        vals[("sugar_top3", g)][c].append(a["sugar_in_top3"])
                        vals[("names_2plus", g)][c].append(a["n_sugar_names"] >= 2)
                        vals[("any_sugar", g)][c].append(a["n_sugar_names"] >= 1)
                if sugar is not None and (sr is not None or sugar >= 0.75 * spec["sugar_cap"]):
                    top[("sugar", g)].append((sugar, sr, "/".join(cs), code, kcal, cats, txt[:70].replace("\n", " ")))
                if g in SALT_CATS and salt is not None and (lr is not None or salt >= 0.75 * spec["salt_cap"]):
                    top[("salt", g)].append((salt, lr, "/".join(cs), code, kcal, cats, txt[:70].replace("\n", " ")))
                if "India" in cs:
                    india_rows[g][code] = {"sugar": sugar if sr is None else None, "salt": salt if lr is None else None,
                                           "top3": a["sugar_in_top3"] if a else None}
            if a is not None and not staple:
                for c in eng_cs:
                    vals[("names_2plus", "all_foods")][c].append(a["n_sugar_names"] >= 2)
                    vals[("any_sugar", "all_foods")][c].append(a["n_sugar_names"] >= 1)
                    vals[("sugar_top3", "all_foods")][c].append(a["sugar_in_top3"])

    # ---- summarise -------------------------------------------------------------------------------------------------
    def med_cell(xs, g, c):
        n = n_cat[g][c]
        d = {"k": len(xs), "n": n, "median": med(xs), "ok": len(xs) >= MIN_K}
        if len(xs) >= 4:
            q = st.quantiles(xs, n=4)
            d["q1"], d["q3"] = round(q[0], 1), round(q[2], 1)
        return d

    def share_cell(xs):
        d = share(xs)
        d["ok"] = d["n"] >= MIN_K
        return d

    out = {"source": "Open Food Facts (https://world.openfoodfacts.org/), ODbL. off_multi.tsv read 6 Oct 2026 (16 countries, one snapshot); "
                     "brand tags for the India check from off_india.csv read 1 Oct 2026.",
           "note": "Open Food Facts is filled in by volunteers, so no country's numbers are a random sample of its shops. A product tagged "
                   "as sold in two countries counts in both. Medians: k = packs with a usable value, n = every pack in the category; "
                   "shares: k of n lists, pct = 100*k/n rounded once. ok=False means fewer than MIN_K packs behind the cell: not for headlines. "
                   "Drinks are per 100 ml as entered on Open Food Facts. English-list measures cover English-label countries only.",
           "rows_read": rows, "duplicate_codes_skipped": dup, "baby_and_supplement_rows_skipped": baby, "min_k": MIN_K,
           "english_countries": sorted(ENGLISH), "countries": sorted(set(C.values())),
           "categories": {g: {"label": s["label"], "tags": sorted(s["tags"]), "drop_tags": sorted(s["drop"]), "sugar_cap": s["sugar_cap"],
                              "salt_cap": s["salt_cap"] if g in SALT_CATS else None, "per": "100 ml" if s.get("liquid") else "100 g"}
                          for g, s in CATS.items()},
           "sugar": {}, "salt": {}, "sugar_top3": {}, "names_2plus": {}, "any_sugar": {}, "soft_drinks_split": {}}
    for g in CATS:
        out["sugar"][g] = {c: med_cell(xs, g, c) for c, xs in sorted(vals[("sugar", g)].items(), key=lambda kv: -len(kv[1]))}
        for c in C.values():
            if c in n_cat[g] and c not in out["sugar"][g]:
                out["sugar"][g][c] = med_cell([], g, c)
        if g in SALT_CATS:
            out["salt"][g] = {c: med_cell(xs, g, c) for c, xs in sorted(vals[("salt", g)].items(), key=lambda kv: -len(kv[1]))}
    for m in ("sugar_top3", "names_2plus", "any_sugar"):
        for g in list(CATS) + ["all_foods"]:
            out[m][g] = {c: share_cell(xs) for c, xs in sorted(vals[(m, g)].items(), key=lambda kv: -len(kv[1]))}
    for c, xs in vals[("sugar", "soft_drinks")].items():
        sweet = [x for x in xs if x >= 0.5]
        out["soft_drinks_split"][c] = {"zero_sugar": share_cell([x < 0.5 for x in xs]),
                                       "median_sweetened": {"k": len(sweet), "median": med(sweet), "ok": len(sweet) >= MIN_K}}
    out["exclusions"] = {f"{m}:{g}": {f"{c}:{reason}": k for (c, reason), k in sorted(cnt.items())} for (m, g), cnt in sorted(excl.items())}
    out["dropped_by_tag"] = {g: dict(cnt) for g, cnt in tagdrop.items()}

    # ---- India without its largest brand (brand_key groups spelling variants; names never output) ------------------
    tags = {}
    want = {code for g in india_rows for code in india_rows[g]}
    with (HERE / "data" / "off_india.csv").open(encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f, delimiter="\t"):
            if r.get("code") in want:
                tags[r["code"]] = (r.get("brands_tags") or "").split(",")[0].strip()
    out["india_brand_check"] = {}
    for g, codes in india_rows.items():
        keyed = Counter(brand_key(tags[c]) for c in codes if tags.get(c))
        top_key, top_n = keyed.most_common(1)[0] if keyed else (None, 0)
        rest = {c: v for c, v in codes.items() if not (tags.get(c) and brand_key(tags[c]) == top_key)}
        sug_all = [v["sugar"] for v in codes.values() if v["sugar"] is not None]
        sug_rest = [v["sugar"] for v in rest.values() if v["sugar"] is not None]
        t3_all = [v["top3"] for v in codes.values() if v["top3"] is not None]
        t3_rest = [v["top3"] for v in rest.values() if v["top3"] is not None]
        salt_all = [v["salt"] for v in codes.values() if v["salt"] is not None]
        salt_rest = [v["salt"] for v in rest.values() if v["salt"] is not None]
        out["india_brand_check"][g] = {
            "packs": len(codes), "packs_with_brand_tag": sum(1 for c in codes if tags.get(c)), "brands_spellings_merged": len(keyed),
            "largest_brand": {"k": top_n, "n": len(codes), "pct": round(100 * top_n / len(codes), 1) if codes else None},
            "sugar_median_all": {"k": len(sug_all), "median": med(sug_all)},
            "sugar_median_without_largest": {"k": len(sug_rest), "median": med(sug_rest)},
            "sugar_top3_all": share(t3_all), "sugar_top3_without_largest": share(t3_rest)}
        if g in SALT_CATS:
            out["india_brand_check"][g]["salt_median_all"] = {"k": len(salt_all), "median": med(salt_all)}
            out["india_brand_check"][g]["salt_median_without_largest"] = {"k": len(salt_rest), "median": med(salt_rest)}

    # ---- gaps India vs the five comparison countries (medians, g) -------------------------------------------------
    out["gaps_sugar_g"] = {}
    for g in CATS:
        d = out["sugar"][g]
        if "India" in d and d["India"]["median"] is not None:
            out["gaps_sugar_g"][g] = {c: round(d["India"]["median"] - d[c]["median"], 1) for c in FOCUS[1:]
                                      if c in d and d[c]["median"] is not None and d[c]["ok"] and d["India"]["ok"]}
    out["gaps_salt_g"] = {}
    for g in SALT_CATS:
        d = out["salt"].get(g, {})
        if "India" in d and d["India"]["median"] is not None:
            out["gaps_salt_g"][g] = {c: round(d["India"]["median"] - d[c]["median"], 1) for c in FOCUS[1:]
                                     if c in d and d[c]["median"] is not None and d[c]["ok"] and d["India"]["ok"]}

    (HERE / "out").mkdir(exist_ok=True)
    (HERE / "out" / "sugar_world.json").write_text(json.dumps(out, indent=1), encoding="utf-8")

    # ---- table: every number with its count --------------------------------------------------------------------------
    table = []
    for m, unit in (("sugar", "g sugar (median)"), ("salt", "g salt (median)")):
        for g, d in out[m].items():
            per = "100 ml" if CATS[g].get("liquid") else "100 g"
            for c, v in d.items():
                table.append({"measure": m, "group": g, "country": c, "count": v["k"], "n": v["n"], "value": v["median"],
                              "unit": f"{unit} per {per}", "ok": v["ok"]})
    for m in ("sugar_top3", "names_2plus", "any_sugar"):
        for g, d in out[m].items():
            for c, v in d.items():
                table.append({"measure": m, "group": g, "country": c, "count": v["k"], "n": v["n"], "value": v["pct"], "unit": "% of English lists", "ok": v["ok"]})
    for c, v in out["soft_drinks_split"].items():
        table.append({"measure": "zero_sugar_share", "group": "soft_drinks", "country": c, "count": v["zero_sugar"]["k"], "n": v["zero_sugar"]["n"],
                      "value": v["zero_sugar"]["pct"], "unit": "% of packs with a value", "ok": v["zero_sugar"]["ok"]})
        table.append({"measure": "sugar_sweetened_only", "group": "soft_drinks", "country": c, "count": v["median_sweetened"]["k"], "n": "",
                      "value": v["median_sweetened"]["median"], "unit": "g sugar (median) per 100 ml, packs with 0.5 g or more", "ok": v["median_sweetened"]["ok"]})
    for g, v in out["india_brand_check"].items():
        table.append({"measure": "india_without_largest_brand", "group": g, "country": "India", "count": v["sugar_median_without_largest"]["k"], "n": v["packs"],
                      "value": v["sugar_median_without_largest"]["median"], "unit": "g sugar (median)", "ok": v["sugar_median_without_largest"]["k"] >= MIN_K})
        table.append({"measure": "india_largest_brand_share", "group": g, "country": "India", "count": v["largest_brand"]["k"], "n": v["largest_brand"]["n"],
                      "value": v["largest_brand"]["pct"], "unit": "% of packs", "ok": True})
        if "salt_median_without_largest" in v:
            table.append({"measure": "india_salt_without_largest_brand", "group": g, "country": "India", "count": v["salt_median_without_largest"]["k"],
                          "n": v["packs"], "value": v["salt_median_without_largest"]["median"], "unit": "g salt (median)",
                          "ok": v["salt_median_without_largest"]["k"] >= MIN_K})
    with (HERE / "out" / "sugar_world_table.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["measure", "group", "country", "count", "n", "value", "unit", "ok"])
        w.writeheader()
        w.writerows(table)

    # ---- audit -------------------------------------------------------------------------------------------------------
    def short_tags(cats):
        skip = {"en:snacks", "en:sweet-snacks", "en:salty-snacks", "en:beverages", "en:dairies", "en:fermented-foods", "en:fermented-milk-products",
                "en:plant-based-foods-and-beverages", "en:plant-based-foods", "en:cereals-and-potatoes", "en:cereals-and-their-products",
                "en:biscuits-and-cakes", "en:biscuits-and-crackers", "en:appetizers", "en:groceries", "en:condiments", "en:desserts", "en:frozen-foods",
                "en:frozen-desserts", "en:carbonated-drinks", "en:chips-and-fries", "en:cocoa-and-its-products", "en:confectioneries", "en:breakfasts",
                "en:spreads", "en:sweet-spreads", "en:meals", "en:dairy-desserts", "en:fermented-dairy-desserts", "en:beverages-and-beverages-preparations",
                "en:dried-products", "en:dried-products-to-be-rehydrated", "en:noodles", "en:pastas"}
        return ",".join(t[3:] for t in cats.split(",") if t.startswith("en:") and t not in skip)[:90]

    L = ["sugar_world.py audit (study 9: sugar and salt across borders). Open Food Facts snapshot of 6 Oct 2026, 16 countries.",
         f"rows read {rows:,}; duplicate barcodes skipped {dup}; baby food and supplement rows skipped {baby:,}.",
         "", "RULES", f"- a cell needs {MIN_K} packs (k) to be used in a headline; smaller cells are output with ok=False.",
         "- sugar value kept when 0 <= g <= 100, sugar x 4 kcal <= the pack's own energy + 10 (when energy is given) and g <= the category cap.",
         "- salt = salt_100g, else sodium x 2.5; kept when 0 <= g <= the category cap (values in the hundreds or thousands are mg typed as g).",
         "- products carrying one of the category's drop tags are not in the category at all (powders, syrups, mixes, coatings, candy, dried fruit).",
         "- rows with the same barcode are counted once; baby food and supplements are out everywhere.",
         "- the 30 highest raw values per category are listed below with what happened to each (kept, or the exclusion reason).", ""]
    L.append("CATEGORY DEFINITIONS")
    for g, s in CATS.items():
        L.append(f"- {g}: tags {sorted(s['tags'])}; drop {sorted(s['drop'])}; sugar cap {s['sugar_cap']} g" +
                 (f"; salt cap {s['salt_cap']} g" if g in SALT_CATS else "; salt not measured") + ("; per 100 ml" if s.get("liquid") else ""))
    L.append("")
    L.append("PULLED OUT BY A DROP TAG (products that carried a category tag and a drop tag), by country")
    for g in CATS:
        if tagdrop[g]:
            L.append(f"- {g}: total {sum(tagdrop[g].values())}; " + ", ".join(f"{c} {k}" for c, k in tagdrop[g].most_common()))
    L.append("")
    L.append("EXCLUDED VALUES BY REASON (all countries together, then India and UK)")
    for (m, g), cnt in sorted(excl.items()):
        tot = Counter()
        for (c, reason), k in cnt.items():
            tot[reason] += k
        kept = sum(len(v) for v in vals[(m, g)].values())
        L.append(f"- {m} {g}: kept {kept}; " + ", ".join(f"{r} {k}" for r, k in tot.most_common()) +
                 " | India: " + ", ".join(f"{r} {k}" for (c, r), k in sorted(cnt.items()) if c == "India") +
                 " | UK: " + ", ".join(f"{r} {k}" for (c, r), k in sorted(cnt.items()) if c == "UK"))
    L.append("")
    L.append("TOP 30 RAW VALUES PER CATEGORY (value, what happened, countries, barcode, kcal, tags, start of the ingredient list)")
    for (m, g), cand in sorted(top.items()):
        cand.sort(key=lambda t: -t[0])
        L.append(f"--- {m} {g} (cap {CATS[g]['sugar_cap' if m == 'sugar' else 'salt_cap']} g)")
        for v, reason, cs, code, kcal, cats, snip in cand[:30]:
            L.append(f"  {v:>10.2f}  {reason or 'kept':14} {cs[:16]:16} {code:15} kcal={kcal} | {short_tags(cats)} | {snip}")
    L.append("")
    L.append("INDIA WITHOUT ITS LARGEST BRAND (brand_key groups spelling variants; no name written)")
    for g, v in out["india_brand_check"].items():
        L.append(f"- {g}: packs {v['packs']}, with a brand tag {v['packs_with_brand_tag']}, brands {v['brands_spellings_merged']}, largest {v['largest_brand']['k']} of {v['largest_brand']['n']} "
                 f"({v['largest_brand']['pct']}%); sugar median {v['sugar_median_all']['median']} g (k {v['sugar_median_all']['k']}) -> "
                 f"{v['sugar_median_without_largest']['median']} g (k {v['sugar_median_without_largest']['k']}) without it; sugar in first 3: "
                 f"{v['sugar_top3_all']['k']} of {v['sugar_top3_all']['n']} -> {v['sugar_top3_without_largest']['k']} of {v['sugar_top3_without_largest']['n']}"
                 + (f"; salt median {v['salt_median_all']['median']} g (k {v['salt_median_all']['k']}) -> {v['salt_median_without_largest']['median']} g "
                    f"(k {v['salt_median_without_largest']['k']}) without it" if "salt_median_all" in v else ""))
    (HERE / "out" / "sugar_world_audit.txt").write_text("\n".join(L) + "\n", encoding="utf-8")

    # ---- console -----------------------------------------------------------------------------------------------------
    print(f"rows read {rows:,}; dup {dup}; baby/supp {baby:,}")
    for m in ("sugar", "salt"):
        for g, d in out[m].items():
            cells = [f"{c} {d[c]['median']} ({d[c]['k']}/{d[c]['n']}){'' if d[c]['ok'] else '*'}" for c in FOCUS if c in d]
            print(f"{m:5} {g:17} " + " | ".join(cells))
    for m in ("sugar_top3", "names_2plus"):
        for g, d in out[m].items():
            cells = [f"{c} {d[c]['pct']}% ({d[c]['k']}/{d[c]['n']}){'' if d[c]['ok'] else '*'}" for c in ("India", "UK", "US", "Australia") if c in d]
            print(f"{m:11} {g:17} " + " | ".join(cells))
    print("soft drinks zero-sugar share:", {c: f"{v['zero_sugar']['pct']}% ({v['zero_sugar']['k']}/{v['zero_sugar']['n']})" for c, v in out["soft_drinks_split"].items() if c in FOCUS})
    print("gaps sugar India minus country (g):", out["gaps_sugar_g"])
    print("gaps salt India minus country (g):", out["gaps_salt_g"])
    print("india brand check:", {g: (v["largest_brand"]["pct"], v["sugar_median_all"]["median"], v["sugar_median_without_largest"]["median"]) for g, v in out["india_brand_check"].items()})


if __name__ == "__main__":
    main()
