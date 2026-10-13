"""India Label Index, what is inside the 'Dairy (milk, paneer, cheese)' row (13 Oct 2026 audit).
analyse.py's last bucket catches every dairy-tagged food that no earlier bucket took, so the hub row and
/india-label-index/dairy/ ('23% of 154 name an added sugar') mix plain milk with sweet milk drinks, dairy sweets,
whitener, condensed milk, protein powders and an infant milk food. This splits those 154 lists by what they are.
Rules, first match wins (hand-audited row by row on 13 Oct; every row lands where the audit put it):
  protein powder   name says whey, or the list starts with whey or a protein blend
  infant milk food name says infant
  cheese or paneer tagged en:cheeses or en:paneer (since 13 Oct these two tags bucket here, not under yoghurt; item 4e)
  dairy sweet      peda/pedha, shrikhand, kheer, kulfi, rabdi, barfi, kalakand, rasgulla, rasmalai, sandesh, halwa
  whitener or condensed milk
  sweet milk drink a flavour or drink word in the name (flavoured milk, shake, lassi, kool, doodh, coffee, caramel,
                   chaas/taak, probiotic), or a sugar first or second in an unnamed product's list
  plain milk, cream, curd or milk powder: everything left
Output: out/dairy_split.json (counts only, no brand or product names). Never changes analyse.py's buckets: 12 scripts
import them and every published study would move. (They changed once, on 13 Oct 2026, to move cheese and paneer out of
yoghurt and curd; the pages carry a dated correction note.)
Run: python -I dairy_split.py [--show]   (--show prints names for the local audit only; never publish them)"""
import csv, json, re, sys
from collections import defaultdict
from pathlib import Path
HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from analyse import bucket, SRC
from sugar import analyse
csv.field_size_limit(2**31 - 1)
DAIRY = "Dairy (milk, paneer, cheese)"
PROTEIN_NAME = re.compile(r"whey|protein powder|isolate", re.I)
PROTEIN_LIST = re.compile(r"^\W*(whey|protein blend|hydrolysed whey)", re.I)
SWEET = re.compile(r"pe+dh?a|shrikhand|kheer|kulfi|rabdi|rabri|barfi|burfi|kalakand|rasgul+a|rasmalai|sandesh|halwa", re.I)
WHITENER = re.compile(r"whitener|condensed|milkmaid", re.I)
DRINK = re.compile(r"flavou?r|shake|lassi|\bkool\b|doodh|coffee|caramel|toffee|taak|chaa?ch|buttermilk|probiotic|yakult|"
                   r"choc|kesar|badam|elaichi", re.I)
SUGAR_EARLY = re.compile(r"^[^,]*,\s*sugar|^\W*water,\s*sugar", re.I)
ORDER = ["plain milk, cream, curd or milk powder", "cheese or paneer", "sweet milk drink", "dairy sweet", "whitener or condensed milk",
         "protein powder", "infant milk food"]


def kind(name, ing, tags=""):
    if PROTEIN_NAME.search(name) or PROTEIN_LIST.search(ing):
        return "protein powder"
    if re.search(r"infant", name, re.I):
        return "infant milk food"
    if {"en:cheeses", "en:paneer"} & set(tags.split(",")):  # before the drink words: a "pepper flavour" cheese spread is cheese
        return "cheese or paneer"
    if SWEET.search(name) and not re.search(r"shake|lassi", name, re.I):  # a rabdi milkshake is a drink
        return "dairy sweet"
    if WHITENER.search(name):
        return "whitener or condensed milk"
    if DRINK.search(name) or (not name.strip() and SUGAR_EARLY.search(ing)):
        return "sweet milk drink"
    return "plain milk, cream, curd or milk powder"


def main():
    seen, rows = set(), []
    with SRC.open(encoding="utf-8") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            c = row.get("code")
            if not c or c in seen:
                continue
            seen.add(c)
            if bucket(row.get("categories_tags", "")) != DAIRY:
                continue
            ing = (row.get("ingredients_text") or row.get("ingredients_text_en") or "").strip()
            a = analyse(ing) if len(ing) >= 8 and ing.isascii() else None
            if not a:  # same base as analyse.py: an English ingredient list
                continue
            name = row.get("product_name") or ""
            rows.append({"name": name, "ing": ing, "kind": kind(name, ing, row.get("categories_tags", "")), "sugar": a["n_sugar_names"] > 0,
                         "top3": bool(a["sugar_in_top3"])})
    by = defaultdict(list)
    for r in rows:
        by[r["kind"]].append(r)
    res = json.loads((HERE / "out" / "results.json").read_text(encoding="utf-8"))["categories"][DAIRY]
    n, k = len(rows), sum(r["sugar"] for r in rows)
    # the split must add up to the published row, or it is splitting something else
    assert n == res["with_ingredient_list"], (n, res["with_ingredient_list"])
    assert round(100 * k / n, 1) == res["pct_any_added_sugar"], (k, n, res["pct_any_added_sugar"])
    out = {"source": "Open Food Facts, products tagged as sold in India (ODbL); base = analyse.py's "
                     "'Dairy (milk, paneer, cheese)' bucket, lists in English",
           "lists": n, "name_added_sugar": k,
           "groups": {g: {"lists": len(by[g]), "name_added_sugar": sum(r["sugar"] for r in by[g]),
                          "sugar_in_first_3": sum(r["top3"] for r in by[g])} for g in ORDER}}
    assert sum(v["lists"] for v in out["groups"].values()) == n
    (HERE / "out" / "dairy_split.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps(out, indent=1))
    if "--show" in sys.argv:
        for r in sorted(rows, key=lambda r: (ORDER.index(r["kind"]), not r["sugar"])):
            print(("S " if r["sugar"] else "  ") + f"{r['kind'][:12]:12s} | {r['name'][:40]:40s} | {r['ing'][:60]}")


if __name__ == "__main__":
    main()
