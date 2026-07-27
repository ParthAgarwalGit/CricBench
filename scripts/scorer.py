"""
Scoring per section 3.7.
Imports dma_eval; never reimplements.
Metrics: EX (execution correctness) and DMA (result set match).
"""

from typing import List, Tuple, Optional
import logging

# Import canonical scorer (section 3.7, section 4, rule 1)
from dma_eval import dma_match

logger = logging.getLogger(__name__)


def score_instance(
    predicted_rows: Optional[List[Tuple]],
    gold_rows: List[Tuple],
) -> dict:
    """
    Score one instance per section 3.7.

    Metrics:
    - EX = predicted SQL executes without error/timeout (returns a result set)
    - DMA = dma_match(gold_rows, pred_rows)
    - Execution failure => EX=0 and DMA=0

    Args:
        predicted_rows: Result from executing predicted SQL, or None if failed
        gold_rows: Gold result rows (obtained by executing gold SQL)

    Returns:
        {
            "ex_correct": 0 or 1,
            "dma_correct": 0 or 1,
        }
    """
    # EX: execution without error/timeout
    ex_correct = 1 if predicted_rows is not None else 0

    # DMA: dma_match (returns False if predicted_rows is None)
    dma_correct = 1 if dma_match(gold_rows, predicted_rows) else 0

    return {
        "ex_correct": ex_correct,
        "dma_correct": dma_correct,
    }


def aggregate_scores(records: List[dict]) -> dict:
    """
    Compute aggregate EX and DMA scores.

    Args:
        records: List of scored records (each with ex_correct, dma_correct)

    Returns:
        {
            "ex_accuracy": float (0-1),
            "dma_accuracy": float (0-1),
            "n_total": int,
        }
    """
    if not records:
        return {"ex_accuracy": 0.0, "dma_accuracy": 0.0, "n_total": 0}

    n = len(records)
    ex_sum = sum(r.get("ex_correct", 0) for r in records)
    dma_sum = sum(r.get("dma_correct", 0) for r in records)

    return {
        "ex_accuracy": ex_sum / n,
        "dma_accuracy": dma_sum / n,
        "n_total": n,
    }
