"""Where maltodextrin sits on Indian ingredient lists (India Label Index study 15 candidate, 27 October 2026; UNPUBLISHED).

Why: FSSAI's own notice of June 2026 (its Instagram post DaE4buXIFmD) objected to a biscuit's 'No Added Sugar' claim
because the biscuit contains maltodextrin and glucose syrup solids, and press reports (punenow, 21 Sep 2026) say an FSSAI
consumer post tells shoppers to check lists for it. This counts how often Indian packaged foods name it, where in the
list, and in which categories. It says nothing about safety or amounts: maltodextrin is a permitted ingredient, and the
Label Checker does not count it as a sugar name (it is starch-derived; kind 'starch' in aliases.json).

Which products: every Open Food Facts India row (data/off_india.csv, one row per barcode, en:india in countries_tags)
with an ingredient list the English matchers can read (fats.english_list), in the non-staple base of every Index study:
analyse.bucket() is not baby food or a supplement (its excluded rows hold en:protein-powders and en:dietary-supplements),
and not spices, flours/grains/pulses, oils/ghee or tea/coffee. Products whose NAME says whey, protein powder, mass or
weight gainer, or isolate are left out too (no protein angle; counted in dropped_protein_name).

The matcher (MALTO_RE) takes every spelling seen on Indian lists on 27 Oct 2026: maltodextrin(e)(s), malto-dextrin,
malto - dextrin, malto dextrin(e), and the photo/typing slips maitodextrin, maltrodextrin, maltodextin, maltodextr and a
dotted i. 'Resistant maltodextrin' (a fibre ingredient) is counted apart and never in the headline. Dextrin alone
(INS 1400, a different starch) and polydextrose never count. A mention after 'no', 'without' or before 'free' does not
count (negated()).
Position: 'top3' = the word sits in one of the first 3 top-level items (sugar.top_items, the Label Checker's split), not
inside that item's bracket; 'in_bracket' = it sits inside any bracket (a seasoning, a flavour, a filling).
Category shares are printed for buckets with MIN_N or more lists.
Hand audit (maltodextrin_labels.csv, every hit read in context 27 Oct 2026, worker 07:00): verdict food, supplement
(nutrition, clinical, pregnancy, protein or sports-gel products the tags missed) or junk (a placeholder record);
supplement and junk records leave the base entirely, from the count AND the denominator. top3_hand = no overrides the
split where a list is printed without commas or garbled. The script fails if the CSV does not cover exactly the hit set,
so a data re-pull forces a re-audit. All 302 hit lines were real ingredient mentions (none negated, none in a 'may
contain' line). Caveat: lists WITHOUT maltodextrin were not read by hand, so a few untagged supplements stay in the
denominator (as in every Index study that uses the tag exclusions).
Category level only: no brand or product name is output. out/maltodextrin_audit.txt (not committed) holds every hit with
its context and barcode for the hand audit.
Output: out/maltodextrin.json. Run: python -I maltodextrin.py  (about 30 s)"""
import csv
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from analyse import ADDED_SUGAR_RELEVANT_EXCLUDE, bucket  # noqa: E402
from fats import english_list  # noqa: E402
from sugar import analyse as sugar_analyse, top_items  # noqa: E402

csv.field_size_limit(2**31 - 1)
SRC = HERE / "data" / "off_india.csv"
OUT = HERE / "out"
LABELS = HERE / "maltodextrin_labels.csv"
MIN_N = 100
STAPLES = ADDED_SUGAR_RELEVANT_EXCLUDE | {"Edible oils and ghee"}

MALTO_RE = re.compile(r"(?<![a-z])ma[il]tr?o\s*-?\s*dext?r?i?\u0307?n?e?s?(?![a-z])", re.I)
RESISTANT_RE = re.compile(r"resistant\s*$", re.I)
PROTEIN_NAME_RE = re.compile(r"\bwhey\b|protein\s+powder|\b(?:mass|weight)\s+gainer|\bisolate\b", re.I)


def negated(txt, s, e):
    before = txt[max(0, s - 16):s].lower()
    after = txt[e:e + 10].lower()
    return bool(re.search(r"\b(?:no|without|zero)\s*$", before) or re.match(r"^[\s-]*free\b", after))


def find(txt):
    """-> list of (start, end, kind) with kind 'malto' or 'resistant'; negated mentions dropped."""
    out = []
    for m in MALTO_RE.finditer(txt):
        if negated(txt, m.start(), m.end()):
            continue
        kind = "resistant" if RESISTANT_RE.search(txt[max(0, m.start() - 12):m.start()]) else "malto"
        out.append((m.start(), m.end(), kind))
    return out


def depth_at(txt, pos, frm=0):
    seg = txt[frm:pos]
    return seg.count("(") + seg.count("[") + seg.count("{") - seg.count(")") - seg.count("]") - seg.count("}")


def place(txt, hits):
    items = top_items(txt)
    top3 = items[:3]
    in_top3 = any(s <= h[0] < e and depth_at(txt, h[0], s) <= 0 for h in hits for s, e in top3)
    in_bracket = any(depth_at(txt, h[0]) > 0 for h in hits)
    top_level = any(depth_at(txt, h[0]) <= 0 for h in hits)
    return in_top3, in_bracket, top_level


