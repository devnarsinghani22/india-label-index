"""India Label Index, study 16: what FSSAI's Food Authority approved, against what FSSAI's own list shows as notified.

Reads data/food-authority/food_authority_lines.csv: one row per agenda line in the Food Authority minutes (43rd,
44th, 46th and 48th meetings, February 2024 to September 2025) that approved a DRAFT or a FINAL notification amending a
food standards, additives, contaminants, labelling, alcohol, sales-restriction, fortification, packaging or grading
regulation, with the date each one appears on FSSAI's notifications list (https://www.fssai.gov.in/food-law/notifications,
searched by title, and every FPS&FA draft or final PDF listed after 7 March 2025 read in full). The 45th approved no
such line; the 47th file holds only the CEO's report. Rows the minutes leave unclear are kept with counted = no.
Two rows stand for many lines (lines = 31 and 21): the 46th meeting listed each FPS&FA change on its own line.
Writes out/food_authority.json. Days run from the meeting date to the list date.

    python -I food_authority.py [AS_OF]      # AS_OF = the day the list was checked, default 2026-10-29
"""
import csv
import json
import statistics
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CSV = ROOT / "data" / "food-authority" / "food_authority_lines.csv"
OUT = ROOT / "out" / "food_authority.json"
MEETINGS = {"43": "2024-02-02", "44": "2024-06-19", "46": "2025-03-07", "48": "2025-09-15"}
BOLD_RULE = "44.1-4"   # per-serve %RDA in bold, larger letters for added sugar, saturated fat and sodium


def d(s):
    return date.fromisoformat(s) if s else None


def build(as_of):
    rows = list(csv.DictReader(CSV.open(encoding="utf-8")))
    for r in rows:
        assert MEETINGS[r["meeting"]] == r["meeting_date"], r["minutes_line"]
        assert r["approved_for"] in ("final", "draft", "unclear"), r["minutes_line"]
    use = [r for r in rows if r["counted"] == "yes"]
    w = lambda r: int(r["lines"])

    def stage(rs, kind):
        n = sum(w(r) for r in rs if r["approved_for"] == kind)
        if kind == "final":
            done = [r for r in rs if r["approved_for"] == "final" and r["final_on_list"]]
            lags = sorted(lag for r in done for lag in [(d(r["final_on_list"]) - d(r["meeting_date"])).days] * w(r))
            return {"approved": n, "final_on_list": sum(w(r) for r in done), "days_to_final": lags,
                    "median_days": statistics.median(lags) if lags else None}
        dr = [r for r in rs if r["approved_for"] == "draft" and r["draft_on_list"] and d(r["draft_on_list"]) >= d(r["meeting_date"])]
        lags = sorted(lag for r in dr for lag in [(d(r["draft_on_list"]) - d(r["meeting_date"])).days] * w(r))
        return {"approved": n, "draft_on_list": sum(w(r) for r in dr), "days_to_draft": lags,
                "median_days": statistics.median(lags) if lags else None,
                "final_on_list": sum(w(r) for r in rs if r["approved_for"] == "draft" and r["final_on_list"])}

    by_meeting = {}
    for m, md in MEETINGS.items():
        rs = [r for r in use if r["meeting"] == m]
        by_meeting[m] = {"date": md, "final": stage(rs, "final"), "draft": stage(rs, "draft"),
                         "days_since_meeting": (as_of - d(md)).days}
    fps46_final = [r for r in use if r["minutes_line"] == "46.1-8.x"][0]
    fps46_draft = [r for r in use if r["minutes_line"] == "46.1-12.x"][0]
    bold = [r for r in use if r["minutes_line"] == BOLD_RULE][0]
    cycles = [{"line": r["minutes_line"], "change": r["change"], "meeting": r["meeting"], "approved_for": r["approved_for"],
               "meeting_date": r["meeting_date"], "final_on_list": r["final_on_list"],
               "days": (d(r["final_on_list"]) - d(r["meeting_date"])).days}
              for r in use if r["final_on_list"]]
    out = {"as_of": as_of.isoformat(),
           "source": "FSSAI Food Authority minutes (43rd, 44th, 46th, 48th) and FSSAI's notifications list",
           "lines_in_file": len(rows), "rows_counted": len(use),
           "rows_not_counted": [{"line": r["minutes_line"], "why": r["counted"]} for r in rows if r["counted"] != "yes"],
           "all_meetings": {"final": stage(use, "final"), "draft": stage(use, "draft")},
           "by_meeting": by_meeting,
           "fpsfa_46th": {"final_approved": w(fps46_final), "final_on_list": 0 if not fps46_final["final_on_list"] else w(fps46_final),
                          "draft_approved": w(fps46_draft), "draft_on_list": 0 if not fps46_draft["draft_on_list"] else w(fps46_draft),
                          "days_since_meeting": (as_of - d(fps46_final["meeting_date"])).days},
           "bold_per_serve_rule": {"approved": bold["meeting_date"], "draft_on_list": bold["draft_on_list"],
                                   "final_on_list": bold["final_on_list"] or None,
                                   "days_since_approval": (as_of - d(bold["meeting_date"])).days},
           "cycles": cycles}
    return out


def check(o):
    """The numbers the study page and its brief rest on (as of 29 Oct 2026)."""
    if o["as_of"] != "2026-10-29":
        return
    a = o["all_meetings"]
    assert (a["final"]["final_on_list"], a["final"]["approved"]) == (8, 41)
    assert a["final"]["days_to_final"] == [252, 263, 265, 453, 508, 532, 532, 787] and a["final"]["median_days"] == 480.5
    assert (a["draft"]["draft_on_list"], a["draft"]["approved"], a["draft"]["final_on_list"]) == (18, 44, 2)
    assert a["draft"]["median_days"] == 245.5
    f = o["fpsfa_46th"]
    assert (f["final_on_list"], f["final_approved"], f["draft_on_list"], f["draft_approved"], f["days_since_meeting"]) == (0, 31, 0, 21, 601)
    m = o["by_meeting"]
    assert [(m[k]["final"]["final_on_list"], m[k]["final"]["approved"]) for k in m] == [(5, 5), (0, 0), (2, 34), (1, 2)]
    assert [(m[k]["draft"]["draft_on_list"], m[k]["draft"]["approved"]) for k in m] == [(9, 9), (5, 6), (3, 24), (1, 5)]
    assert o["bold_per_serve_rule"]["days_since_approval"] == 862 and o["bold_per_serve_rule"]["final_on_list"] is None


if __name__ == "__main__":
    as_of = date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else date(2026, 10, 29)
    o = build(as_of)
    check(o)
    OUT.write_text(json.dumps(o, indent=1, ensure_ascii=False), encoding="utf-8")
    a = o["all_meetings"]
    print(f"as of {o['as_of']}: final {a['final']['final_on_list']} of {a['final']['approved']} (median {a['final']['median_days']} days); "
          f"draft {a['draft']['draft_on_list']} of {a['draft']['approved']} (median {a['draft']['median_days']}), "
          f"{a['draft']['final_on_list']} final; 46th FPS&FA final {o['fpsfa_46th']['final_on_list']} of {o['fpsfa_46th']['final_approved']}")
