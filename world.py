"""India vs the world: the same food categories in Open Food Facts, India against other countries.

Inputs
  data/off_multi.tsv  (pull_multi.py: India + 15 other countries, one snapshot, read 6 Oct 2026). All comparisons use it,
                      so every country comes from the same day's data.
  data/off_india.csv  (pull_csv.py: India only, read 1 Oct 2026). Used for two checks on the India crisps number:
                      the same figure on the earlier snapshot, and how spread it is across brands. Brand names are
                      never written out, only counts and shares.
Output: out/world.json and out/world_table.csv (every number the page uses, each with the count behind it).
Category-level only.

Measures
  1. Crisps (Open Food Facts tags crisps, potato crisps/chips, corn chips, extruded snacks, tortilla chips):
     a. palm oil named in the ingredient list, among lists that name a fat or oil. Same matcher as fats.py
        (palm fruit oil counts; palm sugar, palm jaggery, palmyra, palmitate or a misspelling of it such as
        "palmate", and the palm fruit itself do not).
        English-label countries only, because the matcher reads English words. A list counts as English by
        fats.english_list (a stray accent or a second language printed alongside does not drop it).
     b. Open Food Facts' own palm-oil tag (ingredients_analysis_tags en:palm-oil vs en:palm-oil-free; "maybe" and
        unknown left out). Works in any language, so it is the cross-check for every country.
     c. median saturated fat, g per 100 g; for India also split by whether the list names palm.
     d. which plant oils the crisps lists name (fats.classify, which reads "sunflower and/or canola oil" as two oils).
  2. Instant noodles only (tag en:instant-noodles; dry pasta is NOT mixed in): palm oil by the same two methods.
  3. 5 or more additives (Open Food Facts additives_n, which reads E numbers and India's INS numbers):
     all_foods = every product with an ingredient list and an additive count, baby food and supplements left out
     (analyse.py's excluded buckets); plus biscuits, crisps and instant noodles on their own.
Every share is stored with its count k and base n (pct = 100 * k / n, rounded once, here, to one decimal); pages
round from k and n, never from pct.
Other countries are shown only when the measure rests on at least MIN_N (100) products. India follows the rules of the
rest of the India Label Index: at least 50 lists for a share, 30 values for a median.
Run: python world.py   (python -I world.py works too)"""
import csv
import json
import re
import statistics as st
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from analyse import bucket, num  # noqa: E402
from fats import FAT_RE, PALM_RE, classify, english_list  # noqa: E402

csv.field_size_limit(2**31 - 1)
MIN_N = 100                      # other countries
MIN_INDIA_SHARE, MIN_INDIA_MEDIAN = 50, 30


def shown(country, n, median=False):
    if country in ("India", "India-only"):
        return n >= (MIN_INDIA_MEDIAN if median else MIN_INDIA_SHARE)
    return n >= MIN_N


C = {"en:india": "India", "en:united-kingdom": "UK", "en:united-states": "US", "en:france": "France", "en:germany": "Germany",
     "en:australia": "Australia", "en:brazil": "Brazil", "en:mexico": "Mexico", "en:chile": "Chile", "en:south-africa": "South Africa",
     "en:indonesia": "Indonesia", "en:united-arab-emirates": "UAE", "en:singapore": "Singapore", "en:canada": "Canada",
     "en:spain": "Spain", "en:italy": "Italy"}
ENGLISH = {"India", "UK", "US", "Canada", "Australia", "South Africa", "Singapore", "UAE"}
CRISPS = {"en:crisps", "en:potato-crisps", "en:potato-chips", "en:corn-chips", "en:extruded-snacks", "en:tortilla-chips"}
NOODLES = {"en:instant-noodles"}
BISCUITS = {"en:biscuits", "en:cookies"}
# India writes additives as INS numbers: "Emulsifier (INS 322)", "INS-330", "INS:330", "INS.330", "INS No 510"
INS_RE = re.compile(r"(?<![A-Za-z])INS\s*(?:No\.?\s*)?[\(\[:.\-]?\s*\d{3}", re.I)


