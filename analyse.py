"""India Label Index: category-level analysis of Indian packaged-food labels (Open Food Facts, India subset).
Input: data/off_india.csv (from pull_csv.py). Output: out/results.json, out/category_table.csv.
Brand names are never output. Sugar detection = the site's Label Checker rules (sugar.py)."""
import csv
import json
import statistics as st
import sys
from collections import Counter, defaultdict
from pathlib import Path

from sugar import NAMES, analyse

csv.field_size_limit(2**31 - 1)
HERE = Path(__file__).parent
SRC = HERE / "data" / "off_india.csv"
OUT = HERE / "out"
OUT.mkdir(exist_ok=True)

# Indian-relevant buckets, matched on Open Food Facts category tags (first match wins, order matters).
# Baby/infant food and supplements are excluded on purpose (rules: no kids/baby food critique, no supplement picks).
BUCKETS = [
    ("excluded_baby", ["en:baby-foods", "en:baby-milks", "en:infant-formulas", "en:baby-cereals"]),
    ("excluded_baby", ["en:dietary-supplements", "en:bodybuilding-supplements", "en:protein-powders", "en:food-supplements"]),
    ("Soft drinks and energy drinks", ["en:sodas", "en:carbonated-drinks", "en:energy-drinks", "en:colas", "en:soft-drinks"]),
    ("Fruit juices and juice drinks", ["en:fruit-juices", "en:juices-and-nectars", "en:fruit-based-beverages", "en:nectars"]),
    ("Milk drinks and health drink powders", ["en:flavoured-milks", "en:milk-drinks", "en:cocoa-and-chocolate-powders",
                                              "en:malted-drinks", "en:chocolate-drink-powders", "en:instant-beverages"]),
    ("Ice cream and frozen desserts", ["en:ice-creams", "en:frozen-desserts", "en:ice-creams-and-sorbets"]),
    ("Yoghurt and curd", ["en:yogurts", "en:fermented-milk-products", "en:dahi"]),
    ("Chocolate and confectionery", ["en:chocolates", "en:candies", "en:confectioneries", "en:chocolate-candies", "en:sweets"]),
    ("Indian sweets (mithai)", ["en:indian-sweets", "en:mithai"]),
    ("Biscuits and cookies", ["en:biscuits", "en:cookies", "en:biscuits-and-cakes", "en:crackers"]),
    ("Cakes and bakery", ["en:cakes", "en:pastries", "en:breads", "en:muffins", "en:viennoiseries"]),
    ("Breakfast cereals and muesli", ["en:breakfast-cereals", "en:mueslis", "en:cereal-flakes", "en:granolas", "en:corn-flakes"]),
    ("Protein and snack bars", ["en:cereal-bars", "en:protein-bars", "en:energy-bars", "en:snack-bars"]),
    ("Chips and crisps", ["en:chips-and-fries", "en:crisps", "en:potato-crisps", "en:potato-chips", "en:corn-chips", "en:extruded-snacks"]),
    ("Namkeen and savoury snacks", ["en:namkeen", "en:indian-snacks", "en:salty-snacks", "en:savoury-snacks", "en:appetizers", "en:bhujia"]),
    ("Instant noodles and pasta", ["en:instant-noodles", "en:noodles", "en:pastas", "en:instant-pasta"]),
    ("Sauces, ketchup and spreads", ["en:sauces", "en:ketchup", "en:tomato-sauces", "en:spreads", "en:jams", "en:sweet-spreads",
                                     "en:peanut-butters", "en:nut-butters", "en:chutneys", "en:pickles", "en:mayonnaises"]),
    ("Ready meals and instant mixes", ["en:meals", "en:instant-meals", "en:ready-to-eat", "en:soups", "en:instant-soups", "en:dessert-mixes"]),
    ("Tea and coffee", ["en:teas", "en:coffees", "en:tea-bags", "en:instant-coffees"]),
    ("Spices and masalas", ["en:spices", "en:spice-mixes", "en:masalas", "en:condiments"]),
    ("Flours, grains and pulses", ["en:flours", "en:cereals-and-their-products", "en:rices", "en:pulses", "en:legumes", "en:seeds"]),
    ("Edible oils and ghee", ["en:vegetable-oils", "en:oils", "en:ghee", "en:butters", "en:fats"]),
    ("Dairy (milk, paneer, cheese)", ["en:milks", "en:cheeses", "en:paneer", "en:dairies"]),
]
ADDED_SUGAR_RELEVANT_EXCLUDE = {"Spices and masalas", "Flours, grains and pulses", "Edible oils and ghee", "Tea and coffee"}


def num(v):
    try:
        x = float(v)
        return x if x == x else None
    except (TypeError, ValueError):
        return None


def bucket(tags):
    t = set(tags.split(",")) if tags else set()
    for name, keys in BUCKETS:
        if t & set(keys):
            return name
    return None


def med(xs):
    return round(st.median(xs), 2) if xs else None


def pct(a, b):
    return round(100 * a / b, 1) if b else None


