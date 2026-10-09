"""The Diwali box: what the labels on packaged mithai and namkeen say (India Label Index, 9 October 2026).

Which products are mithai or namkeen: festive_labels.csv (barcode -> type, sorted by hand). Open Food Facts tags almost
no Indian sweets as such (1 product sold in India), so the sets had to be built. A local model (qwen3:14b on Ollama) first
sorted the 1,382 Indian ingredient lists with no category, plus the tagged namkeen and confectionery lists and name
matches elsewhere (1,918 lists). A blind 50-row hand check of its sort was 39 right (78%), under the 90% bar, so the model
sort was not used. Instead: regex on product names and category tags, the model's picks and an ingredient-word sweep made
a candidate pool, and every candidate was read and labelled by hand (column model_type keeps the model's answer, or
not_sent). Types:
  mithai  = a ready-to-eat traditional Indian sweet: soan papdi, laddoo, barfi, peda, kaju katli, petha, gulab jamun,
            rasgulla, ghari and the like. Left out: chikki, gajak and other brittles; mixes; puddings and curd desserts
            (kheer, rabri, shrikhand); kulfi and ice cream; toffees; date-and-nut "laddoos" sold as health snacks.
  namkeen = a savoury Indian snack, fried or roasted: bhujia, sev, mixture, chivda, chakli, murukku, mathri, khakhra,
            bhakarwadi, fried dal, boondi, gathiya, coated or salted peanuts, flavoured makhana, soya sticks, banana chips.
            Left out: potato chips, corn and other extruded snacks, popcorn, crackers, raw dal, papad, plain nuts.
Lists that are not an ingredient list (an address, a date, a nutrition table typed into the field) were left out.
Measures, each with its count k and base n (pages round once, from k / n):
  sugar   = Label Checker rules (sugar.py): any sugar name, a sugar as the 1st or 2nd ingredient (top-level item,
            outside brackets, like analyse.py's first-3 rule), 2 or more sugar names, which names
  fats    = fats.py matchers: palm, hydrogenated / vanaspati / shortening / interesterified, ghee, plant fat or oil
  colours = a colour declared (the word colour, a colour INS/E number 100-199, or a named dye), synthetic colours
            (the words synthetic / artificial colour, a synthetic INS number, or a named synthetic dye)
  INS     = every INS / E number in the list, bracketed runs like "Colours (102, 110)" included, plus dyes named in words
  FSSAI   = fssai.py's test (ICMR-NIN limits cited by FSSAI, any 1 of added sugar, added fat, salt high; supplements out)
Output: out/diwali.json, out/diwali_table.csv. Category level only; brand names are never output.
Run: python -I diwali.py"""
import csv
import json
import re
import statistics as st
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from sugar import KINDS, NAMES, analyse, find_sugars, top_items  # noqa: E402
from analyse import bucket, num  # noqa: E402
from fats import HYDRO_RE, PALM_RE, VEGONLY_RE, classify  # noqa: E402
import fssai as fs  # noqa: E402  (loads warnings.py by path, so -I is safe)

csv.field_size_limit(2**31 - 1)
SRC = HERE / "data" / "off_india.csv"
LABELS = HERE / "festive_labels.csv"
MODEL = HERE / "festive_model.csv"   # the local model's sort (qwen3:14b) and the 50-row blind hand check
OUT = HERE / "out"
SETS = ("mithai", "namkeen")

# fats.py reads "sunflower" as one word; one mithai list writes "Refined Sun Flower oil" (found by the verifier, 9 Oct 2026).
# Counted here as a plant oil so that list is not "ghee only". fats.py reads it too since 9 Oct 2026 (study 4 sunflower
# 10.3% -> 10.4%, study 5 US crisps sunflower 2,000 -> 2,002 of 2,779, 72.0% either way; correction lines on both pages).
SUN_FLOWER_RE = re.compile(r"\bsun\s+flower\s*(?:seed\s*)?oils?\b", re.I)
GHEE_RE = re.compile(r"\b(?:desi\s+)?ghee\b|clarified\s+butter|butter\s*oil|\bbutterfat\b|anhydrous\s+milk\s+fat|\bamf\b", re.I)