def countries(tags):
    """Exact tag match (a substring test would let one tag stand in for another)."""
    return [C[t] for t in (tags or "").split(",") if t in C]


def palm_text(txt):
    """(names a fat or oil, names palm). Same regexes as fats.py."""
    return bool(FAT_RE.search(txt)), bool(PALM_RE.search(txt))


def palm_tag(ia):
    tags = set((ia or "").split(","))
    if "en:palm-oil" in tags:
        return 1
    if "en:palm-oil-free" in tags:
        return 0
    return None


def brand_key(tag):
    """Brand tags come in spelling variants ('lays', 'lay-s', 'xx:lay-s'). Group them: drop the language prefix and
    anything that is not a letter or digit, then keep the first 5 characters. Used only to count brands; never output."""
    return re.sub(r"[^a-z0-9]", "", re.sub(r"^[a-z]{2}:", "", tag.strip().lower()))[:5]


def selftest():
    yes = ["Potato, Edible Vegetable Oil (Palmolein), Salt", "palm oil", "Palm Kernel Oil", "vegetable oil (palm)",
           "Refined Palm Oil, Spices", "PALMOLEIN OIL", "palm fat", "Palm Stearin", "fully hydrogenated palm kernel oil",
           "Potatoes, Palm Fruit Oil, Sea Salt", "organic palm fruit oil"]
    no = ["Potato, Sunflower Oil, Salt", "Palm Sugar, Rice Flour, Rice Bran Oil", "Palm Jaggery, Groundnut Oil",
          "Palmyra Sprout Flour, Coconut Oil", "Vitamin A Palmitate, Milk Fat", "Ascorbyl palmitate, sunflower oil",
          "Corn, Canola Oil, Salt", "Palm fruit (ice apple), sugar, sunflower oil",
          "white corn, canola oil, sunflower oil (contains ascorbyl palmate), salt, calcium hydroxide"]
    for s in yes:
        assert PALM_RE.search(s), s
    for s in no:
        assert palm_text(s)[1] is False, s
    assert not palm_text("Potato, salt, spices")[0]
    assert classify("Potatoes, sunflower and/or safflower oil, salt")[2] == {"sunflower", "safflower"}
    assert classify("Potatoes, Sunflower, safflower and/or canola oil, salt")[2] == {"sunflower", "safflower", "canola"}
    assert countries("en:india,en:united-kingdom") == ["India", "UK"]
    assert countries("en:british-indian-ocean-territory") == []
    assert palm_tag("en:palm-oil,en:vegan") == 1 and palm_tag("en:palm-oil-free") == 0
    assert palm_tag("en:may-contain-palm-oil") is None and palm_tag("en:palm-oil-content-unknown") is None
    assert not english_list("Kartoffeln, Sonnenblumenöl, Speisesalz, Gewürze, Würze, Säuerungsmittel")
    assert english_list("Potatoes, sunflower oil, salt") and english_list("Potatoes, Palm Fruit Oil, Sea Salt, Jalapeño")
    assert english_list("Potatoes (64%), Edible Vegetable Oil (Palmolein), Rock Salt. INGRÉDIENTS Pommes de terre (64%), huile végétale")
    assert len(INS_RE.findall("Emulsifier (INS 322), Acidity Regulators (INS330 INS 525)")) == 3
    assert len(INS_RE.findall("Acidity regulator (INS-330), Antioxidant (INS:300), Colour (INS.150d), Stabiliser (INS No 412)")) == 4
    assert not INS_RE.search("Raisins 100%, Raisins (12%)")
    assert brand_key("xx:lay-s") == brand_key("lays") == "lays" and brand_key("en:balaji-wafers") == brand_key("xx:balaji")
    print("selftest OK")


def share(xs):
    """{'k', 'n', 'pct'} for a list of booleans; pct rounded once, from the raw ratio."""
    k, n = sum(map(bool, xs)), len(xs)
    return {"k": k, "n": n, "pct": round(100 * k / n, 1) if n else None}


