"""Which fat is in the pack? Reads every Indian ingredient list (data/off_india.csv) that names a fat or oil and
sorts it into: palm (palm oil, palmolein, palm kernel, palm stearin, palm fat), another named plant oil
(sunflower, rice bran, soybean, mustard, groundnut, coconut, olive, cottonseed, canola, corn, sesame, safflower),
dairy fat (butter, ghee, cream, milk fat), or an oil named only as "vegetable oil" / "edible oil" with no plant given.
Also counts hydrogenated / vanaspati / shortening / interesterified mentions.
Output: out/fats.json. Category-level only; no brands. Same buckets as analyse.py; baby food and supplements excluded.
Reads lists in English: at least two everyday English ingredient words (english_list), so a stray accent or a second
language printed alongside does not drop a list. Run: python fats.py   (python -I fats.py works too)"""
import csv
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from analyse import ADDED_SUGAR_RELEVANT_EXCLUDE, bucket  # noqa: E402

csv.field_size_limit(2**31 - 1)

# "palm sugar", "palm jaggery", "palmyra", "palmitate" (vitamin A), "palm hearts" and the fruit itself ("palm fruit",
# e.g. ice apple) are not palm oil. "Palm fruit oil" IS palm oil (a common US label name for it).
# Misspelt palmitate is not palm oil either: "ascorbyl palmate", "vitamin A palminate / palmtate / palmiate / palmatate"
# (palm + up to 4 of a i y n l t + "at" + ending). "Palmfat" still counts: the f is not in that set.
PALM_RE = re.compile(r"\bpalm(?!it|yra|[aiíīynlt]{0,4}at(?:e|es|el|o|a)?\b|\s*(?:sugar|jaggery|candy|nectar|syrup|heart|date)|\s*fruit(?!\s*(?:oil|fat|olein|shortening)))"
                     r"(?:olein|\s*fruit\s*oil|\s*kernel|\s*oil|\s*fat|\s*stearin|\s*shortening|\s*olein)?\w*", re.I)
PLANTS = (r"sun ?flower|rice ?bran|soya?(?: ?bean)?|mustard|groundnut|peanut|coconut|olive|cotton ?seed|canola|rapeseed|corn|maize|sesame|"
          r"gingelly|safflower|kardi|linseed|flaxseed|almond|walnut|avocado")
NAMED_RE = re.compile(r"\b(" + PLANTS + r")\s*(?:seed\s*)?oil\b", re.I)
DAIRY_RE = re.compile(r"\b(butter|ghee|cream|milk fat|milk solids|butterfat|dairy fat|anhydrous milk fat|amf)\b", re.I)
FAT_RE = re.compile(r"\b(oil|oils|fat|fats|ghee|butter|shortening|margarine|vanaspati|palmolein)\b", re.I)
HYDRO_RE = re.compile(r"hydrogenated|vanaspati|shortening|interesterified|inter-esterified", re.I)
VEGONLY_RE = re.compile(r"(edible\s+)?(refined\s+)?(vegetable|veg\.?|cooking|edible|refined)\s+(oil|fat)s?\b", re.I)
NAMES = {"sunflower": "sunflower", "sun flower": "sunflower", "rice bran": "rice bran", "ricebran": "rice bran", "soyabean": "soybean", "soybean": "soybean",
         "soya": "soybean", "soy": "soybean", "soya bean": "soybean", "soy bean": "soybean", "mustard": "mustard", "groundnut": "groundnut", "peanut": "groundnut", "coconut": "coconut",
         "olive": "olive", "cottonseed": "cottonseed", "cotton seed": "cottonseed", "canola": "canola", "rapeseed": "canola",
         "corn": "corn", "maize": "corn", "sesame": "sesame", "gingelly": "sesame", "safflower": "safflower", "kardi": "safflower",
         "linseed": "flaxseed", "flaxseed": "flaxseed", "almond": "almond", "walnut": "walnut", "avocado": "avocado"}


