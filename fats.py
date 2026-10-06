"""Which fat is in the pack? Reads every Indian ingredient list (data/off_india.csv) that names a fat or oil and
sorts it into: palm (palm oil, palmolein, palm kernel, palm stearin, palm fat), another named plant oil
(sunflower, rice bran, soybean, mustard, groundnut, coconut, olive, cottonseed, canola, corn, sesame, safflower),
dairy fat (butter, ghee, cream, milk fat), or an oil named only as "vegetable oil" / "edible oil" with no plant given.
Also counts hydrogenated / vanaspati / shortening / interesterified mentions.
Output: out/fats.json. Category-level only; no brands. Same buckets as analyse.py; baby food and supplements excluded."""
import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from analyse import ADDED_SUGAR_RELEVANT_EXCLUDE, bucket

csv.field_size_limit(2**31 - 1)
HERE = Path(__file__).parent

# "palm sugar", "palm jaggery", "palmyra", "palmitate" (vitamin A) and "palm hearts" are not palm oil
PALM_RE = re.compile(r"\bpalm(?!it|yra|\s*(?:sugar|jaggery|candy|nectar|syrup|heart|fruit|date))(?:olein|\s*kernel|\s*oil|\s*fat|\s*stearin|\s*shortening|\s*olein)?\w*", re.I)
NAMED_RE = re.compile(r"\b(sunflower|rice ?bran|soya?(?: ?bean)?|mustard|groundnut|peanut|coconut|olive|cotton ?seed|canola|rapeseed|corn|maize|sesame|gingelly|safflower|kardi|linseed|flaxseed|almond|walnut|avocado)\s*(?:seed\s*)?oil\b", re.I)
DAIRY_RE = re.compile(r"\b(butter|ghee|cream|milk fat|milk solids|butterfat|dairy fat|anhydrous milk fat|amf)\b", re.I)
FAT_RE = re.compile(r"\b(oil|oils|fat|fats|ghee|butter|shortening|margarine|vanaspati|palmolein)\b", re.I)
HYDRO_RE = re.compile(r"hydrogenated|vanaspati|shortening|interesterified|inter-esterified", re.I)
VEGONLY_RE = re.compile(r"(edible\s+)?(refined\s+)?(vegetable|veg\.?|cooking|edible|refined)\s+(oil|fat)s?\b", re.I)
NAMES = {"sunflower": "sunflower", "rice bran": "rice bran", "ricebran": "rice bran", "soyabean": "soybean", "soybean": "soybean",
         "soya": "soybean", "mustard": "mustard", "groundnut": "groundnut", "peanut": "groundnut", "coconut": "coconut",
         "olive": "olive", "cottonseed": "cottonseed", "cotton seed": "cottonseed", "canola": "canola", "rapeseed": "canola",
         "corn": "corn", "maize": "corn", "sesame": "sesame", "gingelly": "sesame", "safflower": "safflower", "kardi": "safflower",
         "linseed": "flaxseed", "flaxseed": "flaxseed", "almond": "almond", "walnut": "walnut", "avocado": "avocado"}


PLANT_RE = re.compile(r"\b(sunflower|rice ?bran|soya?(?: ?bean)?|mustard|groundnut|peanut|coconut|olive|cotton ?seed|canola|rapeseed|corn|maize|sesame|gingelly|safflower|kardi|linseed|flaxseed|almond|walnut|avocado)\b", re.I)
BRACKET_RE = re.compile(r"(?:oil|oils|fat|fats)\s*[\(\[\{]([^\)\]\}]{1,120})[\)\]\}]", re.I)


