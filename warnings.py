"""What if India used Chile's front-of-pack warning rules? (Ley 20.606, final 2019 thresholds)
Solids per 100 g: energy >= 275 kcal, sodium >= 400 mg, total sugars >= 10 g, saturated fat >= 4 g.
Liquids per 100 ml: 70 kcal, 100 mg, 5 g, 3 g.
Chile only labels a nutrient when sugar, salt or fat was ADDED, so each warning here needs the matching
ingredient in the list: a sugar name (Label Checker rules), salt/sodium, or a fat/oil. Energy counts when
any of the three was added. Sources: Global Food Research Program; Chilean Decree 13 (2015).
Output: out/warnings.json. Category-level only; no brands."""
import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from sugar import KINDS, find_sugars
from analyse import BUCKETS, bucket, num

csv.field_size_limit(2**31 - 1)
HERE = Path(__file__).parent
SOLID = {"kcal": 275, "sodium_mg": 400, "sugar": 10, "satfat": 4}
LIQUID = {"kcal": 70, "sodium_mg": 100, "sugar": 5, "satfat": 3}
# salt only: bare "sodium" would catch raising agents like sodium bicarbonate
SALT_RE = re.compile(r"(?<![a-z])(salt|sodium chloride|sendha namak|kala namak)(?![a-z])", re.I)
FAT_RE = re.compile(r"(?<![a-z])(oils?|fats?|ghee|butter|vanaspati|palmolein|shortening|margarine|cream|cocoa butter|lard)(?![a-z])", re.I)
POWDER = {"en:instant-beverages", "en:cocoa-and-chocolate-powders", "en:chocolate-drink-powders", "en:malted-drinks",
          "en:beverage-preparations", "en:dehydrated-beverages", "en:powdered-drinks"}


def is_liquid(tags):
    t = set(tags.split(",")) if tags else set()
    return "en:beverages" in t and not (t & POWDER)


def main():
    rows = list(csv.DictReader((HERE / "data" / "off_india.csv").open(encoding="utf-8"), delimiter="\t"))
    tested, by_cat = [], defaultdict(list)
    for r in rows:
        ing = (r.get("ingredients_text") or "").strip()
        if len(ing) < 8 or not ing.isascii():
            continue
        b = bucket(r.get("categories_tags", ""))
        if b == "excluded_baby":
            continue
        kcal = num(r.get("energy-kcal_100g"))
        sug = num(r.get("sugars_100g"))
        sat = num(r.get("saturated-fat_100g"))
        sod = num(r.get("sodium_100g"))
        if sod is None and num(r.get("salt_100g")) is not None:
            sod = num(r.get("salt_100g")) / 2.5
        if None in (kcal, sug, sat, sod) or not (0 <= kcal <= 950 and 0 <= sug <= 100 and 0 <= sat <= 100 and 0 <= sod <= 40):
            continue
        th = LIQUID if is_liquid(r.get("categories_tags", "")) else SOLID
        added_sugar = any(KINDS[i] == "sugar" for _, _, i in find_sugars(ing))
        added_salt = bool(SALT_RE.search(ing))
        added_fat = bool(FAT_RE.search(ing))
        w = []
        if added_sugar and sug >= th["sugar"]:
            w.append("sugar")
        if added_salt and sod * 1000 >= th["sodium_mg"]:
            w.append("sodium")
        if added_fat and sat >= th["satfat"]:
            w.append("satfat")
        if (added_sugar or added_salt or added_fat) and kcal >= th["kcal"]:
            w.append("calories")
        p = {"cat": b, "w": w, "liquid": th is LIQUID}
        tested.append(p)
        if b:
            by_cat[b].append(p)

    def summ(ps):
        n = len(ps)
        c = Counter(len(p["w"]) for p in ps)
        each = Counter(x for p in ps for x in p["w"])
        return {"tested": n,
                "pct_any_warning": round(100 * sum(1 for p in ps if p["w"]) / n, 1) if n else None,
                "pct_2plus": round(100 * sum(1 for p in ps if len(p["w"]) >= 2) / n, 1) if n else None,
                "pct_by_warning": {k: round(100 * each[k] / n, 1) for k in ("sugar", "sodium", "satfat", "calories")} if n else {},
                "count_distribution": {str(k): c[k] for k in sorted(c)}}

    res = {"rules": "Chile Law 20.606, final 2019 thresholds; warning only where the nutrient was added (ingredient list)",
           "thresholds": {"solid_per_100g": SOLID, "liquid_per_100ml": LIQUID},
           "overall": summ(tested),
           "liquids_tested": sum(p["liquid"] for p in tested),
           "categories": {k: summ(v) for k, v in sorted(by_cat.items(), key=lambda kv: -len(kv[1])) if len(v) >= 30}}
    (HERE / "out" / "warnings.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(json.dumps({k: res[k] for k in ("overall", "liquids_tested")}, indent=1))
    for k, v in res["categories"].items():
        print(f"{k[:34]:34} n={v['tested']:4} any={v['pct_any_warning']} 2+={v['pct_2plus']} {v['pct_by_warning']}")


if __name__ == "__main__":
    main()
