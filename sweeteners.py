"""The sweetener switch (study 11 candidate B, unpublished): which Indian packs list a non-sugar sweetener, which
sweeteners, how often next to an added sugar, and how India compares with the UK, US and France.

Inputs
  data/off_india.csv  (pull_csv.py, read 1 Oct 2026): every India number. Fields: ingredients_text, additives_tags,
                      labels_tags, product_name, categories_tags.
  data/off_multi.tsv  (pull_multi.py, read 6 Oct 2026): UK, US, France, same rules. Its India rows are printed only
                      as a cross-check.
Output: out/sweeteners.json and out/sweeteners_table.csv (every number with its count k and base n).
Category level only; no brands.

Two readings of every list
  text: this script's matcher on the ingredient text (English lists only, fats.english_list):
    - INS or E numbers: 950 acesulfame K, 951 aspartame, 952 cyclamate, 954 saccharin, 955 sucralose, 956 alitame,
      957 thaumatin, 959 neohesperidine DC, 960 steviol glycosides, 961 neotame, 962 aspartame-acesulfame salt,
      969 advantame (intense sweeteners, the WHO's "non-sugar sweeteners"); 420 sorbitol, 421 mannitol, 953 isomalt,
      964 polyglycitol, 965 maltitol, 966 lactitol, 967 xylitol, 968 erythritol (polyols). A number counts when it is
      written after INS or E ("INS 955", "E950"), or bare inside a bracket that follows a class word on Indian packs
      ("Sweetener (955)", "Humectant (420(ii))", "Sweeteners [965(i) & 955]") or a bracket that already has an INS
      number in it ("INS 951, 955"). A bare 420 elsewhere ("1 serve of cooked dish (420 g)") never counts.
    - the words: acesulfame, aspartame, cyclamate, saccharin, sucralose, thaumatin, neohesperidine, stevia / steviol /
      rebaudioside, neotame, advantame, monk fruit / mogroside, alitame; sorbitol, mannitol, isomalt, maltitol,
      lactitol, xylitol, erythritol, polyglycitol. "Sweetener" alone counts only in the phrase "artificial sweetener"
      (or "non-caloric / non-nutritive / intense sweetener"), as an unnamed intense sweetener. "No artificial
      sweetener", "sweetener free" and the like do not count.
  tag: Open Food Facts' own additives_tags (en:e950 and so on), which it reads from the list in any language. Works
    for France, where the matcher's English words do not. On Indian packs Open Food Facts reads INS numbers only
    some of the time (world.py's INS check), so for India the text reading is the headline and the tag the floor.
WHO (15 May 2023) counts the intense sweeteners as non-sugar sweeteners (NSS) and says polyols are not NSS, so the
two are kept apart everywhere: intense, polyol, any.

Measures (k of n; n = English lists in the group, baby food and supplements out)
  by category and country: intense, polyol, any; both = an added sugar name (sugar.py, the Label Checker's rules)
  AND an intense sweetener in the same list.
  which sweeteners: counts per sweetener among lists naming an intense one.
  India only: packs whose name says diet, sugar free, zero, lite, light, no sugar, no added sugar, unsweetened or keto:
  how many list an intense sweetener, a polyol, neither, and how many still name an added sugar.
  India only, warning check: of lists with an intense sweetener, how many carry a children / sweetener warning
  anywhere Open Food Facts could hold it: labels_tags, or the warning sentence pasted into the ingredient text.
Shares: pct = 100 * k / n rounded once here; a page rounds again from k and n.
Other countries shown on 100 or more lists; India needs 50 for a share.
Run: python -I sweeteners.py  (about 60 s)"""
import csv
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from analyse import bucket  # noqa: E402
from fats import english_list  # noqa: E402
from sugar import analyse as sugar_analyse  # noqa: E402

csv.field_size_limit(2**31 - 1)
OUT = HERE / "out"
MIN_N, MIN_INDIA_SHARE = 100, 50

