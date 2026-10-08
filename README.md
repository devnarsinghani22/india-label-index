# India Label Index 2026

What 3,798 Indian food labels say about sugar and salt. By [Dev Narsinghani](https://devnarsinghani22.github.io/).

Full write-up with charts: **https://devnarsinghani22.github.io/india-label-index/**

## Findings

From 3,798 Indian packaged foods with an ingredient list (plain staples like atta, rice, dal, oil, spices, tea and coffee left out):

- **6 in 10** list an added sugar (60%).
- **4 in 10** have a sugar in the first 3 ingredients (42%).
- **2 in 10** list sugar under 2 or more names (19%). For biscuits it is **7 in 10**.
- **2 in 3** are ultra-processed (NOVA group 4, 68%).
- Instant noodles and pasta have a median of **2.5 g of salt in 100 g**, half of the 5 g a day WHO sets for adults.

### Warning labels

- **FSSAI's proposed limits** (ICMR-NIN 2024, as cited to the Supreme Court, 28 Aug 2026), 665 foods with full nutrition: **71%** would carry a warning under FSSAI's current plan (any 1 of added sugar, added fat, salt high; affidavit of 23 Sep 2026), against **41%** under the 2-or-more plan it dropped. Soft drinks: 69% are high in added sugar, but only 3% would have been warned under the dropped plan. [Page](https://devnarsinghani22.github.io/india-label-index/fssai-warning-labels/), `fssai.py`, [`out/fssai.json`](out/fssai.json).
- **Chile's 2019 limits**, 687 foods: 69% would carry at least one warning. [Page](https://devnarsinghani22.github.io/india-label-index/warning-labels/), `warnings.py`, [`out/warnings.json`](out/warnings.json).

### Which fat is in the pack (6 Oct 2026)

- Of **2,015** Indian packaged foods whose ingredient list names a fat or oil (staples left out), **52%** name palm oil (palm oil, palm fruit oil, palmolein, palm kernel or palm fat). Instant noodles **90%** (109 lists), biscuits **82%** (354), chips **77%** (164), namkeen **66%** (99). **15%** list a hydrogenated, interesterified or shortening fat (chocolate 36%, biscuits 29%). **7%** say only "vegetable oil" and never name the plant. [Page](https://devnarsinghani22.github.io/india-label-index/palm-oil/), `fats.py`, [`out/fats.json`](out/fats.json).
- Updated 8 Oct 2026 (first published as 1,917 lists, 51%): `english_list()` replaces `str.isascii()`, so a stray accent or symbol, or a second language printed next to the English list, no longer drops a list; "palm fruit oil" counts as palm; "sunflower, safflower and/or canola oil" names all three oils; soy/soy bean/soya bean merge into soybean. Every share moved by 2 points or less. `fats.json` now carries the counts behind each share, and pages round once, from the counts.

### India vs the world (8 Oct 2026)

The same foods in Open Food Facts, India against 15 other countries (one download, 6 Oct 2026; `world.py`, [`out/world.json`](out/world.json), [`out/world_table.csv`](out/world_table.csv), which holds every number on the page with its count). [Page](https://devnarsinghani22.github.io/india-label-index/india-vs-world/).

- **Chips (crisps):** of 159 Indian chips lists in English that name a fat or oil, **78%** (124) name palm oil. UK **3.3%** (46 of 1,380), US **7.6%** (211 of 2,779), Canada 6.4% (23 of 359), Australia 6.7% (15 of 225): about **23 times** the UK rate. Open Food Facts' own palm-oil tag (any language) agrees: India 83% (113 of 136) vs 3.1% to 21% in 8 other countries. The 159 lists come from about 58 brands (77 brand tags, spellings of one name merged); the biggest is 16% of them (25 of 159), and without it the share is still 78% (104 of 134).
- **Saturated fat in chips:** median **13.8 g** per 100 g in India (58 packs) vs **2.4 g** in the UK (1,773) and 3.6 g in the US (1,023). Only 8 Indian packs that do not name palm have a value, too few to test whether the oil explains the gap.
- **Instant noodles only** (no dry pasta): palm oil tag in **95%** of Indian packs (81 of 85) vs 67% UK (137 of 203), 76% US (146 of 193), 78% France (591 of 760), 77% Germany (277 of 362).
- **5 or more additives, same food:** biscuits India **45%** (158 of 350), the most of 12 countries with enough data (UK 21% of 1,612, US 33% of 11,231); instant noodles India 82% (80 of 97), UK 47% (106 of 227), US 64% (146 of 229).
- **5 or more additives, all foods** (every pack with an ingredient list and an additive count, baby food and supplements left out): India **19%** (958 of 5,159) vs UK 13% (61,585), France 10% (363,226), Germany 8.9% (123,174), US 18% (444,380).
- Other countries are shown only with at least 100 products; India uses the Index rules (50 lists for a share, 30 values for a median).
- Corrected 8 Oct 2026, the day it went up: the all-foods additive figure first covered only analyse.py's 22 food groups (23%, 3,421 packs); the English-list, palm fruit oil and oil-run fixes above apply here too; INS numbers written "INS-330", "INS:330" or "INS.330" are now found (1,228 Indian lists, was 1,197); shares are stored with their counts so pages round once (the UK noodles figure is 67%, not 68%; Indian noodles with 5+ additives 82%, not 83%).

Per-category numbers: [`out/category_table.csv`](out/category_table.csv). Everything: [`out/results.json`](out/results.json).

## Data

[Open Food Facts](https://world.openfoodfacts.org/), every product tagged as sold in India (21,189 products, read 1 October 2026). 4,656 have an English ingredient list. Baby food and supplements are left out. Open Food Facts is filled in by volunteers, so this is not a random sample of every pack in India.

The raw product data is not stored here. `pull_csv.py` downloads it again from Open Food Facts.

## Method

- Sugar names are found with the rules of the [Label Checker](https://devnarsinghani22.github.io/tools/label-checker/) (`aliases.json`, `sugar.py`), based on FSSAI and WHO definitions. Fruit juice concentrate counts as a sugar, as WHO counts it. Fibres such as FOS, flavour names and "no added sugar" claim text are not counted.
- "First 3 ingredients" = the first 3 top-level items, split on commas and semicolons outside brackets. A sugar inside a bracket belongs to the item before it.
- Salt = the salt value, or sodium × 2.5. Medians per category; a category needs 50 ingredient lists (charts) or 30 values (medians) to be shown on the page.
- `audit.py` prints every matched sugar phrase with its context. Every phrase was checked by hand and the rules were fixed where they were wrong.
- Results are category-level. Nothing here rates a brand or product.

## Reproduce

```
pip install requests regex
python pull_csv.py     # streams the Open Food Facts CSV export, keeps India (about 20 minutes)
python sugar.py        # matcher self-test
python analyse.py      # writes out/results.json and out/category_table.csv
python audit.py        # every matched sugar phrase with context
python warnings.py     # Chile-rule warning labels -> out/warnings.json
python fssai.py        # FSSAI proposed limits, Phase I vs II -> out/fssai.json
python fats.py         # which fat the list names: palm, other plant oil, dairy, unnamed -> out/fats.json (self-test first)
python -I pull_multi.py   # slim multi-country extract for cross-country comparisons (data/off_multi.tsv, 20-40 min)
python world.py        # India vs the world: chips (crisps), instant noodles, additives -> out/world.json, out/world_table.csv (self-test first)
```

Run the two `pull_*` scripts with `python -I`: this folder has a `warnings.py`, which shadows the standard-library module that `requests` needs.

## Licence

Code: MIT. Data: derived from Open Food Facts under the [Open Database License (ODbL)](https://opendatacommons.org/licenses/odbl/1-0/). Reuse with credit to Open Food Facts and this project.

## Cite

Narsinghani, D. (2026). India Label Index 2026: What 3,798 Indian food labels say about sugar and salt. https://devnarsinghani22.github.io/india-label-index/. Data from Open Food Facts (ODbL).
