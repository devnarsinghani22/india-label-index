"""Stream the Open Food Facts CSV export and keep a slim column set for a basket of countries, so Indian
packs can be compared with the same categories abroad (India vs UK, US, France, Germany, Australia, Brazil,
Mexico, Chile, South Africa, Indonesia, UAE, Singapore). Brands are NOT kept. Output: data/off_multi.tsv
(one row per product, with its full countries_tags). About 20-40 minutes."""
import csv
import gzip
import io
import time
from pathlib import Path
import requests

csv.field_size_limit(2**31 - 1)
URL = "https://static.openfoodfacts.org/data/en.openfoodfacts.org.products.csv.gz"
OUT = Path(__file__).parent / "data" / "off_multi.tsv"
H = {"User-Agent": "IndiaLabelIndex/1.0 (dev.narsinghani@gmail.com)"}
COUNTRIES = ["en:india", "en:united-kingdom", "en:united-states", "en:france", "en:germany", "en:australia",
             "en:brazil", "en:mexico", "en:chile", "en:south-africa", "en:indonesia", "en:united-arab-emirates",
             "en:singapore", "en:canada", "en:spain", "en:italy"]
KEEP = ["code", "countries_tags", "categories_tags", "ingredients_text", "ingredients_tags", "ingredients_analysis_tags", "additives_n",
        "additives_tags", "nova_group", "labels_tags", "serving_size", "serving_quantity", "product_quantity",
        "energy-kcal_100g", "fat_100g", "saturated-fat_100g", "sugars_100g", "added-sugars_100g", "salt_100g",
        "sodium_100g", "fiber_100g", "proteins_100g", "nutriscore_grade", "completeness", "last_modified_t"]

t, seen, kept = time.time(), 0, 0
with requests.get(URL, headers=H, stream=True, timeout=120) as r:
    r.raise_for_status()
    r.raw.decode_content = False
    text = io.TextIOWrapper(gzip.GzipFile(fileobj=r.raw), encoding="utf-8", errors="replace", newline="")
    reader = csv.reader(text, delimiter="\t")
    header = next(reader)
    idx = [header.index(c) for c in KEEP]
    ci = header.index("countries_tags")
    with OUT.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter="\t")
        w.writerow(KEEP)
        for row in reader:
            seen += 1
            if len(row) > ci and any(c in row[ci] for c in COUNTRIES):
                w.writerow([row[i] if i < len(row) else "" for i in idx])
                kept += 1
            if seen % 200000 == 0:
                print(f"{seen:,} rows read, {kept:,} kept, {time.time() - t:.0f}s", flush=True)
print(f"DONE {seen:,} rows read, {kept:,} kept -> {OUT}", flush=True)