def med(xs):
    return round(st.median(xs), 1) if xs else None


def main():
    selftest()
    acc = defaultdict(lambda: defaultdict(list))   # acc[(measure, group)][country] -> values
    india_crisp_codes = {}
    india_satfat_by_palm = defaultdict(list)       # India crisps lists naming a fat: sat fat, split by palm named or not
    oils = defaultdict(Counter)                     # crisps lists naming a fat: named plant oils, by country
    ins = Counter()                                 # does Open Food Facts count India's INS numbers?
    rows = 0
    with (HERE / "data" / "off_multi.tsv").open(encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f, delimiter="\t"):
            rows += 1
            cs = countries(r.get("countries_tags"))
            if not cs:
                continue
            cats = r.get("categories_tags") or ""
            cset = set(cats.split(","))
            txt = r.get("ingredients_text") or ""
            has_list = bool(txt.strip() or (r.get("ingredients_tags") or ""))
            if "India" in cs and txt.strip():
                k = len(INS_RE.findall(txt))
                if k:
                    a = num(r.get("additives_n"))
                    ins["lists_with_ins"] += 1
                    ins["counted_under_half"] += a is not None and a < k / 2
            groups = []
            if cset & CRISPS:
                groups.append("crisps")
            if cset & NOODLES:
                groups.append("instant_noodles")
            if cset & BISCUITS:
                groups.append("biscuits")
            b = bucket(cats)
            in_food = not (b and b.startswith("excluded"))     # every product except baby food and supplements
            if not groups and not in_food:
                continue
            fat_named, palm_named = palm_text(txt) if english_list(txt) else (False, False)
            ptag = palm_tag(r.get("ingredients_analysis_tags")) if has_list else None
            sat = num(r.get("saturated-fat_100g"))
            sat = sat if sat is not None and 0 <= sat <= 60 else None
            add = num(r.get("additives_n")) if has_list else None
            india_only = (r.get("countries_tags") or "").strip() == "en:india"
            for c in cs + (["India-only"] if india_only else []):
                for g in groups:
                    if fat_named and (c in ENGLISH or c == "India-only"):
                        acc[("palm_text", g)][c].append(palm_named)
                    if ptag is not None:
                        acc[("palm_tag", g)][c].append(ptag)
                    if sat is not None:
                        acc[("satfat", g)][c].append(sat)
                    if add is not None:
                        acc[("add5", g)][c].append(add >= 5)
                if in_food and add is not None:
                    acc[("add5", "all_foods")][c].append(add >= 5)
            if "crisps" in groups and fat_named:
                named = classify(txt)[2]
                for c in cs:
                    if c in ENGLISH:
                        oils[c]["_n"] += 1
                        oils[c].update(named)
            if "India" in cs and "crisps" in groups and fat_named:
                india_crisp_codes[r["code"]] = palm_named
                if sat is not None:
                    india_satfat_by_palm["names_palm" if palm_named else "no_palm"].append(sat)

    out = {"source": "Open Food Facts (https://world.openfoodfacts.org/), ODbL. off_multi.tsv read 6 Oct 2026; off_india.csv read 1 Oct 2026.",
           "rows_read": rows, "min_n_other_countries": MIN_N,
           "min_n_india": {"share": MIN_INDIA_SHARE, "median": MIN_INDIA_MEDIAN},
           "note": "Open Food Facts is filled in by volunteers, so no country's numbers are a random sample of its shops. "
                   "India = every product tagged as sold in India (some are also sold elsewhere); India-only = tagged India and nowhere else. "
                   "Shares: k of n products, pct = 100*k/n. all_foods = every product with an ingredient list and an additive count, "
                   "baby food and supplements left out.",
           "measures": {}}
    for (measure, g), by_c in sorted(acc.items()):
        d = {}
        for c, xs in sorted(by_c.items(), key=lambda kv: -len(kv[1])):
            d[c] = {"n": len(xs), "median_g_100g": med(xs)} if measure == "satfat" else share(xs)
            d[c]["shown"] = shown(c, len(xs), median=measure == "satfat")
        out["measures"].setdefault(measure, {})[g] = d

    out["crisps_named_oils"] = {
        c: {"n": k["_n"], "k": {o: v for o, v in k.most_common() if o != "_n"},
            "pct": {o: round(100 * v / k["_n"], 1) for o, v in k.most_common() if o != "_n"}}
        for c, k in oils.items() if shown(c, k["_n"])}

    out["india_crisps_satfat_by_palm"] = {
        g: {"n": len(xs), "median_g_100g": med(xs)} for g, xs in sorted(india_satfat_by_palm.items())}
    out["india_crisps_satfat_by_palm"]["note"] = ("Indian crisps lists that name a fat and have a saturated fat value, split by whether the "
                                                  "list names palm. Too few lists without palm to compare.")

    out["india_ins_check"] = dict(ins, note="Indian lists that write additives as INS numbers, and how many of them Open Food Facts "
                                                 "counted fewer than half of (additives_n < half the INS numbers in the text).")

    # India crisps checks: earlier snapshot (off_india.csv, 1 Oct) and brand spread (names never output)
    tags, snap = {}, []
    with (HERE / "data" / "off_india.csv").open(encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f, delimiter="\t"):
            code = r.get("code")
            if code in india_crisp_codes:
                tags[code] = (r.get("brands_tags") or "").split(",")[0].strip()
            if set((r.get("categories_tags") or "").split(",")) & CRISPS and english_list(r.get("ingredients_text")):
                fn, pn = palm_text(r["ingredients_text"])
                if fn:
                    snap.append(pn)
    tot = len(india_crisp_codes)
    no_brand = [c for c in india_crisp_codes if not tags.get(c)]
    groups_n = Counter(brand_key(tags[c]) for c in india_crisp_codes if tags.get(c))
    top_key, top_n = groups_n.most_common(1)[0] if groups_n else (None, 0)
    rest = [p for c, p in india_crisp_codes.items() if not (tags.get(c) and brand_key(tags[c]) == top_key)]
    out["india_crisps_checks"] = {
        "lists": tot,
        "lists_found_in_off_india": len(tags),
        "lists_without_brand_tag": len(no_brand),
        "distinct_brand_tags": len({tags[c] for c in india_crisp_codes if tags.get(c)}),
        "brands_spellings_merged": len(groups_n),
        "largest_brand": {"k": top_n, "n": tot, "pct": round(100 * top_n / tot, 1) if tot else None},
        "largest_3_brands": {"k": sum(n for _, n in groups_n.most_common(3)), "n": tot,
                             "pct": round(100 * sum(n for _, n in groups_n.most_common(3)) / tot, 1) if tot else None},
        "palm_without_largest_brand": share(rest),
        "off_india_1oct_snapshot": share(snap),
        "note": "Brand tags grouped by brand_key (spelling variants of one name counted once). Brand names are never output.",
    }

    ct = out["measures"]["palm_text"]["crisps"]
    out["headline"] = {
        "crisps_palm_india": ct["India"], "crisps_palm_uk": ct["UK"], "crisps_palm_us": ct["US"],
        "crisps_palm_ratio_india_uk": round((ct["India"]["k"] / ct["India"]["n"]) / (ct["UK"]["k"] / ct["UK"]["n"]), 1),
        "crisps_satfat_india": out["measures"]["satfat"]["crisps"]["India"],
        "crisps_satfat_uk": out["measures"]["satfat"]["crisps"]["UK"],
    }
    (HERE / "out").mkdir(exist_ok=True)
    (HERE / "out" / "world.json").write_text(json.dumps(out, indent=1), encoding="utf-8")

    # world_table.csv: every number on the page, with the count behind it
    table = []
    for measure, gs in out["measures"].items():
        for g, d in gs.items():
            for c, v in d.items():
                if measure == "satfat":
                    table.append({"measure": measure, "group": g, "item": "", "country": c, "count": "", "n": v["n"],
                                  "value": v["median_g_100g"], "unit": "g per 100 g (median)", "shown": v["shown"]})
                else:
                    table.append({"measure": measure, "group": g, "item": "", "country": c, "count": v["k"], "n": v["n"],
                                  "value": v["pct"], "unit": "%", "shown": v["shown"]})
    for c, v in out["crisps_named_oils"].items():
        for o, k in v["k"].items():
            table.append({"measure": "named_oil", "group": "crisps", "item": o, "country": c, "count": k, "n": v["n"],
                          "value": v["pct"][o], "unit": "%", "shown": True})
    for g, v in out["india_crisps_satfat_by_palm"].items():
        if isinstance(v, dict):
            table.append({"measure": "satfat_by_palm", "group": "crisps", "item": g, "country": "India", "count": "", "n": v["n"],
                          "value": v["median_g_100g"], "unit": "g per 100 g (median)", "shown": v["n"] >= MIN_INDIA_MEDIAN})
    table.append({"measure": "ins_check", "group": "india_lists_with_ins_numbers", "item": "additives counted under half", "country": "India",
                  "count": ins["counted_under_half"], "n": ins["lists_with_ins"],
                  "value": round(100 * ins["counted_under_half"] / ins["lists_with_ins"], 1), "unit": "%", "shown": True})
    chk = out["india_crisps_checks"]
    for item, v, unit in [("brands (spellings merged)", chk["brands_spellings_merged"], "brands"),
                          ("brand tags", chk["distinct_brand_tags"], "tags"),
                          ("lists without a brand", chk["lists_without_brand_tag"], "lists")]:
        table.append({"measure": "brand_spread", "group": "crisps", "item": item, "country": "India", "count": v, "n": chk["lists"],
                      "value": v, "unit": unit, "shown": True})
    for item, v in [("largest brand share", chk["largest_brand"]), ("largest 3 brands share", chk["largest_3_brands"]),
                    ("palm share without the largest brand", chk["palm_without_largest_brand"]),
                    ("palm share on the 1 Oct snapshot", chk["off_india_1oct_snapshot"])]:
        table.append({"measure": "brand_spread", "group": "crisps", "item": item, "country": "India", "count": v["k"], "n": v["n"],
                      "value": v["pct"], "unit": "%", "shown": True})
    table.append({"measure": "ratio", "group": "crisps", "item": "palm named, India vs UK", "country": "India/UK",
                  "count": "", "n": "", "value": out["headline"]["crisps_palm_ratio_india_uk"], "unit": "times", "shown": True})
    with (HERE / "out" / "world_table.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["measure", "group", "item", "country", "count", "n", "value", "unit", "shown"])
        w.writeheader()
        w.writerows(table)

    print(f"rows read {rows:,}")
    for (measure, g) in [("palm_text", "crisps"), ("palm_tag", "crisps"), ("satfat", "crisps"), ("palm_tag", "instant_noodles"),
                         ("palm_text", "instant_noodles"), ("add5", "all_foods"), ("add5", "biscuits"), ("add5", "crisps"),
                         ("add5", "instant_noodles")]:
        d = out["measures"].get(measure, {}).get(g, {})
        cells = [f"{c} {v.get('pct', v.get('median_g_100g'))} (n={v['n']}){'' if v['shown'] else '*'}" for c, v in d.items()]
        print(f"{measure:9} {g:15} " + " | ".join(cells))
    for c, v in out["crisps_named_oils"].items():
        print("crisps named oils", c, v["n"], list(v["pct"].items())[:6])
    print("india crisps sat fat by palm", out["india_crisps_satfat_by_palm"])
    print("india crisps checks", {k: v for k, v in chk.items() if k != "note"})
    print("india INS check", dict(ins))
    print("headline", out["headline"])


if __name__ == "__main__":
    main()
