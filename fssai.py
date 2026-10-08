"""What if FSSAI's proposed front-of-pack warnings applied today?
Thresholds: ICMR-NIN Dietary Guidelines for Indians 2024, Table 15.1, as cited in FSSAI's 28 Aug 2026
affidavit to the Supreme Court (reported by LiveLaw and Business Standard, Sep 2026).
Solids per 100 g: added sugar 3 g, added fat 4.2 g, salt 625 mg. Liquids per 100 ml: 2 g, 1.5 g, 175 mg.
Phase I: warning when 2 or more nutrients are high. Phase II: when any one is high.
Added sugar: the label's declared added-sugar figure when present; otherwise total sugars, but only when a
sugar name is in the ingredient list (an upper estimate). Added fat: total fat when a fat or oil is in the
list (upper estimate). Salt: salt per 100 g when salt is in the list.
Output: out/fssai.json. Category-level only; no brands.

Run with `python -I fssai.py` (the repo's warnings.py shadows the stdlib module, so it is loaded by path).

  python -I fssai.py                     the published 1 Oct 2026 numbers (665 foods), unchanged
  python -I fssai.py --court             limits + trigger from order_thresholds.json (edit it on order day),
                                         supplements dropped by name; writes out/fssai.json for the page
  python -I fssai.py --solid sugar=3,fat=4.2,salt_mg=625 --liquid sugar=2,fat=1.5,salt_mg=175 --any 2
  python -I fssai.py --weighted sugar=2,fat=1,salt=1 --cutoff 2 --drop-supplements
Limits are per 100 g (solid) / 100 ml (liquid); salt in mg, or give sodium_mg and it is converted (x 2.5).
Trigger: --any N = warned when N or more of the 3 are high; --weighted = each high nutrient adds its weight,
warned when the total reaches --cutoff. Runs other than the default and --court print only, unless --out."""
import argparse
import csv
import importlib.util
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from sugar import KINDS, find_sugars  # noqa: E402
from analyse import ADDED_SUGAR_RELEVANT_EXCLUDE, bucket, num  # noqa: E402

_spec = importlib.util.spec_from_file_location("ili_warnings", HERE / "warnings.py")
_w = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_w)
SALT_RE, FAT_RE, is_liquid = _w.SALT_RE, _w.FAT_RE, _w.is_liquid

csv.field_size_limit(2**31 - 1)
SOLID = {"sugar": 3, "fat": 4.2, "salt_mg": 625}
LIQUID = {"sugar": 2, "fat": 1.5, "salt_mg": 175}
NUTS = ("sugar", "fat", "salt")
DEFAULT_TRIGGER = {"type": "any", "n": 1}
DEFAULT_RULES = "ICMR-NIN DGI 2024 Table 15.1 thresholds as cited by FSSAI (affidavit 28 Aug 2026); Phase I = 2+ high, Phase II = any 1 high"
COURT_FILE = HERE / "order_thresholds.json"

# Supplements and medical products that slipped past the category tags (found by a reviewer, 8 Oct 2026):
# protein powders, nutrition drinks, ORS, energy gels. FSSAI's labelling rule is for packaged food; these sit
# under its health-supplement / special-dietary-use rules or are medicines. Matched on the product name.
SUPPLEMENT_RE = re.compile(r"\b(isolate|protein powder|whey protein|protein shake|rehydration salts?|\bors\b|energy gel|"
                           r"diabetes care|moringa powder|spirulina|wheatgrass powder|multivitamins?|capsules?|"
                           r"mass gainer|creatine|bcaa)\b", re.I)
# names that carry only a brand, no generic word: a children's nutrition-supplement powder
SUPPLEMENT_CODES = {"8904145912025"}


def is_supplement(r):
    name = " ".join(r.get(k) or "" for k in ("product_name", "abbreviated_product_name", "generic_name"))
    return r.get("code") in SUPPLEMENT_CODES or bool(SUPPLEMENT_RE.search(name))


