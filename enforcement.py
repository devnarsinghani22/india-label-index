"""India Label Index, study 10: the FSSAI test scoreboard.

Reads data/enforcement/fssai_enforcement.csv (rows copied as published from Parliament replies, PIB releases and FSSAI
annual reports; built by data/enforcement/extract_enforcement.py) and data/enforcement/population_census2011.csv.
Writes out/enforcement.json and out/enforcement_table.csv. Every share is kept as k and n.

    python -I enforcement.py

Which published series is used where (the CSV keeps every source row; this picks one per number):
- state-wise 2021-22 to 2025-26: Lok Sabha UQ 1093 (MoHFW, 24 Jul 2026), the latest state annexure; 2025-26 is provisional
- national 2019-20 and 2020-21 and the unsafe / sub-standard / labelling split 2019-20 to 2023-24: Lok Sabha SQ 361 (26 Mar 2025)
- national 2018-19 and criminal cases launched 2018-19 to 2022-23: PIB 1945166 (2 Aug 2023); 2023-24 criminal launched: PIB 2101739
- state-wise unsafe / sub-standard / labelling split: FSSAI Annual Reports 2019-20, 2020-21, 2021-22 (the 2022-23 to 2024-25
  reports are image PDFs; not read)
- population: Census 2011 (A-1), the last census; Telangana and Ladakh summed from their 2011 districts
"""
import csv
import json
from collections import defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CSV = ROOT / "data" / "enforcement" / "fssai_enforcement.csv"
POP = ROOT / "data" / "enforcement" / "population_census2011.csv"
OUT_JSON = ROOT / "out" / "enforcement.json"
OUT_CSV = ROOT / "out" / "enforcement_table.csv"

LS1093 = "AU1093_HciY1m"
LS361 = "2025_LS_B_361"
PIB1945166 = "PRID=1945166"
PIB2101739 = "PRID=2101739"
AR = "fssai.gov.in/docs/annual-report"
STATE_YEARS = ["2021-22", "2022-23", "2023-24", "2024-25", "2025-26"]
MIN_SAMPLES_FOR_RANK = 1000  # a state needs at least this many samples in the period to be ranked on a share


def to_int(v):
    return int(v) if v not in ("", None) else None


def pct(k, n):
    return round(100.0 * k / n, 1) if n else None


def load():
    rows = list(csv.DictReader(CSV.open(encoding="utf-8")))
    for r in rows:
        for c in ("samples_analysed", "non_conforming", "unsafe", "substandard", "misbranded_labelling_defects",
                  "civil_cases", "criminal_cases", "convictions", "penalty_rs"):
            r[c] = to_int(r[c])
    pop = {r["state"]: int(r["population_2011"]) for r in csv.DictReader(POP.open(encoding="utf-8"))}
    return rows, pop


def pick(rows, fy, state, src):
    hits = [r for r in rows if r["fiscal_year"] == fy and r["state"] == state and src in r["source_url"]]
    if not hits:
        return None
    assert len(hits) == 1, (fy, state, src, len(hits))
    return hits[0]


