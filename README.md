# CricBench

**A Multilingual Benchmark for Evaluating LLMs in Cricket Analytics**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Data: CC BY 4.0](https://img.shields.io/badge/Data-CC%20BY%204.0-lightgrey.svg)](#license)

CricBench is the first Text-to-SQL benchmark designed specifically for **cricket
analytics**. It evaluates the *intrinsic* SQL-generation ability of large language
models on specialized cricket data across four formats and four languages, using
strict **schema-only prompting** (only the database schema, no formulas or
few-shot examples).

- **633** expert-authored base questions → **2,653** evaluation instances
- **4 formats:** Test, ODI, T20I (international) and IPL (franchise)
- **4 languages:** English, and code-mixed **Hindi, Punjabi, Telugu** in their
  native Devanagari, Gurmukhi, and Telugu scripts
- Every gold query is hand-authored, cross-checked against
  [ESPNcricinfo](https://www.espncricinfo.com) / [Cricbuzz](https://www.cricbuzz.com),
  and signed off by a competitive-cricket domain expert

> **Key finding.** No single model dominates across formats, and even the best
> models show a stark gap between syntactic validity (>98% execution) and semantic
> correctness (best full-set Data Match Accuracy 23.8%; best stratified-subset
> 33.0%) — evidence of a large domain-reasoning gap.

---

## Repository structure

```
CricBench/
├── data/                # Gold datasets (NL questions + gold SQL), one file per format
│   ├── test.json        #  169 base questions
│   ├── odi.json         #   64 base questions
│   ├── t20i.json        #  200 base questions
│   └── ipl.json         #  200 base questions (+ extra code-mixed HI/TE variants)
├── schemas/             # SQLite DDL
│   ├── international.sql #  shared Test / ODI / T20I schema (teams = nations)
│   └── ipl.sql          #  IPL schema (teams = franchises)
├── scripts/             # Ingestion, evaluation, and utilities
│   ├── ingest.py        #  build a SQLite DB from Cricsheet ball-by-ball data
│   ├── evaluate.py      #  compute Execution Accuracy (EX) and Data Match Accuracy (DMA)
│   ├── verify.py        #  dataset self-verification
│   ├── convert_dataset.py
│   ├── make_subset.py   #  build a stratified subset (the "CricBench-Sub" split)
│   └── sync_deepseek_results.py
├── results/             # Example raw model outputs (see results/README.md)
├── extras/              # Exploratory data NOT part of the paper benchmark (WPL, World Cup, agent variant)
├── CITATION.cff
└── LICENSE
```

## Dataset

Complexity is characterized by an **objective, reproducible** measure — the number
of joins in the gold SQL — rather than subjective difficulty labels.

| Format | Base Q | 0 joins | 1 join | 2 joins | ≥3 joins | Instances |
|:------:|:------:|:-------:|:------:|:-------:|:--------:|:---------:|
| Test   | 169    | 52      | 26     | 57      | 34       | 676       |
| ODI    | 64     | 10      | 17     | 31      | 6        | 256       |
| T20I   | 200    | 117     | 41     | 15      | 27       | 799       |
| IPL    | 200    | 28      | 79     | 73      | 20       | 922       |
| **Total** | **633** | 207 | 163 | 176 | 87 | **2,653** |

Accounting: 633 base × 4 languages = 2,532 variants, **+122** additional IPL
code-mixed Hindi/Telugu variants, **−1** removed T20I Telugu instance = **2,653**.

### JSON format

Each record in a `data/*.json` file contains:

| Field | Description |
|-------|-------------|
| `db_id` | Target database (`tests`, `wc_db` for ODI, `t20i.db`, `ipl_db`) |
| `question` | Canonical (English) question |
| `question_english`, `question_hindi`, `question_punjabi`, `question_telugu` | Language variants (native script, code-mixed) |
| `query` | Gold SQL |
| `answer` | Gold result rows |
| `column_names` | Output column labels |
| `difficulty` | Legacy label (Easy/Medium/Hard); superseded by join count — retained for reference |

> IPL (and some Test/ODI items) include extra code-mixed variants named
> `question_hindi_1`, `question_hindi_2`, `question_telugu_1`, `question_telugu_2`,
> reflecting alternative code-mixing patterns.

## Databases

The databases are built from publicly available ball-by-ball data from
[Cricsheet](https://cricsheet.org). Create a SQLite database from the schema and
Cricsheet JSON with:

```bash
python scripts/ingest.py   # see the script header for source/output paths
```

International formats (Test / ODI / T20I) share `schemas/international.sql`; IPL
uses `schemas/ipl.sql`.

## Evaluation

`scripts/evaluate.py` reports **Execution Accuracy (EX)** and **Data Match
Accuracy (DMA)**. DMA compares returned values (not SQL strings) using a tolerant
canonicalization: multiset (order-insensitive) row comparison, float rounding to
two decimals, and NULL/column-name normalization.

```bash
# Self-check the gold queries against the stored answers:
python scripts/evaluate.py --db international.db --queries data/test.json

# Score a model's predictions (SQL stored under, e.g., "generated_sql"):
python scripts/evaluate.py --db ipl.db --queries model_outputs.json --pred-key generated_sql
```

## Data sources

Ball-by-ball data: [Cricsheet](https://cricsheet.org). Ground-truth answers were
cross-referenced against [ESPNcricinfo](https://www.espncricinfo.com) and
[Cricbuzz](https://www.cricbuzz.com). All data is publicly available sports
statistics; no personally identifiable information is included.

## Citation

If you use CricBench, please cite:

```bibtex
@inproceedings{cricbench2026,
  title     = {CricBench: A Multilingual Benchmark for Evaluating LLMs in Cricket Analytics},
  author    = {Agarwal, Parth and Shah, Dhruv and Kommuri, Navya and Singhal, Prisha and
               Garg, Trizal and Devraj, Vaibhav and Challa, Jagat Sesh and Sinha, Yash and
               Mandal, Murari and Kumar, Dhruv},
  booktitle = {Conference for AI Scientists (CAISc)},
  year      = {2026}
}
```

*The first five authors contributed equally.*

## License

Code is released under the [MIT License](LICENSE). The dataset is released for
research use under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/);
please cite the paper above when using it.
