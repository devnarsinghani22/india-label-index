"""What if FSSAI's proposed front-of-pack warnings applied today?
Thresholds: ICMR-NIN Dietary Guidelines for Indians 2024, Table 15.1, as cited in FSSAI's 28 Aug 2026
affidavit to the Supreme Court (reported by LiveLaw and Business Standard, Sep 2026).
Solids per 100 g: added sugar 3 g, added fat 4.2 g, salt 625 mg. Liquids per 100 ml: 2 g, 1.5 g, 175 mg.
Phase I: warning when 2 or more nutrients are high. Phase II: when any one is high.
Added sugar: the label's declared added-sugar figure when present; otherwise total sugars, but only when a
sugar name is in the ingredient list (an upper estimate). Added fat: total fat when a fat or oil is in the
list (upper estimate). Salt: salt per 100 g when salt is in the list.
Output: out/fssai.json. Category-level only; no brands."""
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

from sugar import KINDS, find_sugars
from analyse import ADDED_SUGAR_RELEVANT_EXCLUDE, bucket, num
from warnings import SALT_RE, FAT_RE, is_liquid

csv.field_size_limit(2**31 - 1)
HERE = Path(__file__).parent
SOLID = {"sugar": 3, "fat": 4.2, "salt_mg": 625}
LIQUID = {"sugar": 2, "fat": 1.5, "salt_mg": 175}
NUTS = ("sugar", "fat", "salt")


def main():
    rows = csv.DictReader((HERE / "data" / "off_india.csv").open(encoding="utf-8"), delimiter="\t")
    tested, by_cat = [], defaultdict(list)
    declared = 0
    for r in rows:
        ing = (r.get("ingredients_text") or "").strip()
        if len(ing) < 8 or not ing.isascii():
            continue
        b = bucket(r.get("categories_tags", ""))
        if b in ("excluded_baby", "excluded_supplements"):
            continue
        sug, fat, salt = num(r.get("sugars_100g")), num(r.get("fat_100g")), num(r.get("salt_100g"))
        if salt is None and num(r.get("sodium_100g")) is not None:
            salt = num(r.get("sodium_100g")) * 2.5
        if None in (sug, fat, salt) or not (0 <= sug <= 100 and 0 <= fat <= 100 and 0 <= salt <= 100):
            continue
        add_sug = num(r.get("added-sugars_100g"))
        has_sugar = any(KINDS[i] == "sugar" for _, _, i in find_sugars(ing))
        if add_sug is not None and 0 <= add_sug <= sug + 0.5:
            declared += 1
            sugar_val, src = add_sug, "declared"
        else:
            sugar_val, src = (sug if has_sugar else 0.0), "estimate"
        th = LIQUID if is_liquid(r.get("categories_tags", "")) else SOLID
        high = []
        if sugar_val >= th["sugar"]:
            high.append("sugar")
        if FAT_RE.search(ing) and fat >= th["fat"]:
            high.append("fat")
        if SALT_RE.search(ing) and salt * 1000 >= th["salt_mg"]:
            high.append("salt")
        p = {"cat": b, "high": high, "src": src}
        tested.append(p)
        if b and not b.startswith("excluded"):
            by_cat[b].append(p)

    def summ(ps):
        n = len(ps)
        if not n:
            return {"tested": 0}
        each = Counter(x for p in ps for x in p["high"])
        return {"tested": n,
                "pct_phase2_any": round(100 * sum(1 for p in ps if p["high"]) / n, 1),
                "pct_phase1_2plus": round(100 * sum(1 for p in ps if len(p["high"]) >= 2) / n, 1),
                "pct_all3": round(100 * sum(1 for p in ps if len(p["high"]) == 3) / n, 1),
                "pct_by_nutrient": {k: round(100 * each[k] / n, 1) for k in NUTS}}

    # staples (oils, ghee, flours, spices, tea) left out of the headline, like the sugar study; FSSAI exempts
    # single-ingredient and inherently fat-rich foods anyway
    non_staple = [p for p in tested if p["cat"] not in ADDED_SUGAR_RELEVANT_EXCLUDE]
    res = {"rules": "ICMR-NIN DGI 2024 Table 15.1 thresholds as cited by FSSAI (affidavit 28 Aug 2026); Phase I = 2+ high, Phase II = any 1 high",
           "thresholds": {"solid_per_100g": SOLID, "liquid_per_100ml": LIQUID},
           "overall": summ(tested),
           "non_staple": summ(non_staple),
           "declared_added_sugar_only": summ([p for p in non_staple if p["src"] == "declared"]),
           "products_with_declared_added_sugar": declared,
           "categories": {k: summ(v) for k, v in sorted(by_cat.items(), key=lambda kv: -len(kv[1])) if len(v) >= 30}}
    (HERE / "out" / "fssai.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(json.dumps({k: res[k] for k in ("overall", "non_staple", "declared_added_sugar_only", "products_with_declared_added_sugar")}, indent=1))
    for k, v in res["categories"].items():
        print(f"{k[:34]:34} n={v['tested']:4} any={v['pct_phase2_any']} 2+={v['pct_phase1_2plus']} {v['pct_by_nutrient']}")


if __name__ == "__main__":
    main()