def main():
    rows, pop = load()
    out = {"study": "India Label Index, study 10: the FSSAI test scoreboard", "generated": date.today().isoformat(),
           "population_basis": "Census 2011 (A-1 table, Office of the Registrar General). Telangana = its 10 districts of 2011 Andhra Pradesh; "
                               "Ladakh = Leh and Kargil districts; Dadra & Nagar Haveli and Daman & Diu summed. Rates are per million 2011 residents, "
                               "so they overstate today's per-head testing a little everywhere (India has grown about 17% since 2011).",
           "rank_rule": f"a state or UT is ranked on a share only if it analysed at least {MIN_SAMPLES_FOR_RANK} samples in the period"}

    # ---------------- national series ----------------
    nat = []
    for fy in ["2018-19", "2019-20", "2020-21"] + STATE_YEARS:
        if fy in STATE_YEARS:
            r = pick(rows, fy, "All India", LS1093)
            src = "Lok Sabha UQ 1093, 24 Jul 2026"
        elif fy == "2018-19":
            r = pick(rows, fy, "All India", PIB1945166)
            src = "PIB 1945166 (Lok Sabha reply), 2 Aug 2023"
        else:
            r = pick(rows, fy, "All India", LS361)
            src = "Lok Sabha SQ 361, 26 Mar 2025"
        d = {"fiscal_year": fy, "samples_analysed": r["samples_analysed"], "non_conforming": r["non_conforming"],
             "non_conforming_pct": pct(r["non_conforming"], r["samples_analysed"]), "source": src}
        s361 = pick(rows, fy, "All India", LS361)
        if s361:
            d.update({"unsafe": s361["unsafe"], "substandard": s361["substandard"], "labelling_defects": s361["misbranded_labelling_defects"],
                      "non_conforming_in_split_source": s361["non_conforming"],
                      "labelling_pct_of_non_conforming": pct(s361["misbranded_labelling_defects"], s361["non_conforming"]),
                      "unsafe_pct_of_non_conforming": pct(s361["unsafe"], s361["non_conforming"]),
                      "unsafe_pct_of_samples": pct(s361["unsafe"], s361["samples_analysed"]),
                      "civil_cases_decided_with_penalty": s361["civil_cases"], "criminal_convictions": s361["convictions"],
                      "penalty_rs": s361["penalty_rs"], "split_source": "Lok Sabha SQ 361, 26 Mar 2025"})
        if fy == "2018-19":
            d.update({"civil_cases_launched": r["civil_cases"], "criminal_convictions": r["convictions"],
                      "split_source": "PIB 1945166 (criminal convictions column)"})
        if fy in STATE_YEARS:
            d.update({"civil_cases_decided_with_penalty": r["civil_cases"], "criminal_convictions": r["convictions"]})
            if fy in ("2024-25", "2025-26"):
                p985 = pick(rows, fy, "All India", "AU985_")
                d["penalty_rs"] = p985["penalty_rs"]
        crim = pick(rows, fy, "All India", PIB1945166) or pick(rows, fy, "All India", PIB2101739)
        if crim and crim["criminal_cases"]:
            d["criminal_cases_launched"] = crim["criminal_cases"]
            d["criminal_launched_source"] = "PIB 1945166" if PIB1945166 in crim["source_url"] else "PIB 2101739"
            if d.get("criminal_convictions"):
                d["convictions_per_100_criminal_cases_launched_same_year"] = pct(d["criminal_convictions"], crim["criminal_cases"])
        if d.get("criminal_convictions") is not None:
            d["convictions_per_100_non_conforming"] = pct(d["criminal_convictions"], d["non_conforming"])
        if fy == "2025-26":
            d["provisional"] = True
        nat.append(d)
    out["national"] = nat

    # trend: first vs last, and 2022-23 peak
    first, last = nat[0], nat[-1]
    shares = [(d["fiscal_year"], d["non_conforming_pct"]) for d in nat]
    out["national_trend"] = {
        "first": {"fiscal_year": first["fiscal_year"], "k": first["non_conforming"], "n": first["samples_analysed"], "pct": first["non_conforming_pct"]},
        "last": {"fiscal_year": last["fiscal_year"], "k": last["non_conforming"], "n": last["samples_analysed"], "pct": last["non_conforming_pct"]},
        "peak": max(shares, key=lambda x: x[1]), "low": min(shares, key=lambda x: x[1]),
        "samples_growth_pct": round(100.0 * (last["samples_analysed"] - first["samples_analysed"]) / first["samples_analysed"], 1),
        "eight_year_pooled": {"k": sum(d["non_conforming"] for d in nat), "n": sum(d["samples_analysed"] for d in nat),
                              "pct": pct(sum(d["non_conforming"] for d in nat), sum(d["samples_analysed"] for d in nat))},
        "five_year_pooled_2021_22_to_2025_26": {"k": sum(d["non_conforming"] for d in nat if d["fiscal_year"] in STATE_YEARS),
                                                 "n": sum(d["samples_analysed"] for d in nat if d["fiscal_year"] in STATE_YEARS)},
    }
    out["national_trend"]["five_year_pooled_2021_22_to_2025_26"]["pct"] = pct(**{k: v for k, v in out["national_trend"]["five_year_pooled_2021_22_to_2025_26"].items()})

    # ---------------- state series from LS 1093 ----------------
    states = sorted({r["state"] for r in rows if LS1093 in r["source_url"] and r["state"] != "All India"})
    assert len(states) == 36, len(states)
    per = {fy: {} for fy in STATE_YEARS}
    for fy in STATE_YEARS:
        for s in states:
            per[fy][s] = pick(rows, fy, s, LS1093)

    def state_block(fy_list, label):
        res = []
        for s in states:
            smp = sum(per[fy][s]["samples_analysed"] for fy in fy_list)
            nc = sum(per[fy][s]["non_conforming"] for fy in fy_list)
            civ = sum(per[fy][s]["civil_cases"] for fy in fy_list)
            conv = sum(per[fy][s]["convictions"] for fy in fy_list)
            p = pop[s]
            res.append({"state": s, "period": label, "samples_analysed": smp, "non_conforming": nc, "non_conforming_pct": pct(nc, smp),
                        "civil_cases_decided_with_penalty": civ, "criminal_convictions": conv,
                        "convictions_per_100_non_conforming": pct(conv, nc),
                        "convictions_pct_of_punished_cases": pct(conv, civ + conv), "punished_cases": civ + conv,
                        "population_2011": p,
                        "samples_per_million_per_year": round(smp / len(fy_list) / p * 1e6, 1),
                        "samples_per_10000_per_year": round(smp / len(fy_list) / p * 1e4, 2),
                        "rankable": smp >= MIN_SAMPLES_FOR_RANK})
        return res

    blocks = {"five_year_2021_22_to_2025_26": state_block(STATE_YEARS, "2021-22 to 2025-26"),
              "fy_2025_26_provisional": state_block(["2025-26"], "2025-26 (provisional)"),
              "fy_2024_25": state_block(["2024-25"], "2024-25")}
    out["states"] = blocks

    def rank(block, key, reverse=True, rankable_only=True):
        items = [b for b in block if (b["rankable"] or not rankable_only)]
        return [{"state": b["state"], key: b[key], "k_n": kn(b, key)} for b in sorted(items, key=lambda b: (b[key] if b[key] is not None else -1), reverse=reverse)]

    def kn(b, key):
        if key == "non_conforming_pct":
            return f"{b['non_conforming']} of {b['samples_analysed']}"
        if key == "convictions_per_100_non_conforming":
            return f"{b['criminal_convictions']} of {b['non_conforming']}"
        if key == "convictions_pct_of_punished_cases":
            return f"{b['criminal_convictions']} of {b['punished_cases']}"
        if key == "samples_per_million_per_year":
            return f"{b['samples_analysed']} samples over the period, population {b['population_2011']}"
        return ""

    rankings = {}
    for name, block in blocks.items():
        rankings[name] = {
            "non_conforming_share_high_to_low": rank(block, "non_conforming_pct"),
            "samples_per_million_per_year_high_to_low": rank(block, "samples_per_million_per_year", rankable_only=False),
            "convictions_per_100_non_conforming_high_to_low": rank(block, "convictions_per_100_non_conforming"),
            "convictions_share_of_punished_cases_high_to_low": rank(block, "convictions_pct_of_punished_cases"),
            "zero_convictions": sorted(b["state"] for b in block if b["criminal_convictions"] == 0),
            "zero_convictions_with_non_conforming_samples": sorted(b["state"] for b in block if b["criminal_convictions"] == 0 and b["non_conforming"] > 0),
            "not_ranked_small_n": sorted(f"{b['state']} ({b['samples_analysed']} samples)" for b in block if not b["rankable"]),
        }
    out["rankings"] = rankings

    # low-testing states: fewer than 1 sample per 10,000 residents (= 100 per million) in a year
    low = {}
    for name, block in blocks.items():
        under = sorted(b["state"] for b in block if b["samples_per_10000_per_year"] < 1.0)
        low[name] = {"k": len(under), "n": len(block), "states": under,
                     "population_covered": sum(pop[s] for s in under), "population_total_36": sum(pop[s] for s in states),
                     "population_covered_pct": pct(sum(pop[s] for s in under), sum(pop[s] for s in states))}
    out["under_one_sample_per_10000"] = low
    # national rate
    out["national_samples_per_10000"] = {d["fiscal_year"]: round(d["samples_analysed"] / pop["All India"] * 1e4, 2) for d in nat}

    # concentration: UP share of national non-conforming
    conc = {}
    for fy in STATE_YEARS:
        tot_nc = sum(per[fy][s]["non_conforming"] for s in states)
        tot_s = sum(per[fy][s]["samples_analysed"] for s in states)
        up = per[fy]["Uttar Pradesh"]
        rest_nc, rest_s = tot_nc - up["non_conforming"], tot_s - up["samples_analysed"]
        conc[fy] = {"up_non_conforming": up["non_conforming"], "all_non_conforming": tot_nc, "up_pct_of_non_conforming": pct(up["non_conforming"], tot_nc),
                    "up_samples": up["samples_analysed"], "all_samples": tot_s, "up_pct_of_samples": pct(up["samples_analysed"], tot_s),
                    "up_non_conforming_pct": pct(up["non_conforming"], up["samples_analysed"]),
                    "rest_of_india_non_conforming_pct": pct(rest_nc, rest_s), "rest_k": rest_nc, "rest_n": rest_s}
    out["uttar_pradesh_concentration"] = conc

    # ---------------- labelling share by state (annual reports) ----------------
    lab = {}
    for fy in ("2019-20", "2020-21", "2021-22"):
        items = []
        for r in rows:
            if r["fiscal_year"] == fy and AR in r["source_url"] and r["state"] != "All India" and r["misbranded_labelling_defects"] is not None:
                items.append({"state": r["state"], "labelling_defects": r["misbranded_labelling_defects"], "non_conforming": r["non_conforming"],
                              "unsafe": r["unsafe"], "substandard": r["substandard"], "samples_analysed": r["samples_analysed"],
                              "labelling_pct_of_non_conforming": pct(r["misbranded_labelling_defects"], r["non_conforming"]),
                              "rankable": r["non_conforming"] >= 100})
        tot = pick(rows, fy, "All India", AR)
        lab[fy] = {"states_with_split": len(items),
                   "national": {"labelling_defects": tot["misbranded_labelling_defects"], "non_conforming": tot["non_conforming"],
                                "pct": pct(tot["misbranded_labelling_defects"], tot["non_conforming"]),
                                "unsafe": tot["unsafe"], "substandard": tot["substandard"],
                                "note": "annual report total row" + (" (its non-conforming total 29,192 is below the 29,589 that its own state rows add to and that Parliament gives)" if fy == "2019-20" else "")},
                   "states_high_to_low_min100_non_conforming": sorted([i for i in items if i["rankable"]], key=lambda i: i["labelling_pct_of_non_conforming"], reverse=True),
                   "states_labelling_is_largest_bucket": sorted(i["state"] for i in items if i["labelling_defects"] > max(i["unsafe"] or 0, i["substandard"] or 0) and i["rankable"])}
    out["labelling_split"] = lab

    # ---------------- disagreements between sources (same year, same thing) ----------------
    dis = [
        {"what": "2019-20 non-conforming (all India)", "a": "29,589 (LS SQ 361; PIB 1945166; the FSSAI Annual Report 2019-20 state rows add to 29,589)", "b": "29,192 (FSSAI Annual Report 2019-20 total row)"},
        {"what": "2019-20 criminal convictions", "a": "821 (LS SQ 361; Annual Report 'criminal cases decided')", "b": "780 (PIB 1945166)"},
        {"what": "2021-22 non-conforming", "a": "32,934 (LS SQ 361; Annual Report 2021-22)", "b": "32,935 (LS UQ 1093 state annexure total)"},
        {"what": "2022-23 samples / non-conforming", "a": "1,77,511 / 44,626 (LS SQ 361; LS UQ 1093)", "b": "1,72,687 / 44,421 (PIB 1945166, Aug 2023, an earlier cut)"},
        {"what": "2022-23 criminal convictions", "a": "1,188 (LS SQ 361; LS UQ 1093)", "b": "1,133 (PIB 1945166)"},
        {"what": "2024-25 samples analysed", "a": "1,70,535 (LS UQ 1093 and UQ 985, Jul 2026; PIB 2225750, Feb 2026)", "b": "1,94,116 'lifted/analysed' (LS UQ 2076, 1 Aug 2025)"},
        {"what": "2024-25 Maharashtra samples", "a": "5,403 (LS UQ 1093)", "b": "8,788 (LS UQ 2076, Aug 2025)"},
        {"what": "2023-24 state table", "a": "LS UQ 1093 / PIB 2225750 (sum 1,70,513 / 33,808)", "b": "data.gov.in copy of RS UQ 902 (Nov 2024, provisional; sums 1,69,725 / 33,368)"},
    ]
    out["source_disagreements"] = dis

    # ---------------- headline numbers (k of n) ----------------
    fy26 = {b["state"]: b for b in blocks["fy_2025_26_provisional"]}
    fy5 = {b["state"]: b for b in blocks["five_year_2021_22_to_2025_26"]}
    out["headline"] = {
        "fy_2025_26_non_conforming": {"k": last["non_conforming"], "n": last["samples_analysed"], "pct": last["non_conforming_pct"], "provisional": True},
        "fy_2025_26_convictions": {"k": last["criminal_convictions"], "n": last["non_conforming"], "pct": last["convictions_per_100_non_conforming"]},
        "five_year_convictions": {"k": sum(d["criminal_convictions"] for d in nat if d["fiscal_year"] in STATE_YEARS),
                                  "n": sum(d["non_conforming"] for d in nat if d["fiscal_year"] in STATE_YEARS)},
        "five_year_penalty_cases": {"k": sum(d["civil_cases_decided_with_penalty"] for d in nat if d["fiscal_year"] in STATE_YEARS),
                                    "n": sum(d["non_conforming"] for d in nat if d["fiscal_year"] in STATE_YEARS)},
        "labelling_2023_24": {"k": nat[-3]["labelling_defects"], "n": nat[-3]["non_conforming"], "pct": nat[-3]["labelling_pct_of_non_conforming"]},
        "labelling_2022_23": {"k": nat[-4]["labelling_defects"], "n": nat[-4]["non_conforming"], "pct": nat[-4]["labelling_pct_of_non_conforming"]},
        # denominators from the same reply (LS 361) as the split, so 2021-22 is 32,934 there, not the 32,935 of UQ 1093
        "labelling_five_years_2019_20_to_2023_24": {"k": sum(d["labelling_defects"] for d in nat if "labelling_defects" in d),
                                                     "n": sum(d["non_conforming_in_split_source"] for d in nat if "labelling_defects" in d)},
        "unsafe_five_years_2019_20_to_2023_24": {"k": sum(d["unsafe"] for d in nat if "unsafe" in d),
                                                  "n": sum(d["non_conforming_in_split_source"] for d in nat if "unsafe" in d)},
        "up_2025_26": conc["2025-26"],
        "under_one_per_10000_2025_26": low["fy_2025_26_provisional"],
        "under_one_per_10000_2024_25": low["fy_2024_25"],
        "zero_convictions_2025_26": rankings["fy_2025_26_provisional"]["zero_convictions_with_non_conforming_samples"],
        "zero_convictions_five_years": rankings["five_year_2021_22_to_2025_26"]["zero_convictions_with_non_conforming_samples"],
        "tamil_nadu_2025_26": fy26["Tamil Nadu"], "kerala_2025_26": fy26["Kerala"], "uttar_pradesh_2025_26": fy26["Uttar Pradesh"],
        "bihar_5y": fy5["Bihar"], "west_bengal_5y": fy5["West Bengal"], "maharashtra_5y": fy5["Maharashtra"],
    }
    for k in ("five_year_convictions", "five_year_penalty_cases", "labelling_five_years_2019_20_to_2023_24", "unsafe_five_years_2019_20_to_2023_24"):
        out["headline"][k]["pct"] = pct(out["headline"][k]["k"], out["headline"][k]["n"])

    OUT_JSON.parent.mkdir(exist_ok=True)
    OUT_JSON.write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")

    # ---------------- flat table ----------------
    with OUT_CSV.open("w", newline="", encoding="utf-8") as f:
        cols = ["period", "state", "samples_analysed", "non_conforming", "non_conforming_pct", "civil_cases_decided_with_penalty", "criminal_convictions",
                "convictions_per_100_non_conforming", "convictions_pct_of_punished_cases", "population_2011", "samples_per_million_per_year",
                "samples_per_10000_per_year", "rankable"]
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for name, block in blocks.items():
            for b in block:
                w.writerow({c: b[c] for c in cols})
            # all-India line per block
            fys = {"five_year_2021_22_to_2025_26": STATE_YEARS, "fy_2025_26_provisional": ["2025-26"], "fy_2024_25": ["2024-25"]}[name]
            smp = sum(per[fy][s]["samples_analysed"] for fy in fys for s in states)
            nc = sum(per[fy][s]["non_conforming"] for fy in fys for s in states)
            civ = sum(per[fy][s]["civil_cases"] for fy in fys for s in states)
            conv = sum(per[fy][s]["convictions"] for fy in fys for s in states)
            w.writerow({"period": block[0]["period"], "state": "All India (36 states/UTs)", "samples_analysed": smp, "non_conforming": nc,
                        "non_conforming_pct": pct(nc, smp), "civil_cases_decided_with_penalty": civ, "criminal_convictions": conv,
                        "convictions_per_100_non_conforming": pct(conv, nc), "convictions_pct_of_punished_cases": pct(conv, civ + conv),
                        "population_2011": pop["All India"], "samples_per_million_per_year": round(smp / len(fys) / pop["All India"] * 1e6, 1),
                        "samples_per_10000_per_year": round(smp / len(fys) / pop["All India"] * 1e4, 2), "rankable": True})

    # ---------------- console summary ----------------
    print("NATIONAL non-conforming share by year")
    for d in nat:
        print(f"  {d['fiscal_year']}: {d['non_conforming']:>6} of {d['samples_analysed']:>7} = {d['non_conforming_pct']}%"
              + (f" | labelling {d['labelling_defects']} ({d['labelling_pct_of_non_conforming']}%) unsafe {d['unsafe']} sub {d['substandard']}" if 'labelling_defects' in d else "")
              + (f" | convictions {d.get('criminal_convictions')} ({d.get('convictions_per_100_non_conforming')} per 100 NC)" if d.get('criminal_convictions') else "")
              + (f" | crim launched {d['criminal_cases_launched']} -> {d.get('convictions_per_100_criminal_cases_launched_same_year')}%" if d.get('criminal_cases_launched') else ""))
    print("TREND", json.dumps(out["national_trend"]))
    for name in blocks:
        r = rankings[name]
        print(f"\n{name}: NC share top5 {[(x['state'], x['non_conforming_pct']) for x in r['non_conforming_share_high_to_low'][:5]]}")
        print(f"  NC share bottom5 {[(x['state'], x['non_conforming_pct']) for x in r['non_conforming_share_high_to_low'][-5:]]}")
        print(f"  samples/million top5 {[(x['state'], x['samples_per_million_per_year']) for x in r['samples_per_million_per_year_high_to_low'][:5]]}")
        print(f"  samples/million bottom8 {[(x['state'], x['samples_per_million_per_year']) for x in r['samples_per_million_per_year_high_to_low'][-8:]]}")
        print(f"  conv/100 NC top5 {[(x['state'], x['convictions_per_100_non_conforming'], x['k_n']) for x in r['convictions_per_100_non_conforming_high_to_low'][:5]]}")
        print(f"  zero convictions (with NC>0): {r['zero_convictions_with_non_conforming_samples']}")
        print(f"  not ranked: {r['not_ranked_small_n']}")
        print(f"  under 1 per 10,000: {low[name]['k']} of {low[name]['n']} -> {low[name]['states']} covering {low[name]['population_covered_pct']}% of 2011 population")
    print("\nUP concentration", json.dumps(conc["2025-26"]))
    print("\nLABELLING by state (2021-22) top5", [(i["state"], i["labelling_pct_of_non_conforming"], i["labelling_defects"], i["non_conforming"]) for i in lab["2021-22"]["states_high_to_low_min100_non_conforming"][:5]])
    print("  labelling largest bucket 2021-22:", lab["2021-22"]["states_labelling_is_largest_bucket"])
    print("\nHEADLINE", json.dumps({k: v for k, v in out["headline"].items() if not isinstance(v, dict) or "state" not in v}, ensure_ascii=False)[:3000])
    print(f"\nwrote {OUT_JSON} and {OUT_CSV}")


if __name__ == "__main__":
    main()
