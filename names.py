"""Study 6 (draft, not published): do healthy-sounding names get FSSAI's proposed warning less often?
Base = the FSSAI study's foods (fssai.score), current plan as in order_thresholds.json (any 1 of added sugar,
added fat, salt high; supplements left out by name), staples left out like the headline.
A "health word" is matched on the product name with the brand's own words removed first, so a brand called
"Natural ..." or "Fit ..." never counts.
Product-line names inside a company brand DO count ("Nutri Choice" under Britannia, "B Natural" under ITC): they are
printed on the front as the product's name, which is what a shopper reads. Checked by hand on 9 Oct 2026. Words are grouped: grain (multigrain, oats, millet, atta...),
less (diet, lite, sugar free, low fat...), good (healthy, protein, digestive, baked, organic, natural...).
Output: out/names.json (counts k of n, category level, no brands). out/names_audit.tsv lists every matched
name for a hand check; it carries brand names, so it is gitignored and never published.

Run with `python -I names.py` (the repo's warnings.py shadows the stdlib module)."""
import csv
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import fssai  # noqa: E402
from analyse import ADDED_SUGAR_RELEVANT_EXCLUDE  # noqa: E402

csv.field_size_limit(2**31 - 1)
OUT = HERE / "out"

GROUPS = {
    "grain": r"multi[\s-]*grains?|whole[\s-]*(?:wheat|grains?)|wholewheat|atta|oats?|oatmeal|millets?|multi[\s-]*millets?|ragi|nachni|"
             r"jowar|bajra|quinoa|brown rice|foxtail",
    "less": r"diet|lite|light|low[\s-]+(?:fat|sugar|sodium|salt|cal(?:orie)?s?)|less sugar|reduced (?:sugar|fat|salt)|"
            r"sugar[\s-]*free|no added sugar|no sugar|zero sugar|zero|unsweetened",
    "good": r"healthy|health|nutri\w*|high[\s-]+fib(?:re|er)|fib(?:re|er)|protein|digestive|baked|natural|organic|fit|"
            r"wellness|immunity|superfood|keto|gluten[\s-]+free|wholesome",
}
GROUP_RE = {g: re.compile(r"(?<![\w-])(" + p + r")(?![\w-])", re.I) for g, p in GROUPS.items()}
NAME_FIELDS = ("product_name", "abbreviated_product_name", "generic_name")


def clean_name(r):
    name = next((r.get(k) for k in NAME_FIELDS if (r.get(k) or "").strip()), "") or ""
    for b in (r.get("brands") or "").split(","):
        b = b.strip()
        if len(b) >= 2:
            name = re.sub(re.escape(b), " ", name, flags=re.I)
    for t in (r.get("brands_tags") or "").split(","):
        t = t.strip().split(":")[-1]
        if len(t) >= 3:
            name = re.sub(r"\b" + re.escape(t).replace(r"\-", r"[\s-]?") + r"\b", " ", name, flags=re.I)
    return re.sub(r"\s+", " ", name).strip()


def health_words(name):
    return {g: sorted({m.lower() for m in rx.findall(name)}) for g, rx in GROUP_RE.items() if rx.search(name)}


def selftest():
    yes = {"Multigrain Biscuits": "grain", "Multi -Millet Mix": "grain", "Multi - Grain Bread": "grain", "Whole Wheat Bread": "grain", "Atta Noodles": "grain", "Ragi Cookies": "grain",
           "Diet Chivda": "less", "Sugar Free Cookies": "less", "Low-fat Dahi": "less", "No Added Sugar Juice": "less",
           "Digestive Biscuits": "good", "Baked Chips": "good", "High Fibre Muesli": "good", "Protein Bar": "good",
           "Nutri Choice Crackers": "good", "Organic Jaggery Cookies": "good"}
    for s, g in yes.items():
        assert g in health_words(s), (s, health_words(s))
    no = ["Daylight Cream Biscuit", "Goat Milk", "Attack Masala", "Lightning Chips", "Fittings", "Bakedd", "Healthful-ish"]
    for s in no[:5]:
        assert not health_words(s), (s, health_words(s))
    r = {"product_name": "Natural Fit Mango Ice Cream", "brands": "Natural Fit", "brands_tags": "natural-fit"}
    assert clean_name(r) == "Mango Ice Cream" and not health_words(clean_name(r)), clean_name(r)
    r = {"product_name": "Nutri Choice Digestive", "brands": "Acme", "brands_tags": "acme"}
    assert health_words(clean_name(r)) == {"good": ["digestive", "nutri"]}
    assert len(items("Rolled oats.")) == 1 and len(items("Milk")) == 1
    assert len(items("Whole wheat flour (atta) 60%, sugar, edible vegetable oil (palm, rice bran), salt")) == 4
    print("names selftest OK")


def items(ing):
    """Top-level ingredients: split on commas and semicolons outside brackets."""
    out, depth, cur = [], 0, ""
    for ch in ing:
        depth += ch in "([{"
        depth -= ch in ")]}"
        if ch in ",;" and depth <= 0:
            out.append(cur)
            cur = ""
        else:
            cur += ch
    out.append(cur)
    return [x for x in (re.sub(r"[\s.]+$", "", y.strip()) for y in out) if x]


