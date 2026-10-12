"""Independent recount for sugar_world.py (study 9). Different route to the same numbers: DuckDB SQL does the reading,
barcode dedupe, country split, category and drop-tag tests, value rules and medians; sugar_world.py does all of that
in a Python csv loop. The ingredient matcher (sugar.analyse) and the English test (fats.english_list) are shared, so the
share measures check the selection and counting, not the matcher (the matcher was audited in studies 1 and 5).
Prints every cell where the two disagree and writes out/sugar_world_recount.txt. Run: python -I sugar_world_recount.py"""
import json
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

import duckdb

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from analyse import ADDED_SUGAR_RELEVANT_EXCLUDE, BUCKETS, bucket  # noqa: E402
from fats import english_list  # noqa: E402
from sugar import analyse as sugar_analyse  # noqa: E402
from sugar_world import CATS, ENERGY_SLACK, SALT_CATS  # noqa: E402
from world import C, ENGLISH  # noqa: E402

BABY = sorted(set(BUCKETS[0][1]) | set(BUCKETS[1][1]))
MAIN = json.loads((HERE / "out" / "sugar_world.json").read_text(encoding="utf-8"))


def sql_list(xs):
    return "[" + ", ".join("'" + x.replace("'", "''") + "'" for x in sorted(xs)) + "]"


