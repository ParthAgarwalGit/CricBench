"""
BIRD data loader per section 3.4.
Stratified random subset (N=400, seed=42, stratified by db_id).
"""

import json
import logging
from typing import List, Dict, Any, Set
import numpy as np

logger = logging.getLogger(__name__)


def load_bird_full(dev_path: str, bird_databases_dir: str) -> List[Dict[str, Any]]:
    """
    Load full BIRD dev.json without filtering.

    Args:
        dev_path: Path to bird/dev.json
        bird_databases_dir: Path to bird/dev_databases/

    Returns:
        List of questions with gold SQL
    """
    with open(dev_path, "r", encoding="utf-8") as f:
        questions = json.load(f)

    if not isinstance(questions, list):
        raise ValueError(f"Expected list, got {type(questions)}")

    logger.info(f"Loaded {len(questions)} BIRD questions from {dev_path}")
    return questions


def stratified_sample_bird(
    questions: List[Dict[str, Any]],
    n_samples: int = 400,
    stratify_by: str = "db_id",
    seed: int = 42,
) -> tuple:
    """
    Stratified random sample from BIRD questions.

    Per section 3.4:
    - N=400, seed=42, stratified by db_id
    - Save manifest (question_ids) to JSON
    - Returns same subset for all models (BIRD consistency)

    Args:
        questions: List of BIRD questions
        n_samples: Number of samples (default 400)
        stratify_by: Column to stratify by (default "db_id")
        seed: Random seed

    Returns:
        (sampled_questions, question_ids_manifest)
    """
    rng = np.random.default_rng(seed)

    # Group by stratification key
    groups = {}
    for idx, q in enumerate(questions):
        key = q.get(stratify_by, "unknown")
        if key not in groups:
            groups[key] = []
        groups[key].append(idx)

    logger.info(
        f"BIRD: {len(groups)} unique values for '{stratify_by}', "
        f"{len(questions)} total questions"
    )

    # Proportional allocation: sample from each stratum proportionally
    sampled_indices = []
    for key, indices in groups.items():
        # Proportion for this stratum
        stratum_n = len(indices)
        proportion = stratum_n / len(questions)
        target_n = max(1, int(proportion * n_samples))

        # Sample without replacement from this stratum
        sampled = rng.choice(indices, size=min(target_n, stratum_n), replace=False)
        sampled_indices.extend(sampled)

    # If we have fewer than n_samples due to rounding, sample additional questions
    if len(sampled_indices) < n_samples:
        remaining_n = n_samples - len(sampled_indices)
        all_indices = set(range(len(questions)))
        available = list(all_indices - set(sampled_indices))
        if available:
            extra = rng.choice(available, size=min(remaining_n, len(available)), replace=False)
            sampled_indices.extend(extra)

    # Shuffle for consistency
    sampled_indices = sorted(sampled_indices[:n_samples])

    sampled_questions = [questions[i] for i in sampled_indices]

    # Extract question_ids for manifest
    question_ids = [q.get("question_id", i) for i, q in enumerate(sampled_questions)]

    logger.info(
        f"Sampled {len(sampled_questions)} questions (stratified by {stratify_by}, seed={seed})"
    )

    return sampled_questions, question_ids


def prepare_bird_instances(
    questions: List[Dict[str, Any]], bird_databases_dir: str
) -> List[Dict[str, Any]]:
    """
    Convert BIRD questions to evaluation instances.

    Args:
        questions: List of BIRD questions
        bird_databases_dir: Path to bird/dev_databases/

    Returns:
        List of instances with:
            {
                "question_id": int,
                "question": str,
                "gold_sql": str,
                "db_id": str,
                "db_path": str,
            }
    """
    instances = []

    for q in questions:
        question_id = q.get("question_id")
        question_text = q.get("question")
        gold_sql = q.get("SQL")  # BIRD uses "SQL" key per spec 3.4
        db_id = q.get("db_id")

        if not all([question_id, question_text, gold_sql, db_id]):
            logger.warning(f"Skipping question with missing fields: {q.get('question_id')}")
            continue

        # Construct db_path
        db_path = f"{bird_databases_dir}/{db_id}/{db_id}.sqlite"

        instances.append(
            {
                "question_id": question_id,
                "question": question_text,
                "gold_sql": gold_sql,
                "db_id": db_id,
                "db_path": db_path,
            }
        )

    logger.info(f"Prepared {len(instances)} BIRD instances")
    return instances