def main():
    rows, dup = [], 0
    seen = set()
    with SRC.open(encoding="utf-8") as f:
        r = csv.DictReader(f, delimiter="\t")
        for row in r:
            code = row.get("code")
            if not code or code in seen:
                dup += 1
                continue
            seen.add(code)
            rows.append(row)
    total = len(rows)

    prods = []
    for row in rows:
        ing = (row.get("ingredients_text") or row.get("ingredients_text_en") or "").strip()
        b = bucket(row.get("categories_tags", ""))
        sugars = num(row.get("sugars_100g"))
        salt = num(row.get("salt_100g"))
        sodium = num(row.get("sodium_100g"))
        if salt is None and sodium is not None:
            salt = sodium * 2.5
        # implausible values are dropped, not clipped
        if sugars is not None and not (0 <= sugars <= 100):
            sugars = None
        if salt is not None and not (0 <= salt <= 100):
            salt = None
        a = analyse(ing) if len(ing) >= 8 and ing.isascii() else None
        labels = row.get("labels_tags", "") or ""
        prods.append({
            "bucket": b, "ing": bool(a), "a": a, "sugars": sugars, "salt": salt,
            "nova": num(row.get("nova_group")),
            "nas": ("en:no-added-sugar" in labels) or ("en:no-added-sugars" in labels),
        })

    with_ing = [p for p in prods if p["ing"]]
    sugar_relevant = [p for p in with_ing if p["bucket"] not in ADDED_SUGAR_RELEVANT_EXCLUDE and p["bucket"] != "excluded_baby"]

    def summarise(ps):
        ing = [p for p in ps if p["ing"]]
        sug = [p["sugars"] for p in ps if p["sugars"] is not None]
        salt = [p["salt"] for p in ps if p["salt"] is not None]
        nova = [p for p in ps if p["nova"]]
        return {
            "products": len(ps),
            "with_ingredient_list": len(ing),
            "pct_any_added_sugar": pct(sum(p["a"]["n_sugar_names"] > 0 for p in ing), len(ing)),
            "pct_sugar_in_top3": pct(sum(p["a"]["sugar_in_top3"] for p in ing), len(ing)),
            "pct_2plus_sugar_names": pct(sum(p["a"]["n_sugar_names"] >= 2 for p in ing), len(ing)),
            "pct_3plus_sugar_names": pct(sum(p["a"]["n_sugar_names"] >= 3 for p in ing), len(ing)),
            "max_sugar_names": max((p["a"]["n_sugar_names"] for p in ing), default=0),
            "with_sugar_value": len(sug),
            "median_sugar_g_per_100g": med(sug),
            "median_sugar_tsp_per_100g": round(med(sug) / 4, 1) if sug else None,
            "with_salt_value": len(salt),
            "median_salt_g_per_100g": med(salt),
            "median_salt_pct_of_5g": round(100 * med(salt) / 5) if salt else None,
            "with_nova": len(nova),
            "pct_nova4": pct(sum(p["nova"] == 4 for p in nova), len(nova)),
        }

    by = defaultdict(list)
    for p in prods:
        if p["bucket"] and p["bucket"] != "excluded_baby":
            by[p["bucket"]].append(p)
    cats = {k: summarise(v) for k, v in by.items()}
    # which sugar names show up in each category (share of that category's ingredient lists)
    for k, v in by.items():
        ing = [p for p in v if p["ing"]]
        c = Counter(NAMES[g] for p in ing for g in p["a"]["sugar_groups"])
        cats[k]["sugar_names"] = [(n, cnt, round(100 * cnt / len(ing), 1)) for n, cnt in c.most_common(6)] if ing else []

    alias_counter = Counter()
    for p in sugar_relevant:
        for g in p["a"]["sugar_groups"]:
            alias_counter[NAMES[g]] += 1

    # single-food packs ("Honey 100%", "Sugarcane juice 99%") are the sugar itself, so the claim is not tested there
    nas = [p for p in with_ing if p["nas"] and p["a"]["n_items"] >= 3]
    nas_with_sugar = [p for p in nas if p["a"]["n_sugar_names"] > 0]
    nas_alias = Counter(NAMES[g] for p in nas_with_sugar for g in p["a"]["sugar_groups"])

    res = {
        "source": "Open Food Facts (openfoodfacts.org), products tagged as sold in India. ODbL.",
        "products_total": total,
        "duplicates_dropped": dup,
        "excluded_baby_food": sum(p["bucket"] == "excluded_baby" for p in prods),
        "with_ingredient_list": len(with_ing),
        "overall_sugar_relevant": summarise(sugar_relevant),
        "categories": dict(sorted(cats.items(), key=lambda kv: -kv[1]["products"])),
        "sugar_names_frequency": alias_counter.most_common(25),
        "no_added_sugar_claims": {
            "with_ingredient_list": len(nas),
            "still_list_a_sugar_name": len(nas_with_sugar),
            "pct": pct(len(nas_with_sugar), len(nas)),
            "which_names": nas_alias.most_common(10),
        },
    }
    (OUT / "results.json").write_text(json.dumps(res, indent=1, ensure_ascii=False), encoding="utf-8")
    with (OUT / "category_table.csv").open("w", encoding="utf-8", newline="") as f:
        cols = [c for c in next(iter(cats.values())).keys() if c != "sugar_names"]
        w = csv.writer(f)
        w.writerow(["category"] + cols)
        for k, v in res["categories"].items():
            w.writerow([k] + [v[c] for c in cols])
    print(json.dumps({k: res[k] for k in ["products_total", "with_ingredient_list", "overall_sugar_relevant", "no_added_sugar_claims"]}, indent=1))
    print("categories:", {k: (v["products"], v["with_ingredient_list"]) for k, v in res["categories"].items()})


if __name__ == "__main__":
    main()