# ---------------------------------------------------------------- INS / E numbers
ROMAN_RE = re.compile(r"\s*\(\s*(i{1,3}|iv|vi{0,3}|ix|x)\s*\)", re.I)
_CODE = r"(\d{3,4})(?:\s?([a-f])(?![a-z]))?(?:_[ivx]+)?"
PREFIXED_RE = re.compile(r"(?<![A-Za-z0-9])(?:INS|E)\s*(?:No\.?\s*)?[\(\[:.\-]?\s*" + _CODE + r"(?![\d%])", re.I)
BRACKET_RE = re.compile(r"[\(\[]([^\(\)\[\]]{1,160})[\)\]]")
PREFIX_STRIP_RE = re.compile(r"(?<![A-Za-z])(?:INS|E)\s*(?:No\.?\s*)?[:.\-]?\s*(?=\d)", re.I)
RUN_RE = re.compile(r"^\s*" + _CODE + r"(?:\s*(?:,|&|/|;|\band\b)?\s*" + _CODE + r")*\s*$", re.I)
CODE_RE = re.compile(_CODE, re.I)


def valid(num_s):
    v = int(num_s)
    return 100 <= v <= 1599


def ins_codes(text):
    """Set of additive codes ('330', '150c', '500') named in an ingredient list, as INS 330, INS-330, E330, or a bracketed
    run of bare numbers such as 'Colours (102, 110)' or 'Raising agents [500(ii) & 503(ii)]'. Roman sub-numbers are
    dropped, so 500(i) and 500(ii) both count as 500. Percentages, weights and years are not codes."""
    t = ROMAN_RE.sub(lambda m: "_" + m.group(1).lower(), text or "")
    out = set()
    for m in PREFIXED_RE.finditer(t):
        if valid(m.group(1)):
            out.add(m.group(1) + (m.group(2) or "").lower())
    for m in BRACKET_RE.finditer(t):
        inner = PREFIX_STRIP_RE.sub("", m.group(1))
        if RUN_RE.match(inner):
            for c in CODE_RE.finditer(inner):
                if valid(c.group(1)):
                    out.add(c.group(1) + (c.group(2) or "").lower())
    return out


# ---------------------------------------------------------------- colours
COLOUR_WORD_RE = re.compile(r"\bcolou?r(?:s|ed|ing|ings)?\b", re.I)
NEG_RE = re.compile(r"(?:\bno|\bnot|without|free\s+from|\bzero|\bnil)\b[^,.;:()\[\]]{0,30}$", re.I)
SYN_WORD_RE = re.compile(r"(?:synthetic|artificial)\s+(?:food\s+)?colou?r|colou?rs?\s*[\(:]\s*(?:synthetic|artificial)", re.I)
DYES_RE = re.compile(r"tartrazine|sunset\s+yellow|carmoisine|azorubine|ponceau|allura\s+red|brilliant\s+blue|erythrosine?|"
                     r"indigo\s+carmine|indigotine|fast\s+green|\b(?:red|yellow|blue)\s*(?:no\.?\s*)?(?:40|3|5|6|1|2)\b(?:\s*lake)?|fd\s*&\s*c", re.I)
# synthetic colours by INS number (Codex): 102 tartrazine, 104 quinoline yellow, 110 sunset yellow FCF, 122 carmoisine,
# 123 amaranth, 124 ponceau 4R, 127 erythrosine, 129 allura red, 132 indigo carmine, 133 brilliant blue FCF,
# 142 green S, 143 fast green FCF, 151 brilliant black, 155 brown HT
SYN_CODES = {"102", "104", "110", "122", "123", "124", "127", "129", "132", "133", "142", "143", "151", "155"}


# named dyes -> their INS number, so "FD & C Yellow No.5" or "Sunset Yellow" count as 102 / 110 even with no number
DYE_CODES = [(re.compile(p, re.I), c) for p, c in (
    (r"tartrazine|\byellow\s*(?:no\.?\s*)?5\b", "102"), (r"sunset\s+yellow|\byellow\s*(?:no\.?\s*)?6\b", "110"),
    (r"carmoisine|azorubine", "122"), (r"ponceau", "124"), (r"erythrosine?|\bred\s*(?:no\.?\s*)?3\b", "127"),
    (r"allura\s+red|\bred\s*(?:no\.?\s*)?40\b", "129"), (r"indigo\s+carmine|indigotine|\bblue\s*(?:no\.?\s*)?2\b", "132"),
    (r"brilliant\s+blue|\bblue\s*(?:no\.?\s*)?1\b", "133"), (r"fast\s+green", "143"))]