PLANT_RE = re.compile(r"\b(" + PLANTS + r")\b", re.I)
BRACKET_RE = re.compile(r"(?:oil|oils|fat|fats)\s*[\(\[\{]([^\)\]\}]{1,120})[\)\]\}]", re.I)
# "Sunflower, safflower and/or canola oil": several plants share one word "oil". Each one is a named oil.
_MOD = r"(?:(?:high|mid)[- ]?oleic\s+|expeller[- ]pressed\s+|cold[- ]pressed\s+|organic\s+|refined\s+|non[- ]gmo\s+)*"
_ELEM = _MOD + r"(?:" + PLANTS + r"|palm(?:\s*kernel)?)"
_JOIN = r"(?:\s*,\s*(?:(?:and\s*/\s*or|and|or|&)\s+)?|\s+(?:and\s*/\s*or|and|or)\s+|\s*(?:&|/)\s*)"
CHAIN_RE = re.compile(r"\b" + _ELEM + r"(?:" + _JOIN + _ELEM + r")+\s*(?:seed\s*)?oils?\b", re.I)
_PART_RE = re.compile(r"(" + _ELEM + r")(" + _JOIN + r")?", re.I)
# Plant words that are also foods. When one opens a chain and only a bare comma follows it, it is a separate
# ingredient ("Whole corn, sunflower and/or canola oil" names sunflower and canola oil, not corn oil).
FOOD_WORD_RE = re.compile(r"^(?:corn|maize|peanut|groundnut|coconut|almond|walnut|sesame|olive|avocado|soya?(?: ?bean)?|linseed|flaxseed|"
                          r"mustard|rice ?bran)$", re.I)
EN_WORDS_RE = re.compile(r"\b(salt|sugar|oils?|water|flour|wheat|potato(?:es)?|spices?|starch|powder|flavou?r(?:ing)?s?|milk|contains?|and|"
                         r"vegetable|ingredients?|acid|extract|natural|dried|seasoning|corn|rice|cheese|onion|garlic|yeast|whey|"
                         r"sunflower|rapeseed|palm|refined|edible)\b", re.I)


def english_list(txt):
    """Can the English matchers read this list? Yes when it is in plain Latin letters with at most MAX_STRAY accented or
    other non-English letters (a "jalapeno" with a tilde, a stray character from the photo), or when it uses at least two
    everyday English ingredient words (a pack that prints English next to Hindi, French or Arabic). Symbols such as a
    trademark sign or a curly quote are not letters and never count against a list."""
    txt = (txt or "").strip()
    if len(txt) < 8:
        return False
    if sum(1 for ch in txt if ch.isalpha() and not ch.isascii()) <= MAX_STRAY:
        return True
    return len({m.lower() for m in EN_WORDS_RE.findall(txt)}) >= 2


MAX_STRAY = 3


def oil_name(m):
    m = re.sub(r"\s+", " ", m.strip().lower())
    return NAMES.get(m, m)


def chain_names(ing):
    out = set()
    for m in CHAIN_RE.finditer(ing):
        parts = [(re.sub(_MOD, "", e, flags=re.I).strip(), j or "") for e, j in _PART_RE.findall(m.group(0))]
        while len(parts) > 1 and parts[0][1].strip() == "," and FOOD_WORD_RE.match(parts[0][0]):
            parts = parts[1:]
        out |= {oil_name(e) for e, _ in parts if not e.lower().startswith("palm")}
    return out


def classify(ing):
    """Return (has_fat, palm, named_set, dairy, unnamed_only, hydro)."""
    if not FAT_RE.search(ing):
        return False, False, set(), False, False, False
    palm = bool(PALM_RE.search(ing))
    named = {oil_name(m) for m in NAMED_RE.findall(ing)}
    # "Edible Vegetable Oil (Sunflower, Rice Bran)": the plant is named inside the bracket after the word oil
    for inner in BRACKET_RE.findall(ing):
        named |= {oil_name(m) for m in PLANT_RE.findall(inner)}
    named |= chain_names(ing)
    dairy = bool(DAIRY_RE.search(ing))
    hydro = bool(HYDRO_RE.search(ing))
    unnamed_only = (not palm) and (not named) and (not dairy) and bool(VEGONLY_RE.search(ing) or HYDRO_RE.search(ing))
    return True, palm, named, dairy, unnamed_only, hydro


