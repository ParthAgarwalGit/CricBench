# CricBench

**A Multilingual Benchmark for Evaluating LLMs in Cricket Analytics**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Data: CC BY 4.0](https://img.shields.io/badge/Data-CC%20BY%204.0-lightgrey.svg)](#license)

CricBench is the first Text-to-SQL benchmark designed specifically for **cricket analytics**. It evaluates the *intrinsic* SQL-generation ability of large language
models on specialized cricket data across four formats and four languages, under two prompting conditions: strict **schema-only** prompting (only the database
schema, no formulas or few-shot examples) and **schema+domain-knowledge (DK)** prompting (the same schema plus a compact block of cricket-specific facts).

- **669** expert-authored base questions → **2,798** evaluation instances
- **4 formats:** Test, ODI, T20I (international) and IPL (franchise)
- **4 languages:** English, and code-mixed **Hindi, Punjabi, Telugu** in their
  native Devanagari, Gurmukhi, and Dravidian scripts
- Every gold query is hand-authored, cross-checked against [ESPNcricinfo](https://www.espncricinfo.com) / [Cricbuzz](https://www.cricbuzz.com), and signed off by a competitive-cricket domain expert

> **Key finding.** No single model dominates across formats, and even the best models show a stark gap between syntactic validity (frontier models exceed 98%
> execution) and semantic correctness (best single-format Data Match Accuracy 33.0%, and even the best schema+domain-knowledge configuration reaches only
> 30.7%) — evidence of a large domain-reasoning gap that a compact domain-knowledge prompt only partially closes.

---

## Repository structure

```
CricBench/
├── data/                # Gold datasets (NL questions + gold SQL), one file per format
│   ├── test.json        #  169 base questions
│   ├── odi.json         #  100 base questions
│   ├── t20i.json        #  200 base questions
│   └── ipl.json         #  200 base questions (+ extra code-mixed HI/TE variants)
├── schemas/             # SQLite DDL
│   ├── schema_odi_wc.sql #  ODI WC schema
│   ├── schema_tests.sql # Tests schema
│   ├── schema_t20i.sql  # T20I schema
│   └── ipl.sql          #  IPL schema
├── evaluation_prompts/  # Schema+domain-knowledge (DK) system prompts, per format
├── scripts/                   # Model clients, evaluation harness, and utilities
│   ├── config.yaml            #  dataset/DB paths, model, timeout, and bootstrap settings
│   ├── run_eval.py            #  main orchestrator: loads instances, calls the model, scores, checkpoints
│   ├── run_dk_local.sh        #  drives a full DK evaluation (all 4 formats) against a local model server
│   ├── prompt_builder.py      #  builds schema-only / schema+DK system prompts (schema extracted live from the DB)
│   ├── cric_loader.py         #  loads CricBench gold queries, expands to language variants
│   ├── bird_loader.py         #  loads the BIRD dev set for the same-model BIRD comparison
│   ├── sql_extractor.py       #  cleans raw model output down to executable SQL
│   ├── db_exec.py             #  executes SQL against the SQLite DB with a timeout
│   ├── dma_eval.py            #  DMA canonicalization and result-set matching
│   ├── scorer.py              #  scoring wrapper around dma_eval.py
│   ├── bootstrap_ci.py        #  cluster-bootstrap 95% confidence intervals
│   ├── classify_sql_features.py #  recomputes the gold-SQL feature statistics (paper Table 2)
│   ├── count_genuine.py       #  counts genuine (non-stub) completions in a checkpoint file
│   ├── report.py              #  builds result summaries/reports
│   ├── claude_client.py       #  Claude API client
│   ├── codex_client.py        #  Codex/GPT API client
│   ├── local_client.py        #  client for local OpenAI-compatible servers (Ollama, vLLM, ...)
├── results/              # Per-model, per-format evaluation files (schema-only and DK)
├── CITATION.cff
└── LICENSE
```

## Dataset

| Format | Base Q | Instances |
|:------:|:------:|:---------:|
| Test   | 169    | 676       |
| ODI    | 100    | 400       |
| T20I † | 200    | 800       |
| IPL    | 200    | 922       |
| **Total** | **669** | **2,798** |

Accounting: 669 base × 4 languages = 2,676 variants, **+122** additional IPL
code-mixed Hindi/Telugu variants = 2,798.

> **† T20I evaluation set.** Model results in `results/` are reported on a **revised
> set of 161 T20I base questions** (of the original 200). The other 39 were excluded
> in review as having no reliable gold answer — e.g. questions needing team-captain
> or dropped-catch information the schema does not contain — or gold SQL exceeding the
> 600 s execution cap. **All models are evaluated on these 161, except GPT-5.4-mini
> (157):** 4 questions hit the 600 s gold-SQL execution timeout during its run and are
> held out for error analysis rather than scored as incorrect. Per-model filtered
> records and EX/DMA summaries are under each `results/<model>/` folder
> (`*t20i_filtered*`). The raw `data/t20i.json` retains all 200 questions.

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
| `difficulty` | Legacy label (Easy/Medium/Hard); not used in evaluation, retained for reference |

> IPL (and some Test/ODI items) include extra code-mixed variants named `question_hindi_1`, `question_hindi_2`, `question_telugu_1`, `question_telugu_2`,
> reflecting alternative code-mixing patterns.

## Databases

The databases are built from publicly available ball-by-ball data from [Cricsheet](https://cricsheet.org).

## Evaluation

`scripts/evaluate.py` reports **Execution Accuracy (EX)** and **Data Match Accuracy (DMA)**. DMA compares returned values (not SQL strings) using a tolerant
canonicalization: multiset (order-insensitive) row comparison, float rounding to two decimals, and NULL/column-name normalization.

## Data sources

Ball-by-ball data: [Cricsheet](https://cricsheet.org). Ground-truth answers were cross-referenced against [ESPNcricinfo](https://www.espncricinfo.com) and
[Cricbuzz](https://www.cricbuzz.com). All data is publicly available sports statistics; no personally identifiable information is included.

## Citation

If you use CricBench, please cite:

```bibtex
@inproceedings{cricbench2026,
  title     = {CricBench: A Multilingual Benchmark for Evaluating LLMs in Cricket Analytics},
  author    = {Agarwal, Parth and Shah, Dhruv and Kommuri, Navya and Singhal, Prisha and Garg, Trizal and Devraj, Vaibhav and Challa, Jagat Sesh and Sinha, Yash                  and Mandal, Murari and Kumar, Dhruv},
  booktitle = {Conference for AI Scientists (CAISc)},
  year      = {2026}
}
```

*The first five authors contributed equally.*

## License

Code is released under the [MIT License](LICENSE). The dataset is released for research use under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/);
please cite the paper above when using it.