C = {"en:india": "India", "en:united-kingdom": "UK", "en:united-states": "US", "en:france": "France"}
CATS = {
    "soft_drinks": {"en:sodas", "en:carbonated-drinks", "en:soft-drinks", "en:colas", "en:energy-drinks"},
    "juices": {"en:fruit-juices", "en:juices-and-nectars", "en:fruit-based-beverages", "en:nectars"},
    "milk_drinks": {"en:flavoured-milks", "en:milk-drinks", "en:dairy-drinks", "en:milkshakes", "en:malted-drinks",
                    "en:chocolate-drink-powders", "en:cocoa-and-chocolate-powders"},
    "biscuits": {"en:biscuits", "en:cookies"},
    "chocolate": {"en:chocolates", "en:chocolate-candies", "en:milk-chocolates", "en:dark-chocolates", "en:chocolate-bars"},
    "ice_cream": {"en:ice-creams", "en:ice-creams-and-sorbets", "en:frozen-desserts"},
    "yoghurt": {"en:yogurts", "en:fermented-milk-products", "en:dahi"},
    "gum_confectionery": {"en:chewing-gum", "en:candies", "en:confectioneries", "en:sweets", "en:mints"},
    "cereals": {"en:breakfast-cereals", "en:mueslis", "en:cereal-flakes", "en:granolas", "en:corn-flakes"},
    "sauces_spreads": {"en:sauces", "en:ketchup", "en:tomato-sauces", "en:spreads", "en:jams", "en:sweet-spreads"},
}
INTENSE = {"950": "acesulfame K", "951": "aspartame", "952": "cyclamate", "954": "saccharin", "955": "sucralose",
           "956": "alitame", "957": "thaumatin", "959": "neohesperidine DC", "960": "steviol glycosides",
           "961": "neotame", "962": "aspartame-acesulfame salt", "969": "advantame"}
POLYOL = {"420": "sorbitol", "421": "mannitol", "953": "isomalt", "964": "polyglycitol", "965": "maltitol",
          "966": "lactitol", "967": "xylitol", "968": "erythritol"}
WORDS = [(re.compile(p, re.I), name, kind) for p, name, kind in [
    (r"acesulfam", "acesulfame K", "intense"), (r"aspartam", "aspartame", "intense"), (r"cyclamat", "cyclamate", "intense"),
    (r"saccharin", "saccharin", "intense"), (r"sucralos", "sucralose", "intense"), (r"thaumatin", "thaumatin", "intense"),
    (r"neohesperidin", "neohesperidine DC", "intense"), (r"stevi[ao]|steviol|rebaudiosid", "steviol glycosides", "intense"),
    (r"neotam", "neotame", "intense"), (r"advantam", "advantame", "intense"), (r"alitam", "alitame", "intense"),
    (r"monk[\s-]?fruit|luo[\s-]?han|mogrosid", "monk fruit", "intense"),
    (r"sorbitol", "sorbitol", "polyol"), (r"mannitol", "mannitol", "polyol"), (r"isomalt\b", "isomalt", "polyol"),
    (r"maltitol", "maltitol", "polyol"), (r"lactitol", "lactitol", "polyol"), (r"xylitol", "xylitol", "polyol"),
    (r"erythritol", "erythritol", "polyol"), (r"polyglycitol|hydrogenated starch hydrolysate", "polyglycitol", "polyol")]]
UNNAMED_RE = re.compile(r"\b(?:artificial|non[\s-]?caloric|non[\s-]?nutritive|intense|high[\s-]intensity)\s+sweetn?e(?:r|ners?|rs)\b", re.I)
NEG_RE = re.compile(r"\b(?:no|not|without|free\s+(?:of|from)|zero|contains?\s+no|does\s+not\s+contain)\s+(?:added\s+|any\s+)?$", re.I)
FREE_AFTER_RE = re.compile(r"^[\s-]*free\b", re.I)
PREFIXED_RE = re.compile(r"(?:(?<![A-Za-z])INS\s*(?:No\.?\s*)?[\(\[:.\-]?\s*|(?<![A-Za-z0-9])E\s?-?)(\d{3})(?!\d)", re.I)
BARE_RE = re.compile(r"(?<![0-9])(\d{3})(?![0-9])")
CLASS_RE = re.compile(r"(?:sweetn?e(?:r|ners?|rs|ning\s+agents?)|humectants?|polyols?|bulking\s+agents?|sugar\s+substitutes?|stabili[sz]ers?)"
                      r"\s*(?:\(i+v?\)|\(v\))?\s*[:\-]?\s*$", re.I)
