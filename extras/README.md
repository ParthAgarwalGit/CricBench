# extras/

Exploratory data that is **NOT part of the CricBench benchmark** evaluated in the
paper. Provided for completeness and future work; not covered by the paper's
statistics, protocol, or results.

- `wpl.json` — a small set of Women's Premier League (WPL) queries.
- `worldcup.json` / `worldcup_notes.txt` — a small set of ODI World Cup queries and raw notes.
- `ipl_cricagent.json` — an enriched, agent-style variant of the IPL questions with
  additional fields (`evidence`, `logic_tags`, `Chain of Thought`, `expected_result`).
  Not used in the schema-only evaluation reported in the paper.

These files are exploratory and have not undergone the full validation protocol
applied to the benchmark in `data/`.