def share(ps):
    n = len(ps)
    k = sum(1 for p in ps if p["warned"])
    return {"k": k, "n": n, "pct": round(100 * k / n, 1) if n else None}


def main():
    selftest()
    SOL, LIQ, trig, drop, label, _, _ = fssai.config(fssai.parse_args(["--court"]))
    rows = csv.DictReader((HERE / "data" / "off_india.csv").open(encoding="utf-8"), delimiter="\t")
    foods, audit, single = [], [], 0
    for r in rows:
        p = fssai.score(r, SOL, LIQ, trig, drop)
        if p is None or p == "dropped" or p["cat"] in ADDED_SUGAR_RELEVANT_EXCLUDE:
            continue
        # single-ingredient foods ("Rolled oats", "Organic cow milk"): the health word is just the food's name, and
        # FSSAI's plan exempts them anyway (found on the first hand check, 9 Oct 2026)
        if len(items(r.get("ingredients_text") or "")) < 2:
            single += 1
            continue
        name = clean_name(r)
        p["words"] = health_words(name)
        foods.append(p)
        if p["words"]:
            audit.append((p["cat"], ";".join(f"{g}:{','.join(w)}" for g, w in p["words"].items()), p["warned"],
                          "+".join(p["high"]), r.get("product_name", ""), name))
    hw = [p for p in foods if p["words"]]
    plain = [p for p in foods if not p["words"]]
    res = {"rules": label or fssai.describe(trig), "base": "non-staple foods in the FSSAI study, supplements out by name",
           "foods": len(foods), "health_word": share(hw), "no_health_word": share(plain),
           "by_group": {g: share([p for p in hw if g in p["words"]]) for g in GROUPS},
           "by_word": {}, "by_nutrient_health_word": dict(Counter(x for p in hw for x in p["high"])),
           "categories": {}, "single_ingredient_left_out": single,
           "health_word_without_protein": share([p for p in hw if not any("protein" in ws for ws in p["words"].values())])}
    words = Counter(w for p in hw for ws in p["words"].values() for w in ws)
    for w, c in words.most_common():
        if c >= 5:
            res["by_word"][w] = share([p for p in hw if any(w in ws for ws in p["words"].values())])
    by_cat = defaultdict(list)
    for p in foods:
        if p["cat"] and not p["cat"].startswith("excluded"):
            by_cat[p["cat"]].append(p)
    for c, ps in sorted(by_cat.items(), key=lambda kv: -len(kv[1])):
        h = [p for p in ps if p["words"]]
        if len(h) >= 10:
            res["categories"][c] = {"health_word": share(h), "no_health_word": share([p for p in ps if not p["words"]])}
    # category-adjusted: if each health-word food were warned at the rate of the no-health-word foods in its own
    # category, how many would be warned? (foods with no category, or a category with no plain foods, left out)
    rate = {c: share([p for p in ps if not p["words"]]) for c, ps in by_cat.items()}
    adj = [p for p in hw if p["cat"] in rate and rate[p["cat"]]["n"]]
    res["category_adjusted"] = {"n": len(adj), "warned": sum(p["warned"] for p in adj),
                                "expected_at_own_category_rate": round(sum(rate[p["cat"]]["k"] / rate[p["cat"]]["n"] for p in adj), 1)}

    def adjusted(ps):
        a = [p for p in ps if p["cat"] in rate and rate[p["cat"]]["n"]]
        return {"n": len(a), "warned": sum(p["warned"] for p in a),
                "expected_at_own_category_rate": round(sum(rate[p["cat"]]["k"] / rate[p["cat"]]["n"] for p in a), 1)}
    res["health_word_without_protein_adjusted"] = adjusted([p for p in hw if not any("protein" in ws for ws in p["words"].values())])
    # grain words lead the page (no protein angle: worker 9 Oct): own share, category-adjusted, why they are warned
    grain = [p for p in hw if "grain" in p["words"]]
    gcat = defaultdict(list)
    for p in grain:
        gcat[p["cat"] or "no category"].append(p)
    res["grain"] = {"all": share(grain), "category_adjusted": adjusted(grain),
                    "high_among_warned": dict(Counter(x for p in grain if p["warned"] for x in p["high"])),
                    "categories": {c: {**share(ps), "salt_high": sum("salt" in p["high"] for p in ps)}
                                   for c, ps in sorted(gcat.items(), key=lambda kv: (-len(kv[1]), kv[0]))}}
    OUT.mkdir(exist_ok=True)
    (OUT / "names.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    with (OUT / "names_audit.tsv").open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter="\t")
        w.writerow(["category", "words", "warned", "high", "product_name", "name_without_brand"])
        w.writerows(sorted(audit, key=lambda a: tuple(str(x) for x in a)))
    print(json.dumps({k: res[k] for k in ("foods", "single_ingredient_left_out", "health_word", "no_health_word", "by_group",
                                          "health_word_without_protein", "category_adjusted")}))
    for w_, s in res["by_word"].items():
        print(f"  {w_:18} {s}")
    for c, s in res["categories"].items():
        print(f"  {c[:34]:34} {s}")
    return res


if __name__ == "__main__":
    main()
