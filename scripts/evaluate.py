"""
CricBench evaluation harness.

Executes SQL against a CricBench SQLite database and reports two metrics:

  * Execution Accuracy (EX)  -- fraction of queries that run without error.
  * Data Match Accuracy (DMA) -- fraction whose result set matches the gold result.

DMA compares *returned values* (not SQL strings), using the tolerant
canonicalization described in the paper (Appendix D):
  - rows compared as a multiset (order-insensitive) by default;
  - floats rounded to 2 decimals;
  - NULLs normalized; column names ignored; strings stripped/lower-cased.

By default the script executes the gold `query` field and checks it against the
stored `answer` field (a self-consistency check on the benchmark). To score a
model instead, pass --pred-key to point at a field holding the model's SQL
(e.g. "generated_sql"); that SQL is executed and its result compared to the gold.

Usage:
  python scripts/evaluate.py --db path/to/international.db --queries data/test.json
  python scripts/evaluate.py --db ipl.db --queries results/t20i_deepseek_r1.json \
         --pred-key generated_sql
"""

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any, List, Optional, Tuple


def _canon_value(v: Any) -> Any:
    """Canonicalize a single cell value for tolerant comparison."""
    if v is None:
        return "__NULL__"
    if isinstance(v, float):
        return round(v, 2)
    if isinstance(v, str):
        return v.strip().lower()
    if isinstance(v, (list, tuple)):
        return tuple(_canon_value(x) for x in v)
    return v


def canon_rows(rows: Any, unordered: bool = True) -> Tuple:
    """Canonicalize a set of result rows into a comparable tuple (multiset by default)."""
    if rows is None:
        return tuple()
    if not isinstance(rows, (list, tuple)):
        rows = [rows]
    out = []
    for r in rows:
        if not isinstance(r, (list, tuple)):
            r = (r,)
        out.append(tuple(_canon_value(x) for x in r))
    if unordered:
        out.sort(key=lambda t: str(t))
    return tuple(out)


def dma_match(gold_rows: Any, pred_rows: Optional[Any], unordered: bool = True) -> bool:
    if pred_rows is None:  # execution error / timeout
        return False
    return canon_rows(gold_rows, unordered) == canon_rows(pred_rows, unordered)


def execute(conn: sqlite3.Connection, sql: str) -> Tuple[bool, Optional[List[Tuple]], str]:
    try:
        cur = conn.cursor()
        cur.execute(sql)
        return True, [tuple(row) for row in cur.fetchall()], ""
    except Exception as e:  # noqa: BLE001 - any SQL/runtime error is an execution failure
        return False, None, str(e)


def main() -> None:
    ap = argparse.ArgumentParser(description="CricBench SQL evaluation (EX + DMA).")
    ap.add_argument("--db", required=True, help="Path to the SQLite database.")
    ap.add_argument("--queries", required=True, help="Path to a CricBench JSON file.")
    ap.add_argument("--gold-key", default="query", help="Field holding the gold SQL.")
    ap.add_argument("--answer-key", default="answer", help="Field holding the gold answer rows.")
    ap.add_argument("--pred-key", default=None,
                    help="If set, execute this field's SQL (model prediction) instead of the gold SQL "
                         "and compare against the gold answer.")
    ap.add_argument("--ordered", action="store_true",
                    help="Use order-sensitive (strict) comparison instead of the default multiset match.")
    ap.add_argument("--quiet", action="store_true", help="Suppress per-query logging.")
    args = ap.parse_args()

    unordered = not args.ordered
    db_path, q_path = Path(args.db), Path(args.queries)
    if not db_path.exists():
        raise SystemExit(f"ERROR: database not found: {db_path}")
    if not q_path.exists():
        raise SystemExit(f"ERROR: queries file not found: {q_path}")

    with open(q_path, encoding="utf-8") as f:
        rows = json.load(f)
    if not isinstance(rows, list):
        raise SystemExit("ERROR: queries file must contain a JSON list.")

    conn = sqlite3.connect(str(db_path))
    total = ex_ok = dma_ok = 0
    for i, obj in enumerate(rows, 1):
        if not isinstance(obj, dict):
            continue
        gold_sql = obj.get(args.gold_key)
        gold_ans = obj.get(args.answer_key)
        sql_to_run = obj.get(args.pred_key) if args.pred_key else gold_sql
        if not sql_to_run:
            continue
        total += 1

        # Reference answer: prefer the stored gold answer; else execute the gold SQL.
        if gold_ans is not None:
            gold_rows = gold_ans
        else:
            ok_g, gold_rows, _ = execute(conn, gold_sql) if gold_sql else (False, None, "")

        ok, pred_rows, err = execute(conn, sql_to_run)
        if ok:
            ex_ok += 1
        matched = ok and dma_match(gold_rows, pred_rows, unordered)
        if matched:
            dma_ok += 1
        if not args.quiet:
            tag = "MATCH" if matched else ("EXEC-ONLY" if ok else "FAIL")
            q = (obj.get("question") or "")[:70]
            print(f"[{i}] {tag} | {q}")
            if not ok:
                print(f"      error: {err}")

    conn.close()
    print("\n" + "=" * 60)
    print(f"Total queries : {total}")
    print(f"Execution (EX): {ex_ok}/{total} = {100*ex_ok/total:.1f}%" if total else "no queries")
    print(f"Data Match(DMA): {dma_ok}/{total} = {100*dma_ok/total:.1f}%" if total else "")
    print("=" * 60)


if __name__ == "__main__":
    main()