INS_INSIDE_RE = re.compile(r"(?<![A-Za-z])INS\b|(?<![A-Za-z0-9])E\s?-?\d{3}", re.I)
DIET_NAME_RE = re.compile(r"\b(?:diet|sugar[\s-]*free|sugarfree|zero(?:\s+sugar)?|no\s+(?:added\s+)?sugar|lite|light|unsweetened|keto)\b", re.I)
WARN_TEXT_RE = re.compile(r"not\s+recommended\s+for\s+children|phenylketonur|contains?\s+(?:added\s+)?(?:artificial|non[\s-]?caloric)\s+sweetn?e|"
                          r"calorie\s+conscious|this\s+contains\s+(?:aspartame|acesulfame|sucralose|saccharin)", re.I)
WARN_TAG_RE = re.compile(r"children|sweetener|phenylketon", re.I)
NUM_NAME = {**INTENSE, **POLYOL}


def brackets(txt):
    """Outermost bracket groups: (text before the bracket, text inside)."""
    out, depth, start = [], 0, None
    for i, ch in enumerate(txt):
        if ch in "([{":
            if depth == 0:
                start = i
            depth += 1
        elif ch in ")]}" and depth:
            depth -= 1
            if depth == 0 and start is not None:
                out.append((txt[max(0, start - 40):start], txt[start + 1:i]))
                start = None
    if depth and start is not None:                      # unclosed bracket (OCR): take the rest
        out.append((txt[max(0, start - 40):start], txt[start + 1:]))
    return out


def negated(txt, start, end):
    return bool(NEG_RE.search(txt[max(0, start - 30):start])) or bool(FREE_AFTER_RE.match(txt[end:end + 8]))


def find(txt):
    """-> set of sweetener names in the list (text reading)."""
    found = set()
    for m in PREFIXED_RE.finditer(txt):
        if m.group(1) in NUM_NAME:
            found.add(NUM_NAME[m.group(1)])
    for before, inside in brackets(txt):
        if CLASS_RE.search(before) or INS_INSIDE_RE.search(inside):
            for m in BARE_RE.finditer(inside):
                if m.group(1) in NUM_NAME:
                    found.add(NUM_NAME[m.group(1)])
    for rx, name, _ in WORDS:
        for m in rx.finditer(txt):
            if not negated(txt, m.start(), m.end()):
                found.add(name)
                break
    for m in UNNAMED_RE.finditer(txt):
        if not negated(txt, m.start(), m.end()):
            found.add("unnamed artificial sweetener")
            break
    return found


KIND = {**{v: "intense" for v in INTENSE.values()}, **{v: "polyol" for v in POLYOL.values()},
        **{name: kind for _, name, kind in WORDS}, "unnamed artificial sweetener": "intense"}


def tag_find(additives_tags):
    out = set()
    for t in (additives_tags or "").split(","):
        m = re.fullmatch(r"en:e(\d{3})[a-z]*", t.strip())
        if m and m.group(1) in NUM_NAME:
            out.add(NUM_NAME[m.group(1)])
    return out


def selftest():
    yes = {"Carbonated water, Sweetener (955), Acidity regulator (330)": {"sucralose"},
           "Sugar, Artificial Sweeteners (INS 955, INS 950), Preservative (INS 218)": {"sucralose", "acesulfame K", "unnamed artificial sweetener"},
           "Malt extract, Sweeteners (INS 951, 955)": {"aspartame", "sucralose"},
           "Atta, Refined Palm Oil, sweeteners [965(i) & (ii) and 955], wheat bran": {"maltitol", "sucralose"},
           "Maida, Sugar, Humectants (420 (ii), 422, 1520), Palm oil": {"sorbitol"},
           "Chicken fat, Humectant 420(ii), Iodised salt": set(),       # no bracket: Open Food Facts would read it, this matcher does not
           "Water, E950, E951, flavourings": {"acesulfame K", "aspartame"},
           "Water, sweeteners (acesulfame K, sucralose), colour": {"acesulfame K", "sucralose"},
           "Maltodextrin sweetner (420), corn starch": {"sorbitol"},
           "Milk solids, Steviol glycosides (INS 960), stevia leaf extract": {"steviol glycosides"},
           "CONTAINS NO FRUIT. CONTAINS ARTIFICIAL SWEETENERS AND FOR CALORIE CONSCIOUS": {"unnamed artificial sweetener"},
           "Vitamins, Artificial Sweetner": {"unnamed artificial sweetener"},
           "Dates, almonds. No artificial sweetener. Isomaltulose, sorbitan monostearate": set(),
           "Per serve of cooked dish (420 g) 333 kcal": set(),
           "Sugar free: contains sweetener (960) and stabilizer (466)": {"steviol glycosides"},
           "Water, sugar, sweetener free, flavour": set(),
           "Cocoa butter, polysaccharides, saccharides, acidity regulator (331)": set(),
           "Gum base, Sorbitol, Xylitol, Aspartame, Acesulfame-K. Contains phenylalanine": {"sorbitol", "xylitol", "aspartame", "acesulfame K"},
           "Emulsifier (INS 322), Stabiliser (INS 412), Colour (INS 150d)": set()}
    for s, want in yes.items():
        got = find(s)
        assert got == want, (s, got)
    assert tag_find("en:e322,en:e955,en:e950a") == {"sucralose", "acesulfame K"}
    assert tag_find("en:e330,en:e4201") == set()
    assert DIET_NAME_RE.search("Diet Cola 300 ml") and DIET_NAME_RE.search("Sugar-Free Digestive") and not DIET_NAME_RE.search("Delight biscuits")
    print("sweeteners selftest OK")