def limits(s, base):
    """'sugar=3,fat=4.2,salt_mg=625' (or sodium_mg=250) -> dict, unspecified keys from base."""
    out = dict(base)
    for part in filter(None, (p.strip() for p in s.split(","))):
        k, v = (x.strip() for x in part.split("=", 1))
        v = int(v) if re.fullmatch(r"-?\d+", v) else float(v)
        if k == "sodium_mg":
            k, v = "salt_mg", round(v * 2.5, 3)
        if k not in ("sugar", "fat", "salt_mg"):
            raise SystemExit(f"unknown limit {k!r}: use sugar, fat, salt_mg or sodium_mg")
        out[k] = v
    return out


def from_json(d, base):
    d = {k: v for k, v in d.items() if not k.startswith("_")}
    return limits(",".join(f"{k}={v}" for k, v in d.items()), base)


def warned(high, trig):
    if trig["type"] == "any":
        return len(high) >= trig["n"]
    return sum(trig["weights"].get(k, 0) for k in high) >= trig["cutoff"]


def describe(trig):
    if trig["type"] == "any":
        return f"warning when any {trig['n']} of added sugar, added fat, salt is high"
    w = ", ".join(f"{k} {v:g}" for k, v in trig["weights"].items())
    return f"warning when the weights of the high nutrients ({w}) add up to {trig['cutoff']:g} or more"


def parse_args(argv):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--court", action="store_true", help=f"read limits + trigger from {COURT_FILE.name}")
    ap.add_argument("--config", type=Path, default=COURT_FILE, help="JSON file for --court")
    ap.add_argument("--solid", help="per 100 g, e.g. sugar=3,fat=4.2,salt_mg=625")
    ap.add_argument("--liquid", help="per 100 ml, e.g. sugar=2,fat=1.5,salt_mg=175")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--any", type=int, choices=(1, 2, 3), help="warned when N or more of the 3 are high")
    g.add_argument("--weighted", help="e.g. sugar=2,fat=1,salt=1 (use with --cutoff)")
    ap.add_argument("--cutoff", type=float, help="score needed under --weighted")
    ap.add_argument("--drop-supplements", action="store_true", help="leave out supplements found by name")
    ap.add_argument("--out", type=Path, help="where to write the JSON")
    a = ap.parse_args(argv)
    if a.weighted and a.cutoff is None:
        ap.error("--weighted needs --cutoff")
    return a


def config(a):
    """-> (solid, liquid, trigger, drop_supplements, rules label, output path or None, legacy?)"""
    solid, liquid, trig, drop, label = dict(SOLID), dict(LIQUID), dict(DEFAULT_TRIGGER), False, None
    if a.court:
        c = json.loads(a.config.read_text(encoding="utf-8"))
        solid = from_json(c["solid_per_100g"], solid)
        liquid = from_json(c["liquid_per_100ml"], liquid)
        trig = {k: v for k, v in c["trigger"].items() if not k.startswith("_")}
        drop = bool(c.get("exclude_supplements", True))
        label = c.get("label")
    if a.solid:
        solid = limits(a.solid, solid)
    if a.liquid:
        liquid = limits(a.liquid, liquid)
    if a.any:
        trig = {"type": "any", "n": a.any}
    if a.weighted:
        w = {k.strip(): float(v) for k, v in (p.split("=", 1) for p in a.weighted.split(",") if p.strip())}
        bad = set(w) - set(NUTS)
        if bad:
            raise SystemExit(f"unknown weight {sorted(bad)}: use sugar, fat, salt")
        trig = {"type": "weighted", "weights": w, "cutoff": a.cutoff}
    if trig["type"] not in ("any", "weighted"):
        raise SystemExit("trigger type must be 'any' or 'weighted'")
    drop = drop or a.drop_supplements
    legacy = (solid == SOLID and liquid == LIQUID and trig == DEFAULT_TRIGGER and not drop and not a.court)
    out = a.out or ((HERE / "out" / "fssai.json") if (legacy or a.court) else None)
    return solid, liquid, trig, drop, label, out, legacy


