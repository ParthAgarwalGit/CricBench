"""
Computes the SQL feature statistics reported in Table 2 of the CricBench
paper.

For each of the 669 base questions, the query is classified (non-exclusively)
into five feature buckets by regex over the raw SQL text:

    - Aggregation      : contains GROUP BY
    - Top-N            : contains both ORDER BY and LIMIT
    - Subquery / CTE   : starts with WITH, or contains a parenthesized SELECT
    - HAVING filter    : contains HAVING
    - Window function  : contains OVER(...) or RANK/DENSE_RANK/ROW_NUMBER/
                          NTILE/LAG/LEAD

Categories are non-exclusive, so percentages do not sum to 100%.
"""

import json
import re
import sys
from collections import OrderedDict

FEATURE_PATTERNS = OrderedDict([
    ("Aggregation (GROUP BY)",        [r"\bGROUP\s+BY\b"]),
    ("Top-N (ORDER BY + LIMIT)",      [r"\bORDER\s+BY\b", r"\bLIMIT\b"]),  # both must match
    ("Subquery / CTE",                [r"^\s*WITH\b", r"\(\s*SELECT\b"]),  # either matches
    ("HAVING filter",                 [r"\bHAVING\b"]),
    ("Window function (RANK, etc.)",  [r"\bOVER\s*\(",
                                        r"\b(RANK|DENSE_RANK|ROW_NUMBER|NTILE|LAG|LEAD)\s*\("]),
])

# Features where ALL listed patterns must match (conjunctive); everything
# else is disjunctive.
CONJUNCTIVE_FEATURES = {"Top-N (ORDER BY + LIMIT)"}


def has_feature(query: str, patterns: list[str], conjunctive: bool) -> bool:
    hits = [re.search(p, query, re.IGNORECASE) is not None for p in patterns]
    return all(hits) if conjunctive else any(hits)


def load_queries(paths: list[str]) -> list[tuple[str, str]]:
    """Returns a list of (format_name, gold_sql) pairs, one per base question."""
    out = []
    for path in paths:
        fmt = path.rsplit("/", 1)[-1].split(".")[0]
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        for row in data:
            q = row.get("query") or row.get("sql") or ""
            out.append((fmt, q))
    return out


def main(paths: list[str]) -> None:
    records = load_queries(paths)
    n = len(records)
    if n == 0:
        raise SystemExit("No queries loaded — check input paths.")

    missing = sum(1 for _, q in records if not q)
    if missing:
        print(f"WARNING: {missing} record(s) had no 'query' field.", file=sys.stderr)

    print(f"Loaded {n} base queries from {len(paths)} file(s).\n")

    counts = OrderedDict((name, 0) for name in FEATURE_PATTERNS)
    for _, query in records:
        if not query:
            continue
        for name, patterns in FEATURE_PATTERNS.items():
            if has_feature(query, patterns, conjunctive=name in CONJUNCTIVE_FEATURES):
                counts[name] += 1

    print(f"{'SQL feature':32s}{'Count':>8s}{'% of ' + str(n):>12s}")
    for name, c in counts.items():
        print(f"{name:32s}{c:8d}{c / n * 100:11.1f}%")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    main(sys.argv[1:])