def share(k, n):
    return {"k": k, "n": n, "pct": round(100 * k / n, 1) if n else None}


def shown(country, n):
    return n >= (MIN_INDIA_SHARE if country == "India" else MIN_N)


def groups(cats):
    cset = set((cats or "").split(","))
    return [g for g, tags in CATS.items() if cset & tags]


def read_row(r):
    """-> record or None (no English list / excluded bucket)."""
    b = bucket(r.get("categories_tags", ""))
    if b and b.startswith("excluded"):
        return None
    txt = (r.get("ingredients_text") or "").strip()
    en = english_list(txt)
    tags = tag_find(r.get("additives_tags"))
    if not en and not txt and not tags:
        return None
    rec = {"en": en, "groups": groups(r.get("categories_tags")), "tag": tags, "has_list": bool(txt)}
    if en:
        f = find(txt)
        rec["text"] = f
        rec["intense"] = {x for x in f if KIND[x] == "intense"}
        rec["polyol"] = {x for x in f if KIND[x] == "polyol"}
        rec["sugar"] = sugar_analyse(txt)["n_sugar_names"] > 0
    return rec


def summarise(recs, country):
    en = [p for p in recs if p["en"]]
    n = len(en)
    k_int = sum(bool(p["intense"]) for p in en)
    k_pol = sum(bool(p["polyol"]) for p in en)
    k_any = sum(bool(p["intense"] or p["polyol"]) for p in en)
    k_both = sum(bool(p["intense"]) and p["sugar"] for p in en)
    k_sugar = sum(p["sugar"] for p in en)
    which = Counter(x for p in en for x in p["intense"])
    which_pol = Counter(x for p in en for x in p["polyol"])
    listed = [p for p in recs if p["has_list"] or p["tag"]]
    nt = len(listed)
    t_int = sum(bool({x for x in p["tag"] if KIND[x] == "intense"}) for p in listed)
    t_pol = sum(bool({x for x in p["tag"] if KIND[x] == "polyol"}) for p in listed)
    which_tag = Counter(x for p in listed for x in p["tag"] if KIND[x] == "intense")
    return {"text": {"n": n, "shown": shown(country, n),
                     "intense": share(k_int, n), "polyol": share(k_pol, n), "any": share(k_any, n),
                     "added_sugar": share(k_sugar, n), "both_sugar_and_intense": share(k_both, n),
                     "both_among_intense": share(k_both, k_int),
                     "which_intense": dict(which.most_common()), "which_polyol": dict(which_pol.most_common())},
            "tag": {"n": nt, "shown": shown(country, nt), "intense": share(t_int, nt), "polyol": share(t_pol, nt),
                    "which_intense": dict(which_tag.most_common())}}


