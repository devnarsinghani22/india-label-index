"""India Label Index, Milk Day cut (11 Oct 2026): ready-to-drink sweet milk drinks vs plain milk.
Base: India-tagged Open Food Facts products in the Dairy and Milk drinks buckets of analyse.py.
Drinks = flavoured milk, milkshakes, lassi, thandai, kesar/badam/elaichi milk, milk coffee, sold ready to drink.
Out on purpose: powders and malt drinks, condensed milk, chocolate bars mis-tagged as milk, probiotic and
fermented drinks, buttermilk/chaas (savoury), and anything with "protein" in the name. Plain milk = milk with
no flavour word. Output: out/milk_drinks.json (counts only, no brand or product names).
Run: python -I milk_drinks.py [--show]   (--show prints names for the local audit only; never publish them)"""
import csv, json, re, statistics as st, sys
from pathlib import Path
HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from analyse import bucket, SRC, num
from sugar import analyse
csv.field_size_limit(2**31 - 1)

SWEET_NAME = re.compile(r"flavou?re?d?\s*milk|milk\s*shake|milkshake|\bshake\b|lassi|thandai|doodh|\bkool\b|badam|kesar|"
                        r"saffron|elaichi|pista|chocolate milk|coffee|latte|rabdi", re.I)
DRINK_TAGS = {"en:flavoured-milks", "en:milk-drinks", "en:dairy-drinks", "en:milkshakes", "en:sterilised-flavoured-standardized-milk"}
OUT_NAME = re.compile(r"protein|powder|\bmix\b|premix|whitener|condensed|milkmaid|health drink|chhach|chaach|chach|buttermilk|"
                      r"\btaak\b|yakult|probiotic", re.I)
OUT_TAGS = {"en:cocoa-and-chocolate-powders", "en:malted-drinks", "en:chocolate-drink-powders", "en:instant-beverages",
            "en:dehydrated-beverages", "en:milk-powders", "en:dairy-whitener", "en:whey-powder", "en:condensed-milks",
            "en:fermented-drinks", "en:buttermilks", "en:protein-powders", "en:baby-foods", "en:baby-milks",
            "en:infant-formulas", "en:plant-based-milk-alternatives", "en:milk-substitutes", "en:chocolates"}
# a ready-to-drink milk drink's list starts with milk, water or curd; sugar or malt first = a powder, bar or syrup
FIRST_OK = re.compile(r"^\W*(water|pasteuri[sz]ed|chilled|double\s*ton+ed|ton+ed|standardi[sz]ed|skimmed|whole|full\s*cream|"
                      r"milk|curd|dahi|cow|buffalo)", re.I)
PLAIN_TAGS = {"en:milks", "en:cow-milks", "en:toned-milks", "en:uht-milks", "en:pasteurised-milks", "en:homogenized-milks",
              "en:whole-milks", "en:semi-skimmed-milks", "en:skimmed-milks", "en:buffalo-milks", "en:double-toned-milks",
              "en:dairy-drinks"}
PLAIN_OUT = re.compile(r"protein|lactose|calci|camel|shake|flavou?r|choc|badam|kesar|pista|lassi|chaa?ch|butter|masala|"
                       r"paneer|cheese|cream\b|slim|curd|dahi", re.I)


def load():
    seen, drinks, plain = set(), [], []
    with SRC.open(encoding="utf-8") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            c = row.get("code")
            if not c or c in seen:
                continue
            seen.add(c)
            if bucket(row.get("categories_tags", "")) not in ("Dairy (milk, paneer, cheese)", "Milk drinks and health drink powders"):
                continue
            tags = {t for t in row["categories_tags"].split(",") if t}
            name = row.get("product_name") or ""
            ing = (row.get("ingredients_text") or row.get("ingredients_text_en") or "").strip()
            a = analyse(ing) if len(ing) >= 8 and ing.isascii() else None
            s = num(row.get("sugars_100g"))
            if s is not None and not (0 <= s <= 100):
                s = None
            rec = {"code": c, "name": name, "ing": ing, "a": a, "sugar": s}
            if tags & OUT_TAGS or OUT_NAME.search(name):
                continue
            if tags & DRINK_TAGS and SWEET_NAME.search(name):
                if ing and not FIRST_OK.search(ing):
                    continue
                drinks.append(rec)
            elif tags & PLAIN_TAGS and not PLAIN_OUT.search(name) and not SWEET_NAME.search(name):
                if a and a["n_sugar_names"] == 0:
                    plain.append(rec)
    return drinks, plain


def summary(xs):
    li = [x for x in xs if x["a"]]
    sv = sorted(x["sugar"] for x in li if x["sugar"] is not None)
    return {"products": len(xs), "with_english_list": len(li),
            "list_names_added_sugar": sum(x["a"]["n_sugar_names"] > 0 for x in li),
            "sugar_in_first_3": sum(bool(x["a"]["sugar_in_top3"]) for x in li),
            "with_sugar_value": len(sv), "median_total_sugar_g_per_100": round(st.median(sv), 1) if sv else None,
            "sugar_values_min_max": [round(sv[0], 1), round(sv[-1], 1)] if sv else None}


def main():
    drinks, plain = load()
    out = {"source": "Open Food Facts, India-tagged products (data/off_india.csv, pulled 1 Oct 2026); ODbL",
           "ready_to_drink_sweet_milk_drinks": summary(drinks), "plain_milk_no_sugar_named": summary(plain),
           "note": "Total sugar per 100 g or ml as entered on Open Food Facts; plain milk's sugar is its own lactose. "
                   "Small samples: say k of n. Category level only."}
    (HERE / "out" / "milk_drinks.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps(out, indent=2))
    if "--show" in sys.argv:
        for tag, xs in (("D", drinks), ("P", plain)):
            for x in xs:
                if x["a"]:
                    print(tag, "SUG" if x["a"]["n_sugar_names"] else "---", x["sugar"], "|", x["name"][:38], "|", x["ing"][:75])


if __name__ == "__main__":
    main()