# "Turmeric (colouring and spices)" is turmeric the spice, written with FSSAI's class title; it is not an added colour
TURMERIC_RE = re.compile(r"turmeric\s*[\(\[]\s*$", re.I)


def colours(text, codes):
    """-> (declares a colour, synthetic colour, colour codes)."""
    t = text or ""
    words = [m for m in COLOUR_WORD_RE.finditer(t) if not NEG_RE.search(t[max(0, m.start() - 40):m.start()])
             and not TURMERIC_RE.search(t[max(0, m.start() - 20):m.start()])]
    syn_words = [m for m in SYN_WORD_RE.finditer(t) if not NEG_RE.search(t[max(0, m.start() - 40):m.start()])]
    ccodes = {c for c in codes if 100 <= int(re.match(r"\d+", c).group()) <= 199} | {c for rx, c in DYE_CODES if rx.search(t)}
    dyes = bool(DYES_RE.search(t))
    synthetic = bool(syn_words) or bool({re.match(r"\d+", c).group() for c in ccodes} & SYN_CODES) or dyes
    return bool(words) or bool(ccodes) or dyes, synthetic, ccodes


# ---------------------------------------------------------------- sugar position
SPLIT_RE = re.compile(r"\s*&\s*|\s+and\s+|\.\s+(?=[A-Za-z])", re.I)


def items(text):
    """Top-level ingredients (start, end): sugar.py's split on , and ; outside brackets, then each item split again on
    '&', 'and' and a full stop between words, outside brackets. 'Milk solids & Sugar' is 2 ingredients, so sugar is
    2nd there, not 1st; 'Gram flour. Clarified butter, Sugar' is 3."""
    out = []
    for a, z in top_items(text):
        depth, frm, k = 0, a, a
        while k < z:
            c = text[k]
            if c in "([{":
                depth += 1
            elif c in ")]}" and depth:
                depth -= 1
            elif depth == 0:
                m = SPLIT_RE.match(text, k, z)
                if m and m.end() > k:
                    if text[frm:k].strip():
                        out.append((frm, k))
                    frm = k = m.end()
                    continue
            k += 1
        if text[frm:z].strip():
            out.append((frm, z))
    return out


def first_item(text):
    it = items(text)
    return text[it[0][0]:it[0][1]] if it else ""


def sugar_rank(text):
    """0-based top-level position of the first sugar name that is not inside a bracket, or None."""
    items_ = items(text)
    best = None
    for s, e, i in find_sugars(text):
        if KINDS[i] != "sugar":
            continue
        for k, (a, z) in enumerate(items_):
            if a <= s < z:
                seg = text[a:s]
                if seg.count("(") + seg.count("[") > seg.count(")") + seg.count("]"):
                    break
                best = k if best is None else min(best, k)
                break
    return best


# ---------------------------------------------------------------- FSSAI (same test as fssai.py main(), any 1 high)
def fssai_high(r, ing):
    """-> list of high nutrients, or None when the nutrition table is incomplete (or the product is a supplement)."""
    sug, fat, salt = num(r.get("sugars_100g")), num(r.get("fat_100g")), num(r.get("salt_100g"))
    if salt is None and num(r.get("sodium_100g")) is not None:
        salt = num(r.get("sodium_100g")) * 2.5
    if None in (sug, fat, salt) or not (0 <= sug <= 100 and 0 <= fat <= 100 and 0 <= salt <= 100):
        return None
    if fs.is_supplement(r):
        return None
    add_sug = num(r.get("added-sugars_100g"))
    has_sugar = any(KINDS[i] == "sugar" for _, _, i in find_sugars(ing))
    if add_sug is not None and 0 <= add_sug <= sug + 0.5:
        sugar_val = add_sug
    else:
        sugar_val = sug if has_sugar else 0.0
    th = fs.LIQUID if fs.is_liquid(r.get("categories_tags", "")) else fs.SOLID
    high = []
    if sugar_val >= th["sugar"]:
        high.append("sugar")
    if fs.FAT_RE.search(ing) and fat >= th["fat"]:
        high.append("fat")
    if fs.SALT_RE.search(ing) and salt * 1000 >= th["salt_mg"]:
        high.append("salt")
    return high