def classify(ing):
    """Return (has_fat, palm, named_set, dairy, unnamed_only, hydro)."""
    if not FAT_RE.search(ing):
        return False, False, set(), False, False, False
    palm = bool(PALM_RE.search(ing))
    named = {NAMES.get(m.lower().replace("  ", " "), m.lower()) for m in NAMED_RE.findall(ing)}
    # "Edible Vegetable Oil (Sunflower, Rice Bran)": the plant is named inside the bracket after the word oil
    for inner in BRACKET_RE.findall(ing):
        named |= {NAMES.get(m.lower().replace("  ", " "), m.lower()) for m in PLANT_RE.findall(inner)}
    dairy = bool(DAIRY_RE.search(ing))
    hydro = bool(HYDRO_RE.search(ing))
    unnamed_only = (not palm) and (not named) and (not dairy) and bool(VEGONLY_RE.search(ing) or HYDRO_RE.search(ing))
    return True, palm, named, dairy, unnamed_only, hydro


def main():
    rows = csv.DictReader((HERE / "data" / "off_india.csv").open(encoding="utf-8"), delimiter="\t")
    lists = 0
    recs = []
    for r in rows:
        ing = (r.get("ingredients_text") or "").strip()
        if len(ing) < 8 or not ing.isascii():
            continue
        b = bucket(r.get("categories_tags", ""))
        if b and b.startswith("excluded"):
            continue
        lists += 1
        has_fat, palm, named, dairy, unnamed, hydro = classify(ing)
        if not has_fat:
            continue
        recs.append({"cat": b or "Other", "palm": palm, "named": sorted(named), "dairy": dairy, "unnamed": unnamed, "hydro": hydro})

    def summ(ps):
        n = len(ps)
        if not n:
            return {"with_fat": 0}
        oils = Counter(o for p in ps for o in p["named"])
        return {"with_fat": n,
                "pct_palm": round(100 * sum(p["palm"] for p in ps) / n, 1),
                "pct_named_other_only": round(100 * sum(1 for p in ps if p["named"] and not p["palm"]) / n, 1),
                "pct_dairy_only": round(100 * sum(1 for p in ps if p["dairy"] and not p["palm"] and not p["named"]) / n, 1),
                "pct_unnamed_vegetable_oil": round(100 * sum(p["unnamed"] for p in ps) / n, 1),
                "pct_hydrogenated_or_vanaspati": round(100 * sum(p["hydro"] for p in ps) / n, 1),
                "named_oils": {k: round(100 * v / n, 1) for k, v in oils.most_common(8)}}

    non_staple = [p for p in recs if p["cat"] not in ADDED_SUGAR_RELEVANT_EXCLUDE | {"Edible oils and ghee"}]
    by_cat = defaultdict(list)
    for p in non_staple:
        by_cat[p["cat"]].append(p)
    res = {"lists_total": lists,
           "note": "Share of ingredient lists that name any fat or oil. Palm = palm oil, palmolein, palm kernel, palm stearin or palm fat anywhere in the list. 'Unnamed vegetable oil' = the list says only vegetable/edible/refined oil or fat (or hydrogenated oil / vanaspati / shortening) and never names a plant or dairy fat. Staples (oils, ghee, flours, spices, tea) left out of the headline.",
           "overall_all": summ(recs),
           "overall_non_staple": summ(non_staple),
           "categories": {k: summ(v) for k, v in sorted(by_cat.items()) if len(v) >= 50 and k != "Other"}}
    (HERE / "out").mkdir(exist_ok=True)
    (HERE / "out" / "fats.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    o = res["overall_non_staple"]
    print(f"lists {lists}; with a fat or oil (non-staple) {o['with_fat']}: palm {o['pct_palm']}%, other named {o['pct_named_other_only']}%, "
          f"dairy only {o['pct_dairy_only']}%, unnamed vegetable oil {o['pct_unnamed_vegetable_oil']}%, hydrogenated/vanaspati {o['pct_hydrogenated_or_vanaspati']}%")
    print("named oils", o["named_oils"])
    for k, v in sorted(res["categories"].items(), key=lambda kv: -kv[1]["pct_palm"]):
        print(f"  {k:40} n={v['with_fat']:4} palm {v['pct_palm']:5}%  unnamed {v['pct_unnamed_vegetable_oil']:5}%  hydro {v['pct_hydrogenated_or_vanaspati']:5}%  {list(v['named_oils'].items())[:3]}")


if __name__ == "__main__":
    main()