def main():
    con = duckdb.connect()
    src = str((HERE / "data" / "off_multi.tsv").as_posix())
    con.execute(f"""
        CREATE TABLE raw AS
        SELECT row_number() OVER () AS rn, code, countries_tags, categories_tags, ingredients_text,
               TRY_CAST(sugars_100g AS DOUBLE) AS sugar, TRY_CAST(salt_100g AS DOUBLE) AS salt0,
               TRY_CAST(sodium_100g AS DOUBLE) AS sodium, TRY_CAST("energy-kcal_100g" AS DOUBLE) AS kcal
        FROM read_csv('{src}', delim='\t', quote='"', escape='"', header=true, all_varchar=true, parallel=false, max_line_size=20000000,
                      columns={{'code':'VARCHAR','countries_tags':'VARCHAR','categories_tags':'VARCHAR','ingredients_text':'VARCHAR',
                               'ingredients_tags':'VARCHAR','ingredients_analysis_tags':'VARCHAR','additives_n':'VARCHAR','additives_tags':'VARCHAR',
                               'nova_group':'VARCHAR','labels_tags':'VARCHAR','serving_size':'VARCHAR','serving_quantity':'VARCHAR',
                               'product_quantity':'VARCHAR','energy-kcal_100g':'VARCHAR','fat_100g':'VARCHAR','saturated-fat_100g':'VARCHAR',
                               'sugars_100g':'VARCHAR','added-sugars_100g':'VARCHAR','salt_100g':'VARCHAR','sodium_100g':'VARCHAR',
                               'fiber_100g':'VARCHAR','proteins_100g':'VARCHAR','nutriscore_grade':'VARCHAR','completeness':'VARCHAR',
                               'last_modified_t':'VARCHAR'}})""")
    rows = con.execute("SELECT count(*) FROM raw").fetchone()[0]
    cmap = " ".join(f"WHEN '{t}' THEN '{n}'" for t, n in C.items())
    con.execute(f"""
        CREATE TABLE base AS
        WITH d AS (SELECT * FROM raw QUALIFY row_number() OVER (PARTITION BY code ORDER BY rn) = 1),
        c AS (SELECT *, string_split(coalesce(categories_tags, ''), ',') AS cats,
                        list_filter(list_transform(string_split(coalesce(countries_tags, ''), ','), x -> CASE x {cmap} END), x -> x IS NOT NULL) AS cs
              FROM d)
        SELECT rn, code, cats, cs, ingredients_text, sugar, coalesce(salt0, sodium * 2.5) AS salt, kcal, categories_tags
        FROM c WHERE len(cs) > 0 AND NOT list_has_any(cats, {sql_list(BABY)})""")
    dedup = con.execute("SELECT count(*) FROM base").fetchone()[0]
    out = [f"rows read {rows:,} (main {MAIN['rows_read']:,}); rows after dedupe, country and baby filter {dedup:,}"]
    bad = 0

    def cmp(label, a, b):
        nonlocal bad
        ok = a == b
        bad += not ok
        out.append(f"{'ok ' if ok else 'XX '} {label}: main {a} recount {b}")

    # ---- medians (a) and (c) -------------------------------------------------------------------------------------------
    for g, spec in CATS.items():
        q = f"""
            SELECT c AS country, count(*) AS n,
                   count(*) FILTER (WHERE sugar IS NOT NULL AND sugar BETWEEN 0 AND 100 AND (kcal IS NULL OR sugar * 4 <= kcal + {ENERGY_SLACK})
                                      AND sugar <= {spec['sugar_cap']}) AS k_sugar,
                   list(sugar) FILTER (WHERE sugar IS NOT NULL AND sugar BETWEEN 0 AND 100 AND (kcal IS NULL OR sugar * 4 <= kcal + {ENERGY_SLACK})
                                      AND sugar <= {spec['sugar_cap']}) AS sugars,
                   list(salt) FILTER (WHERE salt IS NOT NULL AND salt BETWEEN 0 AND {spec['salt_cap']}) AS salts
            FROM base, unnest(cs) AS u(c)
            WHERE list_has_any(cats, {sql_list(spec['tags'])}) AND NOT list_has_any(cats, {sql_list(spec['drop'])})
            GROUP BY c"""
        for country, n, k_sugar, sugars, salts in con.execute(q).fetchall():
            m = MAIN["sugar"][g].get(country)
            if m is None:
                cmp(f"sugar {g} {country} (cell missing in main)", None, (k_sugar, n))
                continue
            med = round(st.median(sugars), 1) if sugars else None
            cmp(f"sugar {g} {country} k/n/median", (m["k"], m["n"], m["median"]), (k_sugar, n, med))
            if g in SALT_CATS:
                ms = MAIN["salt"][g].get(country)
                meds = round(st.median(salts), 1) if salts else None
                cmp(f"salt  {g} {country} k/median", (ms["k"], ms["median"]) if ms else None, (len(salts), meds) if salts else None)
    # soft drinks split
    for country, xs in con.execute(f"""
            SELECT c, list(sugar) FROM base, unnest(cs) AS u(c)
            WHERE list_has_any(cats, {sql_list(CATS['soft_drinks']['tags'])}) AND NOT list_has_any(cats, {sql_list(CATS['soft_drinks']['drop'])})
              AND sugar IS NOT NULL AND sugar BETWEEN 0 AND 25 AND (kcal IS NULL OR sugar * 4 <= kcal + {ENERGY_SLACK}) GROUP BY c""").fetchall():
        m = MAIN["soft_drinks_split"][country]
        zero = sum(1 for x in xs if x < 0.5)
        sweet = [x for x in xs if x >= 0.5]
        cmp(f"soft_drinks split {country} zero/k_sweet/median_sweet", (m["zero_sugar"]["k"], m["median_sweetened"]["k"], m["median_sweetened"]["median"]),
            (zero, len(sweet), round(st.median(sweet), 1) if sweet else None))

    # ---- English-list shares (b) and (d): SQL selects, Python matches ------------------------------------------------
    eng = sql_list(ENGLISH)
    acc = defaultdict(lambda: defaultdict(lambda: [0, 0, 0, 0]))     # acc[g][country] -> [n, top3, names2, any]
    cat_sql = ", ".join(f"(list_has_any(cats, {sql_list(s['tags'])}) AND NOT list_has_any(cats, {sql_list(s['drop'])})) AS g_{g}" for g, s in CATS.items())
    cur = con.execute(f"""
        SELECT list_filter(cs, x -> list_contains({eng}, x)) AS ecs, ingredients_text, categories_tags, {cat_sql}
        FROM base WHERE len(list_filter(cs, x -> list_contains({eng}, x))) > 0 AND length(trim(coalesce(ingredients_text, ''))) >= 8""")
    names = list(CATS)
    while True:
        chunk = cur.fetchmany(20000)
        if not chunk:
            break
        for row in chunk:
            ecs, txt, cats_s = row[0], row[1] or "", row[2] or ""
            gs = [names[i] for i, flag in enumerate(row[3:]) if flag]
            staple = bucket(cats_s) in ADDED_SUGAR_RELEVANT_EXCLUDE
            if not gs and staple:
                continue
            if not english_list(txt):
                continue
            a = sugar_analyse(txt)
            hit = (1, a["sugar_in_top3"], a["n_sugar_names"] >= 2, a["n_sugar_names"] >= 1)
            for g in gs + ([] if staple else ["all_foods"]):
                for c in ecs:
                    cell = acc[g][c]
                    for i in range(4):
                        cell[i] += hit[i]
    for g in names + ["all_foods"]:
        for c, (n, t3, n2, anyk) in acc[g].items():
            for key, k in (("sugar_top3", t3), ("names_2plus", n2), ("any_sugar", anyk)):
                m = MAIN[key][g].get(c)
                cmp(f"{key} {g} {c} k/n", (m["k"], m["n"]) if m else None, (k, n))
        for c in MAIN["sugar_top3"][g]:
            if c not in acc[g]:
                cmp(f"sugar_top3 {g} {c} (cell missing in recount)", MAIN["sugar_top3"][g][c]["n"], None)

    out.append(f"\ncells compared {len(out) - 1}, disagreements {bad}")
    text = "\n".join(out)
    (HERE / "out" / "sugar_world_recount.txt").write_text(text + "\n", encoding="utf-8")
    print("\n".join(l for l in out if l.startswith("XX") or l.startswith("rows") or l.startswith("\ncells")))
    print("AGREE" if not bad else f"DISAGREE on {bad} cells")


if __name__ == "__main__":
    main()
