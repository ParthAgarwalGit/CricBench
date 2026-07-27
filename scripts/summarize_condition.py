#!/usr/bin/env python3
"""
Write a compact bootstrap summary for one benchmark/condition file.

This is the per-condition summary the GPT run uses after each finished pass
condition, without touching the legacy combined report output.
"""

import argparse
import csv
from pathlib import Path

from bootstrap_ci import bootstrap_metric, format_pct, load_results


def _cluster_key(benchmark: str) -> str:
    return "question_id" if benchmark == "bird" else "base_question_id"


def _condition_label(dk: bool) -> str:
    return "schema+dk" if dk else "schema_only"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--records", required=True, help="Path to records JSON or JSONL")
    parser.add_argument("--model", required=True, help="Model slug")
    parser.add_argument(
        "--benchmark",
        required=True,
        choices=["bird", "cricbench", "odi", "t20i", "test"],
        help="Benchmark name",
    )
    parser.add_argument("--dk", action="store_true", help="Mark the DK condition")
    parser.add_argument(
        "--out",
        default=None,
        help="Optional output CSV path. Defaults to outputs/results/<model>_<benchmark>[_dk]_results.csv",
    )
    parser.add_argument("--n-resamples", type=int, default=10000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--alpha", type=float, default=0.05)
    args = parser.parse_args()

    records = load_results(args.records)
    if not records:
        raise SystemExit(f"No records found in {args.records}")

    cluster_key = _cluster_key(args.benchmark)
    ci = bootstrap_metric(
        records,
        metric_key="dma_correct",
        cluster_key=cluster_key,
        n_resamples=args.n_resamples,
        seed=args.seed,
        alpha=args.alpha,
    )

    suffix = "_dk" if args.dk else ""
    out_path = Path(args.out) if args.out else Path(
        f"outputs/results/{args.model}_{args.benchmark}{suffix}_results.csv"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with open(out_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "Model",
            "Benchmark",
            "Condition",
            "Metric",
            "Point Estimate",
            "CI Low",
            "CI High",
            "N Items",
            "N Clusters",
            "N Resamples",
            "Seed",
            "Alpha",
        ])
        writer.writerow([
            args.model,
            args.benchmark,
            _condition_label(args.dk),
            "dma_correct",
            f"{ci['point_estimate']:.4f}",
            f"{ci['ci_low']:.4f}",
            f"{ci['ci_high']:.4f}",
            ci["n_items"],
            ci["n_clusters"],
            ci["n_resamples"],
            ci["seed"],
            args.alpha,
        ])

    print(f"{args.model} {args.benchmark} {_condition_label(args.dk)}")
    print(f"  DMA: {format_pct(ci['point_estimate'])} [{format_pct(ci['ci_low'])}, {format_pct(ci['ci_high'])}]")
    print(f"  N items={ci['n_items']} clusters={ci['n_clusters']}")
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