def main():
    selftest()
    acc = defaultdict(lambda: defaultdict(list))   # acc[group][country] -> records
    india_named, india_warn = [], []
    seen = set()
    text_vs_tag = Counter()
    with (HERE / "data" / "off_india.csv").open(encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f, delimiter="\t"):
            code = r.get("code")
            if not code or code in seen or "en:india" not in (r.get("countries_tags") or "").split(","):
                continue
            seen.add(code)
            rec = read_row(r)
            if not rec:
                continue
            for g in ["all_foods"] + rec["groups"]:
                acc[g]["India"].append(rec)
            if rec["en"]:
                name = " ".join((r.get(k) or "") for k in ("product_name", "abbreviated_product_name", "generic_name"))
                if DIET_NAME_RE.search(name):
                    india_named.append(rec)
                if rec["intense"]:
                    text_vs_tag["intense_by_text"] += 1
                    text_vs_tag["also_tagged_by_off"] += bool({x for x in rec["tag"] if KIND[x] == "intense"})
                    txt = r.get("ingredients_text") or ""
                    in_tags = bool(WARN_TAG_RE.search(r.get("labels_tags") or ""))
                    in_text = bool(WARN_TEXT_RE.search(txt))
                    india_warn.append({"tag": in_tags, "text": in_text, "unnamed_only": rec["intense"] == {"unnamed artificial sweetener"}})
    multi_india = defaultdict(list)
    with (HERE / "data" / "off_multi.tsv").open(encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f, delimiter="\t"):
            cs = [C[t] for t in (r.get("countries_tags") or "").split(",") if t in C]
            if not cs:
                continue
            rec = read_row(r)
            if not rec:
                continue
            for c in cs:
                for g in ["all_foods"] + rec["groups"]:
                    (multi_india if c == "India" else acc)[g if c == "India" else g][c if c != "India" else g] if False else None
                    if c == "India":
                        multi_india[g].append(rec)
                    else:
                        acc[g][c].append(rec)

    out = {"source": "Open Food Facts (https://world.openfoodfacts.org/), ODbL. off_india.csv read 1 Oct 2026 (India); "
                     "off_multi.tsv read 6 Oct 2026 (UK, US, France).",
           "note": "text = this script's matcher on English ingredient lists (n = English lists in the group, baby food and "
                   "supplements out). tag = Open Food Facts' additives_tags (any language; n = products with a list or a tag). "
                   "intense = the WHO's non-sugar sweeteners (acesulfame K, aspartame, sucralose, saccharin, steviol glycosides, "
                   "neotame, cyclamate, thaumatin and the rest); polyol = sorbitol, maltitol, xylitol, erythritol, isomalt, "
                   "mannitol, lactitol. Volunteers fill Open Food Facts, so no country's packs are a random sample. "
                   "Shares: k of n, pct = 100*k/n.",
           "min_n": {"other_countries": MIN_N, "india_share": MIN_INDIA_SHARE},
           "categories": {}, "india_multi_snapshot": {}, "india_named_diet_zero_sugar_free": {}, "india_warning_check": {},
           "india_text_vs_tag": {}}
    for g in ["all_foods"] + list(CATS):
        out["categories"][g] = {c: summarise(v, c) for c, v in sorted(acc[g].items(), key=lambda kv: -len(kv[1])) if v}
        if multi_india.get(g):
            s = summarise(multi_india[g], "India")
            out["india_multi_snapshot"][g] = {"n": s["text"]["n"], "intense": s["text"]["intense"]}
    nn = len(india_named)
    out["india_named_diet_zero_sugar_free"] = {
        "n": nn, "shown": shown("India", nn),
        "intense": share(sum(bool(p["intense"]) for p in india_named), nn),
        "polyol_only": share(sum(bool(p["polyol"]) and not p["intense"] for p in india_named), nn),
        "no_sweetener_found": share(sum(not (p["intense"] or p["polyol"]) for p in india_named), nn),
        "names_an_added_sugar": share(sum(p["sugar"] for p in india_named), nn),
        "which_intense": dict(Counter(x for p in india_named for x in p["intense"]).most_common()),
        "name_words": "diet, sugar free, zero, no sugar, no added sugar, lite, light, unsweetened, keto (product name, any brand words included)"}
    nw = len(india_warn)
    out["india_warning_check"] = {
        "n_lists_with_intense": nw,
        "warning_in_labels_tags": share(sum(p["tag"] for p in india_warn), nw),
        "warning_sentence_in_ingredient_text": share(sum(p["text"] for p in india_warn), nw),
        "either": share(sum(p["tag"] or p["text"] for p in india_warn), nw),
        "note": "Open Food Facts has no field for FSSAI's sweetener statements. labels_tags carries one only when a volunteer typed it; "
                "the ingredient text carries one only when the volunteer pasted the whole back of the pack. So this is a floor on "
                "how many packs print the statement, not a measure of it."}
    out["india_text_vs_tag"] = dict(text_vs_tag, note="Indian English lists where the matcher finds an intense sweetener, and how "
                                                      "many of those Open Food Facts also tagged (additives_tags).")
    OUT.mkdir(exist_ok=True)
    (OUT / "sweeteners.json").write_text(json.dumps(out, indent=1), encoding="utf-8")

    table = []
    for g, byc in out["categories"].items():
        for c, v in byc.items():
            for key in ("intense", "polyol", "any", "added_sugar", "both_sugar_and_intense"):
                s = v["text"][key]
                table.append({"measure": "text_" + key, "group": g, "item": "", "country": c, "count": s["k"], "n": s["n"],
                              "value": s["pct"], "unit": "%", "shown": v["text"]["shown"]})
            s = v["text"]["both_among_intense"]
            table.append({"measure": "text_both_among_intense", "group": g, "item": "", "country": c, "count": s["k"], "n": s["n"],
                          "value": s["pct"], "unit": "%", "shown": s["n"] >= (MIN_INDIA_SHARE if c == "India" else MIN_N)})
            for name, k in v["text"]["which_intense"].items():
                table.append({"measure": "text_which_intense", "group": g, "item": name, "country": c, "count": k, "n": v["text"]["n"],
                              "value": round(100 * k / v["text"]["n"], 1), "unit": "%", "shown": v["text"]["shown"]})
            for key in ("intense", "polyol"):
                s = v["tag"][key]
                table.append({"measure": "tag_" + key, "group": g, "item": "", "country": c, "count": s["k"], "n": s["n"],
                              "value": s["pct"], "unit": "%", "shown": v["tag"]["shown"]})
            for name, k in v["tag"]["which_intense"].items():
                table.append({"measure": "tag_which_intense", "group": g, "item": name, "country": c, "count": k, "n": v["tag"]["n"],
                              "value": round(100 * k / v["tag"]["n"], 1), "unit": "%", "shown": v["tag"]["shown"]})
    d = out["india_named_diet_zero_sugar_free"]
    for key in ("intense", "polyol_only", "no_sweetener_found", "names_an_added_sugar"):
        table.append({"measure": "named_diet_" + key, "group": "diet_zero_sugar_free_names", "item": "", "country": "India",
                      "count": d[key]["k"], "n": d["n"], "value": d[key]["pct"], "unit": "%", "shown": d["shown"]})
    w = out["india_warning_check"]
    for key in ("warning_in_labels_tags", "warning_sentence_in_ingredient_text", "either"):
        table.append({"measure": "warning_" + key, "group": "lists_with_intense", "item": "", "country": "India",
                      "count": w[key]["k"], "n": w[key]["n"], "value": w[key]["pct"], "unit": "%", "shown": True})
    with (OUT / "sweeteners_table.csv").open("w", encoding="utf-8", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=["measure", "group", "item", "country", "count", "n", "value", "unit", "shown"])
        wr.writeheader()
        wr.writerows(table)

    for g, byc in out["categories"].items():
        cells = [f"{c} intense {v['text']['intense']['k']}/{v['text']['intense']['n']} ({v['text']['intense']['pct']}%)"
                 f"{'' if v['text']['shown'] else '*'} polyol {v['text']['polyol']['k']} both {v['text']['both_sugar_and_intense']['k']}"
                 f" | tag {v['tag']['intense']['k']}/{v['tag']['intense']['n']}" for c, v in byc.items()]
        print(f"{g:18} " + " || ".join(cells))
        iv = byc.get("India")
        if iv:
            print(f"{'':18} India which: {iv['text']['which_intense']} polyols {iv['text']['which_polyol']}"
                  + (f"; off_multi India {out['india_multi_snapshot'][g]['intense']}" if g in out["india_multi_snapshot"] else ""))
    print("India named diet/zero/sugar free:", json.dumps(out["india_named_diet_zero_sugar_free"]))
    print("India warning check:", json.dumps(out["india_warning_check"]))
    print("India text vs tag:", dict(text_vs_tag))


if __name__ == "__main__":
    main()