def selftest():
    palm_yes = ["Potato, Edible Vegetable Oil (Palmolein), Salt", "palm oil", "Palm Kernel Oil", "vegetable oil (palm)",
                "Refined Palm Oil, Spices", "PALMOLEIN OIL", "palm fat", "Palm Stearin", "fully hydrogenated palm kernel oil",
                "Potatoes, Palm Fruit Oil, Salt", "organic red palm fruit oil", "palm fruit shortening",
                "Wheat flour, palmfat, sugar", "Vegetable oil (canola, cottonseed, palmi, sed starch", "Palmolien, salt"]
    palm_no = ["Potato, Sunflower Oil, Salt", "Palm Sugar, Rice Flour, Rice Bran Oil", "Palm Jaggery, Groundnut Oil",
               "Palmyra Sprout Flour, Coconut Oil", "Vitamin A Palmitate, Milk Fat", "Ascorbyl palmitate, sunflower oil",
               "Corn, Canola Oil, Salt", "Palm fruit (ice apple) 40%, sugar, sunflower oil", "palm fruit jelly, coconut oil",
               "white corn, canola oil, sunflower oil (contains ascorbyl palmate), salt, calcium hydroxide",
               "Milk, vitamin A palminate, vitamin D3", "Fat free milk, vitamin a palmtate", "VITAMIN A PALMIATE, REDUCED IRON",
               "vitamin A palmatate, sunflower oil", "Vitamin A palmítate, canola oil"]
    for s in palm_yes:
        assert PALM_RE.search(s), s
    for s in palm_no:
        assert not PALM_RE.search(s), s
    named = {"Potatoes, sunflower and/or safflower oil, salt": {"sunflower", "safflower"},
             "Potatoes, Sunflower, safflower and/or canola oil, salt": {"sunflower", "safflower", "canola"},
             "Whole Corn, Sunflower and/or Canola Oil, Whole Wheat": {"sunflower", "canola"},
             "Potatoes, Sunflower and Rapeseed Oil (in varying proportions), Salt": {"sunflower", "canola"},
             "Corn, Vegetable Oil (Corn, Canola, and/or Sunflower Oil), Salt": {"corn", "canola", "sunflower"},
             "Stone ground white corn, expeller pressed corn or sunflower seed oil, sea salt": {"corn", "sunflower"},
             "potatoes, high oleic sunflower and/or canola oil": {"sunflower", "canola"},
             "Potatoes, palm and/or sunflower oil": {"sunflower"}, "Potatoes, sunflower, palm and/or canola oil": {"sunflower", "canola"},
             "Rice Bran & Sunflower Oil": {"rice bran", "sunflower"}, "Soy bean oil, Soy oil, Soya Bean Oil": {"soybean"},
             "Edible Vegetable Oil (Palmolein, Rice Bran Oil)": {"rice bran"}, "Corn, Canola Oil, Salt": {"canola"},
             "Whole grain corn, sunflower oil, salt": {"sunflower"}, "Peanuts, sunflower oil": {"sunflower"},
             "Sesame seeds and sunflower oil": {"sunflower"},
             # two-word spelling on some Indian packs (worker, 9 Oct 2026; first seen by the study 7 verifier)
             "Gram Dhal Flour, Ghee, Dry Fruits, Sugar, Elachi, Refined Sun Flower oil.": {"sunflower"},
             "Edible Vegetable Oil (Sun Flower, Rice Bran)": {"sunflower", "rice bran"},
             "Sun flower seeds, sun dried flower petals, coconut oil": {"coconut"}}
    for s, want in named.items():
        got = classify(s)[2]
        assert got == want, (s, got)
    assert english_list("Potatoes, sunflower oil, salt") and english_list("Potatoes, Palm Fruit Oil, Sea Salt. Jalape\u00f1o")
    assert english_list("Banana 79 %, Palm Oil 20%, Salt. INGR\u00c9DIENTS: Banane 79%, Huile de palme 20%, Sel")
    assert english_list("Edible Vegetable Oil (Palmolein)\u00ae, Salt\u2122") and english_list("Turmeric powder")
    assert not english_list("Kartoffeln, Sonnenblumen\u00f6l, Speisesalz, Gew\u00fcrze, W\u00fcrze, S\u00e4uerungsmittel")
    assert not english_list("Pommes de terre, huile v\u00e9g\u00e9tale, ar\u00f4me, \u00e9pices, s\u00e9l\u00e9ction")
    assert not english_list("\u0906\u0932\u0942, \u0924\u0947\u0932, \u0928\u092e\u0915 \u0914\u0930 \u092e\u0938\u093e\u0932\u0947")
    print("fats selftest OK")


def main():
    selftest()
    rows = csv.DictReader((HERE / "data" / "off_india.csv").open(encoding="utf-8"), delimiter="\t")
    lists = 0
    recs = []
    for r in rows:
        ing = (r.get("ingredients_text") or "").strip()
        if not english_list(ing):
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
        k = {"palm": sum(p["palm"] for p in ps),
             "named_other_only": sum(1 for p in ps if p["named"] and not p["palm"]),
             "dairy_only": sum(1 for p in ps if p["dairy"] and not p["palm"] and not p["named"]),
             "unnamed_vegetable_oil": sum(p["unnamed"] for p in ps),
             "hydrogenated_or_vanaspati": sum(p["hydro"] for p in ps)}
        # counts kept so a page can round each share once, from count / with_fat
        return {"with_fat": n, **{"pct_" + key: round(100 * v / n, 1) for key, v in k.items()},
                "named_oils": {o: round(100 * v / n, 1) for o, v in oils.most_common(8)},
                "counts": dict(k, named_oils=dict(oils.most_common(8)))}

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
