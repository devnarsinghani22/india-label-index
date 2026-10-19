"""What sweetens a 'no added sugar' pack? (India Label Index, 19 October 2026; UNPUBLISHED until every counted claim is
photo-checked.)

Which products: every Open Food Facts India row (data/off_india.csv, one row per barcode) whose labels carry the
'no added sugar' tag (en:no-added-sugar, en:no-added-sugars, en:no-sugar-added) or whose product name says it, and whose
ingredient list the English matchers can read (fats.english_list). Every one of those lists was read by hand;
nas_labels.csv holds the verdicts, and the script fails if a candidate is missing from it or it holds a code that is no
longer a candidate.
  verdict  food        = a made food with the claim
           single      = one food, alone or with only water, salt, an acid, a preservative, a stabiliser or a culture
                         (dates, raisins, oats, peanut butter, honey, one-fruit juice, coconut water, plain yoghurt):
                         nothing sweet could be added, so these are counted apart
           supplement  = protein, collagen or herbal supplement powder or tonic (left out, as in every Index study)
           unreadable  = the list cannot be read
           duplicate:X = the same product and list as barcode X (counted once)
  sugar    = sugar names in the list under the Label Checker rules (sugar.py): sugar, jaggery, honey, syrups, glucose,
             fruit juice concentrate (WHO counts it as free sugar). Lemon or lime concentrate never counts.
  dates    = dates or date powder in the list (not a sugar name in the Index rules; reported on its own)
  polyol / intense = non-sugar sweeteners (sweeteners.py names)
  claim_photo = confirmed (the pack photo on Open Food Facts prints 'no added sugar'), tag_wrong (the photos show a
             different claim; the row is dropped), not_seen (the photos do not show the claim), blank (not checked yet)
The script checks the hand columns against sugar.find_sugars and sweeteners.find and fails on any disagreement.
Category level only: brand names are never output (nas_labels.csv holds barcodes and plain product types).
Caveat: Open Food Facts is crowd-entered, not a random sample of what India buys; the claim tag itself is crowd-entered,
and 2 of the first 8 tags checked against the photos were wrong.
Output: out/nas.json, out/nas_audit.txt. Run: python -I nas.py"""
import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from sugar import KINDS, NAMES, find_sugars  # noqa: E402
from fats import english_list  # noqa: E402
import sweeteners as sw  # noqa: E402

csv.field_size_limit(2**31 - 1)
SRC = HERE / "data" / "off_india.csv"
LABELS = HERE / "nas_labels.csv"
OUT = HERE / "out"

NAME_RE = re.compile(r"\bno\s+(?:added\s+)?sugars?\s+added\b|\bno[\s-]+added[\s-]+sugars?\b|\bwithout\s+added\s+sugars?\b|"
                     r"\bno\s+sugar\s+added\b", re.I)
TAGS = {"en:no-added-sugar", "en:no-added-sugars", "en:no-sugar-added"}
DATES_RE = re.compile(r"\bdates?\b(?!\s*(?:of|:))|\bkhajoor\b", re.I)
VERDICTS = ("food", "single", "supplement", "unreadable", "duplicate")
CLAIMS = ("confirmed", "tag_wrong", "not_seen", "")


def candidates():
    seen, out = set(), {}
    with SRC.open(encoding="utf-8") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            code = row.get("code")
            name = (row.get("product_name") or "").strip()
            tags = {t.strip() for t in (row.get("labels_tags") or "").split(",")}
            if not (NAME_RE.search(name) or TAGS & tags):
                continue
            ing = (row.get("ingredients_text") or "").strip()
            if not code or code in seen or not ing or not english_list(ing):
                continue
            seen.add(code)
            out[code] = {"ing": re.sub(r"\s+", " ", ing), "additives": row.get("additives_tags")}
    return out


def kn(k, n):
    return {"k": k, "n": n, "pct": round(100 * k / n, 1) if n else None}