def selftest():
    cases = [("Ingredients: Maltodextrin, Sugar, Salt", 1, True), ("Wheat flour, Sugar, Edible oil, Maltodextrin", 1, False),
             ("Potato, oil, seasoning (salt, malto-dextrin, spices)", 1, False), ("Malto Dextrine, cocoa", 1, True),
             ("no maltodextrin, oats", 0, False), ("Maltodextrin free formula: oats", 0, False),
             ("Dextrin (INS 1400), sugar", 0, False), ("Polydextrose, sugar", 0, False),
             ("Resistant maltodextrin, cocoa", 0, False), ("Maitodextrin, salt", 1, True), ("Maltodextin, salt", 1, True)]
    bad = 0
    for t, n, top in cases:
        h = [x for x in find(t) if x[2] == "malto"]
        got_top = place(t, h)[0] if h else False
        ok = len(h) == n and got_top == top
        bad += not ok
        print("OK " if ok else "BAD", t, "->", len(h), got_top)
    assert not bad, "maltodextrin.py self-test failed"


def share(k, n):
    return {"k": k, "n": n, "pct": round(100 * k / n, 1) if n else None}


def labels():
    with LABELS.open(encoding="utf-8", newline="") as f:
        rows = {r["code"]: r for r in csv.DictReader(f)}
    assert all(r["verdict"] in ("food", "supplement", "junk") and r["top3_hand"] in ("", "no") for r in rows.values())
    return rows


def main():
    selftest()
    lab = labels()
    hit_codes = set()
    seen = set()
    base, dropped = [], Counter()
    audit = []
    with SRC.open(encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f, delimiter="\t"):
            code = r.get("code")
            if not code or code in seen or "en:india" not in (r.get("countries_tags") or "").split(","):
                continue
            seen.add(code)
            txt = (r.get("ingredients_text") or "").strip()
            if not english_list(txt):
                continue
            b = bucket(r.get("categories_tags", ""))
            if b == "excluded_baby":
                dropped["baby_or_supplement_tag"] += 1
                continue
            if b in STAPLES:
                dropped["staple"] += 1
                continue
            name = " ".join((r.get(k) or "") for k in ("product_name", "abbreviated_product_name", "generic_name"))
            if PROTEIN_NAME_RE.search(name):
                dropped["protein_name"] += 1
                continue
            hits = find(txt)
            malto = [h for h in hits if h[2] == "malto"]
            if malto:
                hit_codes.add(code)
                v = lab.get(code, {}).get("verdict")
                if v in ("supplement", "junk"):
                    dropped["hand_" + v] += 1
                    continue
            rec = {"bucket": b or "Uncategorised", "malto": bool(malto), "resistant": any(h[2] == "resistant" for h in hits)}
            if malto:
                rec["top3"], rec["in_bracket"], rec["top_level"] = place(txt, malto)
                if lab.get(code, {}).get("top3_hand") == "no":
                    rec["top3"] = False
                rec["sugar"] = sugar_analyse(txt)["n_sugar_names"] > 0
                for s, e, k in malto:
                    audit.append(f"{code}\t{rec['bucket']}\ttop3={rec['top3']}\t{txt[s:e]!r}\t...{txt[max(0, s - 70):e + 50]}...")
            elif rec["resistant"]:
                audit.append(f"{code}\t{rec['bucket']}\tRESISTANT\t...{txt[:160]}...")
            base.append(rec)
    assert hit_codes == set(lab), (f"maltodextrin_labels.csv must cover exactly the hits: missing {sorted(hit_codes - set(lab))[:5]}, "
                                   f"stale {sorted(set(lab) - hit_codes)[:5]}")
    n = len(base)
    m = [p for p in base if p["malto"]]
    k = len(m)
    by = defaultdict(list)
    for p in base:
        by[p["bucket"]].append(p)
    cats = {c: {**share(sum(p["malto"] for p in ps), len(ps)),
                "top3": sum(p["malto"] and p["top3"] for p in ps)}
            for c, ps in sorted(by.items(), key=lambda kv: -sum(p["malto"] for p in kv[1])) if len(ps) >= MIN_N}
    spell = Counter(re.sub(r"\s+", " ", x.split("\t")[3]).lower() for x in audit if "\tRESISTANT\t" not in x)
    res = {
        "status": "UNPUBLISHED candidate (27 Oct 2026); every hit read by hand (maltodextrin_labels.csv)",
        "base": "non-staple Indian English ingredient lists, baby food, supplements and protein-named products out",
        "lists": n,
        "dropped": dict(dropped),
        "maltodextrin": share(k, n),
        "resistant_maltodextrin_only": sum(1 for p in base if p["resistant"] and not p["malto"]),
        "maltodextrin_top3": share(sum(p["top3"] for p in m), k),
        "maltodextrin_inside_a_bracket_only": share(sum(p["in_bracket"] and not p["top_level"] for p in m), k),
        "maltodextrin_with_added_sugar_name": share(sum(p["sugar"] for p in m), k),
        "by_category_min_n": MIN_N,
        "by_category": cats,
        "spellings": dict(spell.most_common()),
    }
    OUT.mkdir(exist_ok=True)
    (OUT / "maltodextrin.json").write_text(json.dumps(res, indent=1, ensure_ascii=False), encoding="utf-8")
    (OUT / "maltodextrin_audit.txt").write_text("\n".join(audit) + "\n", encoding="utf-8")
    print(json.dumps({x: res[x] for x in ("lists", "dropped", "maltodextrin", "resistant_maltodextrin_only", "maltodextrin_top3",
                                         "maltodextrin_inside_a_bracket_only", "maltodextrin_with_added_sugar_name")}, indent=1))
    for c, v in cats.items():
        print(f"{c:40} {v['k']:4} of {v['n']:5} {v['pct']:5}%  top3 {v['top3']}")
    print(dict(spell.most_common()))


if __name__ == "__main__":
    main()