def brand_key(tag):
    """Same grouping as world.py: spellings of one brand count once. Used only to count; never output."""
    return re.sub(r"[^a-z0-9]", "", re.sub(r"^[a-z]{2}:", "", tag.strip().lower()))[:5]


def top(counter, k, ties=False):
    """most_common with ties broken by name, so the output does not depend on Python's per-run set order.
    ties=True keeps every item tied with the k-th, so a cut never splits equal counts."""
    items = sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))
    if ties and len(items) > k:
        return [kv for kv in items if kv[1] >= items[k - 1][1]]
    return items[:k]


def share(k, n):
    return {"k": k, "n": n, "pct": round(100 * k / n, 1) if n else None}


def med(xs):
    return {"median": round(st.median(xs), 1) if xs else None, "n": len(xs)}


def model_check(labels):
    """How the local model's sort compares with the hand sort. It was not used for any number below."""
    with MODEL.open(encoding="utf-8") as f:
        mod = list(csv.DictReader(f))
    spot = [r for r in mod if r["spot_check_hand_type"]]
    hand = {c: r["type"] for c, r in labels.items()}
    mt = {r["code"]: r["model_type"] for r in mod}
    return {"model": "qwen3:14b on local Ollama, think off, JSON mode, temperature 0, 20 lists a call",
            "lists_sorted": len(mod),
            "spot_check": share(sum(1 for r in spot if r["model_type"] == r["spot_check_hand_type"]), len(spot)),
            "spot_check_design": "50 of the 1,382 lists with no category, drawn at random within the model's labels (15 mithai, 15 namkeen, "
                                 "10 other festive, 10 not festive), labelled by hand before the model's answers were shown; bar 90%",
            "found_mithai": share(sum(1 for c, t in hand.items() if t == "mithai" and mt.get(c) == "mithai"), sum(1 for t in hand.values() if t == "mithai")),
            "found_namkeen": share(sum(1 for c, t in hand.items() if t == "namkeen" and mt.get(c) == "namkeen"), sum(1 for t in hand.values() if t == "namkeen")),
            "false_mithai": sum(1 for c, t in mt.items() if t == "mithai" and hand.get(c) != "mithai"),
            "false_namkeen": sum(1 for c, t in mt.items() if t == "namkeen" and hand.get(c) != "namkeen")}