def main():
    cands = candidates()
    labels = {r["code"]: r for r in csv.DictReader(LABELS.open(encoding="utf-8"))}
    missing, extra = sorted(set(cands) - set(labels)), sorted(set(labels) - set(cands))
    assert not missing and not extra, f"audit out of step with the data: missing {missing}, extra {extra}"
    clash = []
    for r in labels.values():
        v = r["verdict"].split(":")[0]
        assert v in VERDICTS and r["claim_photo"] in CLAIMS, r["code"]
        if r["verdict"].startswith("duplicate:"):
            assert r["verdict"].split(":", 1)[1] in labels, r["code"]
        if v != "food":
            continue
        ing = cands[r["code"]]["ing"]
        m_sugar = any(KINDS[h[2]] == "sugar" for h in find_sugars(ing))
        m_sweet = sw.find(ing) | sw.tag_find(cands[r["code"]]["additives"])
        m_poly = {s for s in m_sweet if sw.KIND.get(s) == "polyol"}
        m_int = {s for s in m_sweet if sw.KIND.get(s) == "intense"}
        for col, hand, auto in (("sugar", bool(r["sugar"]), m_sugar), ("dates", bool(r["dates"]), bool(DATES_RE.search(ing))),
                                ("polyol", bool(r["polyol"]), bool(m_poly)), ("intense", bool(r["intense"]), bool(m_int))):
            if hand != auto:
                clash.append(f"{r['code']} {col}: hand={hand} matcher={auto}")
    assert not clash, "hand read and matchers disagree:\n" + "\n".join(clash)

    verdicts = Counter(r["verdict"].split(":")[0] for r in labels.values())
    foods_all = [r for r in labels.values() if r["verdict"] == "food"]
    claims = Counter(r["claim_photo"] or "unchecked" for r in foods_all)
    foods = [r for r in foods_all if r["claim_photo"] != "tag_wrong"]
    n = len(foods)
    sugar = [r for r in foods if r["sugar"]]
    dates = [r for r in foods if r["dates"]]
    poly = [r for r in foods if r["polyol"]]
    inten = [r for r in foods if r["intense"]]
    any_sw = [r for r in foods if r["polyol"] or r["intense"]]
    none = [r for r in foods if not (r["sugar"] or r["dates"] or r["polyol"] or r["intense"])]
    sugar_names = Counter(s.strip() for r in sugar for s in r["sugar"].split(";"))
    poly_names = Counter(s.strip() for r in poly for s in r["polyol"].split(";"))
    int_names = Counter(s.strip() for r in inten for s in r["intense"].split(";"))

    res = {
        "source": "Open Food Facts India rows (data/off_india.csv, pulled 1 October 2026), hand-audited 19 October 2026",
        "status": "UNPUBLISHED: claim photo check incomplete" if claims.get("unchecked") else "claim photo check complete",
        "candidates_with_english_list": len(cands),
        "verdicts": dict(verdicts),
        "claim_photo_check_of_foods": dict(claims),
        "foods_counted": n,
        "sugar_name": kn(len(sugar), n),
        "dates_or_date_powder": kn(len(dates), n),
        "non_sugar_sweetener": kn(len(any_sw), n),
        "polyol": kn(len(poly), n),
        "intense_sweetener": kn(len(inten), n),
        "sugar_name_and_sweetener": kn(sum(1 for r in sugar if r["polyol"] or r["intense"]), n),
        "none_of_these": kn(len(none), n),
        "sugar_names": dict(sugar_names.most_common()),
        "polyols": dict(poly_names.most_common()),
        "intense_sweeteners": dict(int_names.most_common()),
        "single_foods_with_the_claim": verdicts["single"],
    }
    OUT.mkdir(exist_ok=True)
    (OUT / "nas.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    with (OUT / "nas_audit.txt").open("w", encoding="utf-8") as f:
        for r in sorted(foods_all, key=lambda r: (r["claim_photo"], r["code"])):
            f.write(f"{r['code']}\tclaim={r['claim_photo'] or '-'}\tsugar={r['sugar'] or '-'}\tdates={r['dates'] or '-'}\t"
                    f"polyol={r['polyol'] or '-'}\tintense={r['intense'] or '-'}\n\t{r['note']}\n\t{cands[r['code']]['ing'][:300]}\n")
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
