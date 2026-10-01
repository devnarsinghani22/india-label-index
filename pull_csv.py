"""Stream the Open Food Facts CSV export (static.openfoodfacts.org), keep only products sold in India.
Decompresses on the fly, so only the India subset touches disk: data/off_india.csv"""
import csv
import gzip
import io
import sys
import time
from pathlib import Path
import requests

csv.field_size_limit(2**31 - 1)
URL = "https://static.openfoodfacts.org/data/en.openfoodfacts.org.products.csv.gz"
OUT = Path(__file__).parent / "data" / "off_india.csv"
H = {"User-Agent": "IndiaLabelIndex/1.0 (dev.narsinghani@gmail.com)"}

t, seen, kept = time.time(), 0, 0
with requests.get(URL, headers=H, stream=True, timeout=120) as r:
    r.raise_for_status()
    r.raw.decode_content = False
    text = io.TextIOWrapper(gzip.GzipFile(fileobj=r.raw), encoding="utf-8", errors="replace", newline="")
    reader = csv.reader(text, delimiter="\t")
    header = next(reader)
    ci = header.index("countries_tags")
    with OUT.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter="\t")
        w.writerow(header)
        for row in reader:
            seen += 1
            if len(row) > ci and "en:india" in row[ci]:
                w.writerow(row)
                kept += 1
            if seen % 200000 == 0:
                print(f"{seen:,} rows read, {kept:,} India, {time.time() - t:.0f}s", flush=True)
print(f"DONE {seen:,} rows read, {kept:,} India -> {OUT}", flush=True)
