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
```

## Licence

Code: MIT. Data: derived from Open Food Facts under the [Open Database License (ODbL)](https://opendatacommons.org/licenses/odbl/1-0/). Reuse with credit to Open Food Facts and this project.

## Cite

Narsinghani, D. (2026). India Label Index 2026: What 3,798 Indian food labels say about sugar and salt. https://devnarsinghani22.github.io/india-label-index/. Data from Open Food Facts (ODbL).