def selftest():
    assert ins_codes("Emulsifier (INS 322), Acidity Regulators (INS330 INS 525)") == {"322", "330", "525"}
    assert ins_codes("Colours (102, 133, 122, 110)") == {"102", "133", "122", "110"}
    assert ins_codes("Raising Agents [503(ii) & 500(ii)], Colours (150a & 150d)") == {"503", "500", "150a", "150d"}
    assert ins_codes("Acidity Regulators (INS 340 (ii), 340 (iii), 452), Colour (INS 150d)") == {"340", "452", "150d"}
    assert ins_codes("Antioxidant (E319), Flavour Enhancers (E627, E631), Colour [INS 160c(i)]") == {"319", "627", "631", "160c"}
    assert ins_codes("Preservative (INS-224), Stabilizer (INS No 412), Colour (INS.150d)") == {"224", "412", "150d"}
    assert ins_codes("Raisins (12%), Milk Solids (110 g), Best before 2027, Lic. No. 10012022000123") == set()
    assert ins_codes("Sugar, Gram flour (Besan) (35%), Ghee (10%)") == set()
    assert ins_codes("Vitamin E (E 306), Colour (162)") == {"306", "162"}
    assert ins_codes("potassium metabisulphite (e 224 contains sulphite)") == {"224"}
    assert ins_codes("Colours (INS 150c & INS 160c(i)), Natural Colour (100a)") == {"150c", "160c", "100a"}
    d, s, c = colours("Contains permitted synthetic food colour (INS 102)", ins_codes("Contains permitted synthetic food colour (INS 102)"))
    assert d and s and c == {"102"}
    t = "Gram flour, oil, salt. Contains no artificial colours or preservatives"
    assert colours(t, ins_codes(t))[:2] == (False, False)
    t = "Potato, oil, Natural Colour (INS 160c). No artificial colours"
    assert colours(t, ins_codes(t))[:2] == (True, False)
    t = "Sugar, milk solids, Colour (110)"
    assert colours(t, ins_codes(t))[:2] == (True, True)
    t = "Gram flour, oil, salt, turmeric (colouring & spices), cumin"
    assert colours(t, ins_codes(t))[:2] == (False, False)
    t = "Sugar syrup, chena. Contains permitted synthetic food colour (IE102)/ FD & C Yellow No.5) and [(E110) / FD & C Yellow No.6]"
    assert colours(t, ins_codes(t)) == (True, True, {"102", "110"})
    t = "Sugar, glucose, Contains Permitted Natural Colours & added artificial flavouring substances"
    assert colours(t, ins_codes(t))[:2] == (True, False)
    assert sugar_rank("Sugar, gram flour, ghee") == 0
    assert sugar_rank("Milk solids (60%), sugar (30%), cardamom") == 1
    assert sugar_rank("Chhena (milk, citric acid), sugar syrup (sugar, water)") == 1
    assert sugar_rank("Gram flour, oil, masala (salt, sugar, spices)") is None
    assert sugar_rank("Gram flour, oil, salt") is None
    assert SUN_FLOWER_RE.search("Gram Dhal Flour, Ghee, Dry Fruits, Sugar, Elachi, Refined Sun Flower oil.")
    assert not SUN_FLOWER_RE.search("Sunflower seeds, sun dried flower petals")
    assert sugar_rank("Ingredients: Refined wheat flour, Jaggery (40%), ghee") == 1
    assert sugar_rank("Milk Solids & Sugar, Contains Permitted Preservatives (INS 202 & INS 211)") == 1
    assert sugar_rank("Milk and Sugar") == 1 and sugar_rank("Sugar and liquid glucose, besan") == 0
    assert sugar_rank("Gram flour. Clarified Butter, Sugar, Cashews") == 2
    assert sugar_rank("Sugar syrup [(water (48.25%), sugar (46.7%) and sodium bisulphite (E223) (0.0025%))], chena (4.5%)") == 0
    assert sugar_rank("Cashew (0.1%). Raisin, sugar") == 2
    print("diwali selftest OK")


