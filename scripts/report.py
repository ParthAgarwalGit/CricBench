"""
Report generation.
Bootstrap CIs (95%, 10k resamples, seed 42), gap analysis, CSV + LaTeX output.
"""

import csv
import json
import logging
from typing import List, Dict, Any
from pathlib import Path

# Import canonical bootstrap utilities
from bootstrap_ci import (
    bootstrap_metric,
    bootstrap_gap,
    format_pct,
    load_results,
)

logger = logging.getLogger(__name__)


def generate_report(
    cricbench_records_path: str,
    bird_records_path: str,
    output_dir: str,
    model_name: str = "claude-haiku-4-5",
) -> None:
    """
    Generate full report: per-model CIs, gap CI, CSV + LaTeX tables.

    - 95% clustered bootstrap CIs (10k resamples, seed 42)
    - CricBench clustered by base_question_id
    - BIRD by question_id (singletons, but still pass key explicitly)
    - Gap = BIRD DMA - CricBench DMA with excludes_zero flag
    - Report aggregates only (per model × per benchmark, no breakdowns)

    Args:
        cricbench_records_path: Path to CricBench scored records (JSON/JSONL)
        bird_records_path: Path to BIRD scored records (JSON/JSONL)
        output_dir: Output directory for results
        model_name: Model identifier for output tables
    """
    output_dir_path = Path(output_dir)
    output_dir_path.mkdir(parents=True, exist_ok=True)

    # Load records
    cric_records = load_results(cricbench_records_path)
    bird_records = load_results(bird_records_path)

    logger.info(f"Loaded {len(cric_records)} CricBench records")
    logger.info(f"Loaded {len(bird_records)} BIRD records")

    # Bootstrap CIs for each benchmark
    cric_ci = bootstrap_metric(
        cric_records,
        metric_key="dma_correct",
        cluster_key="base_question_id",
        n_resamples=10000,
        seed=42,
        alpha=0.05,
    )

    bird_ci = bootstrap_metric(
        bird_records,
        metric_key="dma_correct",
        cluster_key="question_id",
        n_resamples=10000,
        seed=42,
        alpha=0.05,
    )

    # Gap CI: BIRD DMA - CricBench DMA
    gap_ci = bootstrap_gap(
        bird_records,
        cric_records,
        metric_key="dma_correct",
        cluster_key_a="question_id",
        cluster_key_b="base_question_id",
        n_resamples=10000,
        seed=42,
        alpha=0.05,
    )

    # Log results
    logger.info(f"CricBench DMA: {format_pct(cric_ci['point_estimate'])} "
                f"[{format_pct(cric_ci['ci_low'])}, {format_pct(cric_ci['ci_high'])}]")
    logger.info(f"BIRD DMA: {format_pct(bird_ci['point_estimate'])} "
                f"[{format_pct(bird_ci['ci_low'])}, {format_pct(bird_ci['ci_high'])}]")
    logger.info(f"Gap (BIRD - CricBench): {format_pct(gap_ci['point_estimate'])} "
                f"[{format_pct(gap_ci['ci_low'])}, {format_pct(gap_ci['ci_high'])}] "
                f"(excludes_zero={gap_ci['excludes_zero']})")

    # Write CSV results
    csv_path = output_dir_path / "results.csv"
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "Model",
                "Benchmark",
                "Metric",
                "Point Estimate",
                "CI Low",
                "CI High",
                "N Items",
                "N Clusters",
                "N Resamples",
            ],
        )
        writer.writeheader()

        for bench, ci_result in [("CricBench", cric_ci), ("BIRD", bird_ci)]:
            for metric in ["dma_correct"]:  # Only DMA per spec
                writer.writerow(
                    {
                        "Model": model_name,
                        "Benchmark": bench,
                        "Metric": metric,
                        "Point Estimate": f"{ci_result['point_estimate']:.4f}",
                        "CI Low": f"{ci_result['ci_low']:.4f}",
                        "CI High": f"{ci_result['ci_high']:.4f}",
                        "N Items": ci_result["n_items"],
                        "N Clusters": ci_result["n_clusters"],
                        "N Resamples": ci_result["n_resamples"],
                    }
                )

    logger.info(f"CSV results written to {csv_path}")

    # Write gap CSV
    gap_csv_path = output_dir_path / "gaps.csv"
    with open(gap_csv_path, "w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "Model",
                "Gap (BIRD - CricBench)",
                "CI Low",
                "CI High",
                "Excludes Zero",
                "N Resamples",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "Model": model_name,
                "Gap (BIRD - CricBench)": f"{gap_ci['point_estimate']:.4f}",
                "CI Low": f"{gap_ci['ci_low']:.4f}",
                "CI High": f"{gap_ci['ci_high']:.4f}",
                "Excludes Zero": gap_ci["excludes_zero"],
                "N Resamples": gap_ci["n_resamples"],
            }
        )

    logger.info(f"Gap results written to {gap_csv_path}")

    # Write LaTeX tables
    tex_path = output_dir_path / "results.tex"
    with open(tex_path, "w") as f:
        f.write(_latex_results_table(model_name, cric_ci, bird_ci, gap_ci))

    logger.info(f"LaTeX table written to {tex_path}")


def _latex_results_table(
    model_name: str,
    cric_ci: dict,
    bird_ci: dict,
    gap_ci: dict,
) -> str:
    """Generate LaTeX table for results."""
    latex = r"""\documentclass{article}
\usepackage{booktabs}
\begin{document}

\begin{table}[h]
\centering
\caption{CricBench + BIRD Evaluation: """ + model_name + r"""}
\begin{tabular}{lcccc}
\toprule
Benchmark & Point Estimate & 95\% CI Low & 95\% CI High & N Clusters \\
\midrule
"""

    latex += f"CricBench & {cric_ci['point_estimate']:.4f} & {cric_ci['ci_low']:.4f} & {cric_ci['ci_high']:.4f} & {cric_ci['n_clusters']} \\\\\n"
    latex += f"BIRD & {bird_ci['point_estimate']:.4f} & {bird_ci['ci_low']:.4f} & {bird_ci['ci_high']:.4f} & {bird_ci['n_clusters']} \\\\\n"

    latex += r"""\bottomrule
\end{tabular}
\end{table}

\begin{table}[h]
\centering
\caption{Domain Gap (BIRD DMA - CricBench DMA)}
\begin{tabular}{lccc}
\toprule
Gap & 95\% CI Low & 95\% CI High & Excludes Zero \\
\midrule
"""

    latex += f"{gap_ci['point_estimate']:.4f} & {gap_ci['ci_low']:.4f} & {gap_ci['ci_high']:.4f} & {gap_ci['excludes_zero']} \\\\\n"

    latex += r"""\bottomrule
\end{tabular}
\end{table}

\end{document}
"""
    return latex