def main(argv=None):
    a = parse_args(sys.argv[1:] if argv is None else argv)
    SOL, LIQ, trig, drop, label, out_path, legacy = config(a)
    rows = csv.DictReader((HERE / "data" / "off_india.csv").open(encoding="utf-8"), delimiter="\t")
    tested, by_cat = [], defaultdict(list)
    declared = 0
    dropped = Counter()
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
        if drop and is_supplement(r):
            dropped["non_staple" if b not in ADDED_SUGAR_RELEVANT_EXCLUDE else "staple"] += 1
            continue
        add_sug = num(r.get("added-sugars_100g"))
        has_sugar = any(KINDS[i] == "sugar" for _, _, i in find_sugars(ing))
        if add_sug is not None and 0 <= add_sug <= sug + 0.5:
            declared += 1
            sugar_val, src = add_sug, "declared"
        else:
            sugar_val, src = (sug if has_sugar else 0.0), "estimate"
        th = LIQ if is_liquid(r.get("categories_tags", "")) else SOL
        high = []
        if sugar_val >= th["sugar"]:
            high.append("sugar")
        if FAT_RE.search(ing) and fat >= th["fat"]:
            high.append("fat")
        if SALT_RE.search(ing) and salt * 1000 >= th["salt_mg"]:
            high.append("salt")
        p = {"cat": b, "high": high, "src": src, "warned": warned(high, trig)}
        tested.append(p)
        if b and not b.startswith("excluded"):
            by_cat[b].append(p)

    def summ(ps):
        n = len(ps)
        if not n:
            return {"tested": 0}
        each = Counter(x for p in ps for x in p["high"])
        s = {"tested": n,
             "pct_phase2_any": round(100 * sum(1 for p in ps if p["high"]) / n, 1),
             "pct_phase1_2plus": round(100 * sum(1 for p in ps if len(p["high"]) >= 2) / n, 1),
             "pct_all3": round(100 * sum(1 for p in ps if len(p["high"]) == 3) / n, 1),
             "pct_by_nutrient": {k: round(100 * each[k] / n, 1) for k in NUTS}}
        if not legacy:
            k = sum(1 for p in ps if p["warned"])
            s.update({"warned": k, "pct_warned": round(100 * k / n, 1),
                      "n_any1": sum(1 for p in ps if p["high"]), "n_2plus": sum(1 for p in ps if len(p["high"]) >= 2)})
        return s

    # staples (oils, ghee, flours, spices, tea) left out of the headline, like the sugar study; FSSAI exempts
    # single-ingredient and inherently fat-rich foods anyway
    non_staple = [p for p in tested if p["cat"] not in ADDED_SUGAR_RELEVANT_EXCLUDE]
    res = {"rules": DEFAULT_RULES if legacy else (label or f"{describe(trig)}; limits per 100 g / 100 ml below"),
           "thresholds": {"solid_per_100g": SOL, "liquid_per_100ml": LIQ}}
    if not legacy:
        res["trigger"] = trig
        res["supplements_excluded_by_name"] = dict(dropped) if drop else None
    res.update({"overall": summ(tested),
                "non_staple": summ(non_staple),
                "declared_added_sugar_only": summ([p for p in non_staple if p["src"] == "declared"]),
                "products_with_declared_added_sugar": declared,
                "categories": {k: summ(v) for k, v in sorted(by_cat.items(), key=lambda kv: -len(kv[1])) if len(v) >= 30}})
    if out_path:
        out_path.write_text(json.dumps(res, indent=1), encoding="utf-8")
    keys = ("overall", "non_staple", "declared_added_sugar_only", "products_with_declared_added_sugar")
    print(json.dumps({k: res[k] for k in (("trigger", "supplements_excluded_by_name") if not legacy else ()) + keys}, indent=1))
    for k, v in res["categories"].items():
        extra = "" if legacy else f" warned={v['pct_warned']}"
        print(f"{k[:34]:34} n={v['tested']:4} any={v['pct_phase2_any']} 2+={v['pct_phase1_2plus']}{extra} {v['pct_by_nutrient']}")
    print("wrote", out_path if out_path else "nothing (what-if run; pass --out to save)")
    return res


if __name__ == "__main__":
    main()