def main():
    selftest()
    labels = {}
    with LABELS.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            labels[r["code"]] = r
    rows, seen = [], set()
    with SRC.open(encoding="utf-8") as f:
        for r in csv.DictReader(f, delimiter="\t"):
            c = r.get("code")
            if not c or c in seen:
                continue
            seen.add(c)
            rows.append(r)
    lists = [r for r in rows if len((r.get("ingredients_text") or "").strip()) >= 8 and (r.get("ingredients_text") or "").strip().isascii()]
    uncategorised = sum(1 for r in lists if bucket(r.get("categories_tags", "")) is None)
    missing = [c for c in labels if c not in {r["code"] for r in lists}]
    assert not missing, f"labels for codes with no readable list: {missing[:5]}"

    recs = {k: [] for k in SETS}
    for r in lists:
        lab = labels.get(r["code"])
        if not lab or lab["type"] not in SETS:
            continue
        ing = r["ingredients_text"].strip()
        a = analyse(ing)
        has_fat, palm, named, dairy, unnamed, hydro = classify(ing)
        ghee = bool(GHEE_RE.search(ing))
        plant = palm or bool(named) or hydro or bool(VEGONLY_RE.search(ing)) or bool(SUN_FLOWER_RE.search(ing))
        codes = ins_codes(ing)
        col, syn, ccodes = colours(ing, codes)
        codes = codes | ccodes   # a dye named in words ("FD & C Yellow No.5") counts as its INS number (102)
        sug = num(r.get("sugars_100g"))
        salt = num(r.get("salt_100g"))
        if salt is None and num(r.get("sodium_100g")) is not None:
            salt = num(r.get("sodium_100g")) * 2.5
        fat = num(r.get("fat_100g"))
        recs[lab["type"]].append({
            "rank": sugar_rank(ing), "n_names": a["n_sugar_names"], "groups": a["sugar_groups"],
            "first_names": sorted({NAMES[g] for g in analyse(first_item(ing))["sugar_groups"]}),
            "has_fat": has_fat or ghee, "palm": palm, "hydro": hydro, "ghee": ghee, "plant": plant,
            "ghee_only": ghee and not plant, "ghee_and_palm": ghee and palm, "codes": codes, "colour": col, "synthetic": syn, "ccodes": ccodes,
            "fssai": fssai_high(r, ing),
            "sugar_g": sug if sug is not None and 0 <= sug <= 100 else None,
            "salt_g": salt if salt is not None and 0 <= salt <= 100 else None,
            "fat_g": fat if fat is not None and 0 <= fat <= 100 else None,
            "brands": {brand_key(t) for t in (r.get("brands_tags") or "").split(",") if t.strip()},
            "model_agreed": lab["model_type"] == lab["type"],
        })

    def summ(ps, headline):
        n = len(ps)
        fat = [p for p in ps if p["has_fat"]]
        tested = [p for p in ps if p["fssai"] is not None]
        names = Counter(NAMES[g] for p in ps for g in p["groups"])
        codes = Counter(c for p in ps for c in p["codes"])
        ccodes = Counter(c for p in ps for c in p["ccodes"])
        brands = Counter(b for p in ps for b in p["brands"])
        no_brand = sum(1 for p in ps if not p["brands"])
        top_brand, top_k = top(brands, 1)[0] if brands else (None, 0)
        rest = [p for p in ps if top_brand not in p["brands"]]
        hk = headline(rest)
        ft_b, ft_k = top(Counter(b for p in tested for b in p["brands"]), 1)[0] if tested else (None, 0)
        return {
            "lists": n,
            "sugar_any": share(sum(1 for p in ps if p["n_names"] > 0), n),
            "sugar_first": share(sum(1 for p in ps if p["rank"] == 0), n),
            "sugar_first_or_second": share(sum(1 for p in ps if p["rank"] is not None and p["rank"] <= 1), n),
            "sugar_2plus_names": share(sum(1 for p in ps if p["n_names"] >= 2), n),
            "sugar_3plus_names": share(sum(1 for p in ps if p["n_names"] >= 3), n),
            "sugar_names_count": {str(k): v for k, v in sorted(Counter(min(p["n_names"], 3) for p in ps).items())},
            "sugar_names": [{"name": nm, **share(k, n)} for nm, k in top(names, 8)],
            "fat_named": share(len(fat), n),
            "of_fat": {key: share(sum(1 for p in fat if p[key]), len(fat)) for key in ("palm", "hydro", "ghee", "ghee_only", "ghee_and_palm", "plant")},
            "colour_any": share(sum(1 for p in ps if p["colour"]), n),
            "colour_synthetic": share(sum(1 for p in ps if p["synthetic"]), n),
            "colour_codes": [{"code": c, **share(k, n)} for c, k in top(ccodes, 8, ties=True)],
            "ins_any": share(sum(1 for p in ps if p["codes"]), n),
            "ins_codes": [{"code": c, **share(k, n)} for c, k in top(codes, 12, ties=True)],
            "sugar_first_names": dict(Counter(nm for p in ps if p["rank"] == 0 for nm in p["first_names"])),
            "fssai": {"tested": len(tested), "warned_any1": share(sum(1 for p in tested if p["fssai"]), len(tested)),
                      "largest_brand_among_tested": share(ft_k, len(tested)),
                      "warned_without_largest_brand": share(sum(1 for p in tested if p["fssai"] and ft_b not in p["brands"]),
                                                            sum(1 for p in tested if ft_b not in p["brands"])),
                      "two_plus": share(sum(1 for p in tested if len(p["fssai"]) >= 2), len(tested)),
                      "by_nutrient": {k: share(sum(1 for p in tested if k in p["fssai"]), len(tested)) for k in ("sugar", "fat", "salt")}},
            "sugar_g_100g": med([p["sugar_g"] for p in ps if p["sugar_g"] is not None]),
            "salt_g_100g": med([p["salt_g"] for p in ps if p["salt_g"] is not None]),
            "fat_g_100g": med([p["fat_g"] for p in ps if p["fat_g"] is not None]),
            "brand_check": {"brands_spellings_merged": len(brands), "lists_without_brand_tag": no_brand,
                            "largest_brand": share(top_k, n), "headline_without_largest_brand": hk},
            "model_agreed_with_final_label": share(sum(1 for p in ps if p["model_agreed"]), n),
        }

    res = {
        "study": "The Diwali box (India Label Index, 9 October 2026)",
        "source": "Open Food Facts, products tagged as sold in India (data/off_india.csv, read 1 Oct 2026). ODbL.",
        "lists_in_english": len(lists),
        "lists_with_no_category": uncategorised,
        "labelled": dict(Counter(l["type"] for l in labels.values())),
        "model_check": model_check(labels),
        "note": ("Shares are {k, n, pct}: k lists of n. Sugar position = the first top-level ingredient that is a sugar name, "
                 "outside brackets. of_fat shares are of the lists that name a fat or oil (ghee included). FSSAI = any 1 of added "
                 "sugar, added fat, salt over the ICMR-NIN limits FSSAI cited (fssai.py), only for lists with a full nutrition "
                 "table, supplements out. Brand names are never output."),
        "mithai": summ(recs["mithai"], lambda ps: share(sum(1 for p in ps if p["rank"] == 0), len(ps))),
        "namkeen": summ(recs["namkeen"], lambda ps: share(sum(1 for p in ps if p["palm"] and p["has_fat"]), sum(1 for p in ps if p["has_fat"]))),
    }
    OUT.mkdir(exist_ok=True)
    (OUT / "diwali.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    table = []
    for s in SETS:
        v = res[s]
        for key in ("sugar_any", "sugar_first", "sugar_first_or_second", "sugar_2plus_names", "fat_named", "colour_any",
                    "colour_synthetic", "ins_any"):
            table.append((s, key, "", v[key]["k"], v[key]["n"], v[key]["pct"]))
        for key, sh in v["of_fat"].items():
            table.append((s, "of_lists_naming_a_fat", key, sh["k"], sh["n"], sh["pct"]))
        for x in v["sugar_names"]:
            table.append((s, "sugar_name", x["name"], x["k"], x["n"], x["pct"]))
        for x in v["colour_codes"]:
            table.append((s, "colour_code", "INS " + x["code"], x["k"], x["n"], x["pct"]))
        for x in v["ins_codes"]:
            table.append((s, "ins_code", "INS " + x["code"], x["k"], x["n"], x["pct"]))
        f = v["fssai"]
        table.append((s, "fssai_warning_any_1", "", f["warned_any1"]["k"], f["warned_any1"]["n"], f["warned_any1"]["pct"]))
        for k, sh in f["by_nutrient"].items():
            table.append((s, "fssai_high", k, sh["k"], sh["n"], sh["pct"]))
        for key in ("sugar_g_100g", "salt_g_100g", "fat_g_100g"):
            table.append((s, "median_" + key, "", "", v[key]["n"], v[key]["median"]))
    with (OUT / "diwali_table.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["set", "measure", "item", "k", "n", "value"])
        w.writerows(table)
    for s in SETS:
        v = res[s]
        print(f"== {s}: {v['lists']} lists")
        for key in ("sugar_any", "sugar_first", "sugar_first_or_second", "sugar_2plus_names", "fat_named", "colour_any", "colour_synthetic", "ins_any"):
            print(f"  {key:24} {v[key]['k']:4} of {v[key]['n']:4} = {v[key]['pct']}%")
        print("  of_fat", {k: f"{x['k']}/{x['n']}" for k, x in v["of_fat"].items()})
        print("  names", [(x["name"][:24], x["k"]) for x in v["sugar_names"]])
        print("  colour codes", [(x["code"], x["k"]) for x in v["colour_codes"]])
        print("  ins codes", [(x["code"], x["k"]) for x in v["ins_codes"]])
        print("  fssai", v["fssai"]["tested"], {k: f"{x['k']}/{x['n']}" for k, x in v["fssai"]["by_nutrient"].items()}, "any1", v["fssai"]["warned_any1"])
        print("  medians", v["sugar_g_100g"], v["salt_g_100g"], v["fat_g_100g"])
        print("  brands", v["brand_check"], "model agreed", v["model_agreed_with_final_label"])


if __name__ == "__main__":
    main()
