"""Precision audit of sugar detection: every distinct matched phrase with counts and context samples,
plus the 'no added sugar' products that still match. Brand names are not printed."""
import csv
import random
from collections import Counter, defaultdict
from pathlib import Path

from sugar import NAMES, KINDS, find_sugars

csv.field_size_limit(2**31 - 1)
rows = list(csv.DictReader((Path(__file__).parent / "data" / "off_india.csv").open(encoding="utf-8"), delimiter="\t"))
phr, ctx = Counter(), defaultdict(list)
nas = []
for r in rows:
    ing = (r.get("ingredients_text") or "").strip()
    if len(ing) < 8 or not ing.isascii():
        continue
    hits = find_sugars(ing)
    for s, e, i in hits:
        if KINDS[i] != "sugar":
            continue
        key = ing[s:e].lower()
        phr[key] += 1
        if len(ctx[key]) < 4:
            ctx[key].append(ing[max(0, s - 40):e + 40].replace("\n", " "))
    lab = r.get("labels_tags", "") or ""
    if ("en:no-added-sugar" in lab) and any(KINDS[i] == "sugar" for _, _, i in hits):
        nas.append((r["code"], [ing[s:e] for s, e, i in hits if KINDS[i] == "sugar"], ing[:300].replace("\n", " ")))

for k, n in phr.most_common(80):
    print(f"{n:5}  {k!r}")
    for c in ctx[k][:2]:
        print("        ..." + c + "...")
print("\n=== NO ADDED SUGAR products still matching ===")
for code, hs, ing in nas:
    print(code, hs, "|", ing)
