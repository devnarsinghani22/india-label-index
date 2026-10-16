"""Independent recount for study 10. Re-derives the headline numbers from data/enforcement/fssai_enforcement.csv by a
different route (filter rows by the note text, sum with Counter, no shared code with enforcement.py) and compares them with
out/enforcement.json. Exit code 1 on any mismatch.

    python -I enforcement_recount.py
"""
import csv
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
rows = list(csv.DictReader((ROOT / "data/enforcement/fssai_enforcement.csv").open(encoding="utf-8")))
pop = {r["state"]: int(r["population_2011"]) for r in csv.DictReader((ROOT / "data/enforcement/population_census2011.csv").open(encoding="utf-8"))}
J = json.loads((ROOT / "out/enforcement.json").read_text(encoding="utf-8"))
fails = []


def check(name, got, want):
    ok = got == want
    print(("PASS " if ok else "FAIL ") + f"{name}: recount {got} vs json {want}")
    if not ok:
        fails.append(name)


# --- state rows of the 24 Jul 2026 annexure, by note text (not by URL) ---
ann = [r for r in rows if r["note"].startswith("Lok Sabha UQ 1093") and r["state"] != "All India"]
check("annexure rows", len(ann), 5 * 36)
smp, nc, civ, conv = Counter(), Counter(), Counter(), Counter()
for r in ann:
    smp[r["fiscal_year"]] += int(r["samples_analysed"])
    nc[r["fiscal_year"]] += int(r["non_conforming"])
    civ[r["fiscal_year"]] += int(r["civil_cases"])
    conv[r["fiscal_year"]] += int(r["convictions"])
nat = {d["fiscal_year"]: d for d in J["national"]}
for fy in ("2021-22", "2022-23", "2023-24", "2024-25", "2025-26"):
    check(f"{fy} samples", smp[fy], nat[fy]["samples_analysed"])
    check(f"{fy} non-conforming", nc[fy], nat[fy]["non_conforming"])
    check(f"{fy} convictions", conv[fy], nat[fy]["criminal_convictions"])
    # published total row must equal the state sum
    tot = [r for r in rows if r["note"].startswith("Lok Sabha UQ 1093") and r["state"] == "All India" and r["fiscal_year"] == fy][0]
    check(f"{fy} published total = state sum", (int(tot["samples_analysed"]), int(tot["non_conforming"])), (smp[fy], nc[fy]))
five_nc = sum(nc.values())
check("five-year non-conforming", five_nc, J["headline"]["five_year_convictions"]["n"])
check("five-year convictions", sum(conv.values()), J["headline"]["five_year_convictions"]["k"])
check("five-year penalty cases", sum(civ.values()), J["headline"]["five_year_penalty_cases"]["k"])
check("2025-26 share rounds to", round(100 * nc["2025-26"] / smp["2025-26"], 1), J["headline"]["fy_2025_26_non_conforming"]["pct"])

# --- Uttar Pradesh share of 2025-26 failures ---
up = [r for r in ann if r["state"] == "Uttar Pradesh" and r["fiscal_year"] == "2025-26"][0]
check("UP 2025-26 non-conforming", int(up["non_conforming"]), J["headline"]["up_2025_26"]["up_non_conforming"])
check("UP share of failures", round(100 * int(up["non_conforming"]) / nc["2025-26"], 1), J["headline"]["up_2025_26"]["up_pct_of_non_conforming"])
rest_nc = nc["2025-26"] - int(up["non_conforming"])
rest_s = smp["2025-26"] - int(up["samples_analysed"])
check("rest-of-India 2025-26 share", round(100 * rest_nc / rest_s, 1), J["headline"]["up_2025_26"]["rest_of_india_non_conforming_pct"])

# --- states under 1 sample per 10,000 residents, 2025-26 and 2024-25 ---
for fy, key in (("2025-26", "under_one_per_10000_2025_26"), ("2024-25", "under_one_per_10000_2024_25")):
    under = sorted(r["state"] for r in ann if r["fiscal_year"] == fy and int(r["samples_analysed"]) * 10000 < pop[r["state"]])
    check(f"under 1 per 10,000 {fy}", under, J["headline"][key]["states"])
    check(f"under 1 per 10,000 {fy} count", len(under), J["headline"][key]["k"])

# --- zero convictions with failures, 2025-26 and five years pooled ---
z26 = sorted(r["state"] for r in ann if r["fiscal_year"] == "2025-26" and int(r["convictions"]) == 0 and int(r["non_conforming"]) > 0)
check("zero convictions 2025-26", z26, J["headline"]["zero_convictions_2025_26"])
c5, n5 = Counter(), Counter()
for r in ann:
    c5[r["state"]] += int(r["convictions"])
    n5[r["state"]] += int(r["non_conforming"])
check("zero convictions five years", sorted(s for s in c5 if c5[s] == 0 and n5[s] > 0), J["headline"]["zero_convictions_five_years"])

# --- labelling split from the Consumer Affairs reply (LS 361) ---
l361 = [r for r in rows if "Starred Q 361" in r["note"]]
check("LS 361 rows", len(l361), 5)
lab = sum(int(r["misbranded_labelling_defects"]) for r in l361)
ncs = sum(int(r["non_conforming"]) for r in l361)
check("labelling five years k", lab, J["headline"]["labelling_five_years_2019_20_to_2023_24"]["k"])
check("labelling five years n", ncs, J["headline"]["labelling_five_years_2019_20_to_2023_24"]["n"])
r24 = [r for r in l361 if r["fiscal_year"] == "2023-24"][0]
check("labelling 2023-24", (int(r24["misbranded_labelling_defects"]), int(r24["non_conforming"])), (J["headline"]["labelling_2023_24"]["k"], J["headline"]["labelling_2023_24"]["n"]))
check("unsafe five years k", sum(int(r["unsafe"]) for r in l361), J["headline"]["unsafe_five_years_2019_20_to_2023_24"]["k"])

# --- Tamil Nadu and Kerala 2025-26 ---
for st, key in (("Tamil Nadu", "tamil_nadu_2025_26"), ("Kerala", "kerala_2025_26"), ("Uttar Pradesh", "uttar_pradesh_2025_26")):
    r = [x for x in ann if x["state"] == st and x["fiscal_year"] == "2025-26"][0]
    check(f"{st} 2025-26 convictions/NC", (int(r["convictions"]), int(r["non_conforming"])), (J["headline"][key]["criminal_convictions"], J["headline"][key]["non_conforming"]))
    check(f"{st} 2025-26 per million", round(int(r["samples_analysed"]) / pop[st] * 1e6, 1), J["headline"][key]["samples_per_million_per_year"])

# --- annual report 2021-22 labelling by state: recompute the top state ---
ar = [r for r in rows if r["note"].startswith("FSSAI Annual Report 2021-22") and r["state"] != "All India" and int(r["non_conforming"]) >= 100]
top = max(ar, key=lambda r: int(r["misbranded_labelling_defects"]) / int(r["non_conforming"]))
check("2021-22 top labelling state", top["state"], J["labelling_split"]["2021-22"]["states_high_to_low_min100_non_conforming"][0]["state"])

print(f"\n{len(fails)} mismatches" if fails else "\nALL PASS")
sys.exit(1 if fails else 0)
