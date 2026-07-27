"""
CricBench data loader.
Handles 4-language variants, clustering by base_question_id.
"""

import json
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


def load_cricbench(gold_path: str, db_path: str) -> List[Dict[str, Any]]:
    """
    Load CricBench gold queries and expand to language variants.

    - Each base question has 4 language fields (english, hindi, telugu, punjabi)
    - Expand to one instance per language (even if multiple variants exist per language)
    - cluster_id = base_question_id (list index in gold file)
    - Log any skipped/empty entries

    Args:
        gold_path: Path to queries.json
        db_path: Path to database (for schema extraction later)

    Returns:
        List of instances, each with:
            {
                "base_question_id": int,
                "language": str,
                "question": str,
                "gold_sql": str,
                "db_path": str,
                "context_url": str,
            }
    """
    with open(gold_path, "r", encoding="utf-8") as f:
        gold_data = json.load(f)

    if not isinstance(gold_data, list):
        raise ValueError(f"Expected gold data to be a list, got {type(gold_data)}")

    instances = []
    languages_to_check = ["english", "hindi", "telugu", "punjabi"]

    for base_idx, entry in enumerate(gold_data):
        # Gold SQL is under "query" or "sql_query" key per spec
        gold_sql = entry.get("query") or entry.get("sql_query")
        if not gold_sql:
            logger.warning(
                f"Base question {base_idx}: no gold SQL found (query/sql_query missing)"
            )
            continue

        context_url = entry.get("context_url", "")

        # Check for language variants
        for lang in languages_to_check:
            # Collect ALL variants of this language (exact key + numbered variants)
            variants = []

            # Try exact key first
            if f"question_{lang}" in entry and entry[f"question_{lang}"]:
                variants.append(entry[f"question_{lang}"])

            # Collect all numbered variants (hindi_1, hindi_2, etc.)
            for variant_num in [1, 2, 3, 4, 5]:
                key = f"question_{lang}_{variant_num}"
                if key in entry and entry[key]:
                    variants.append(entry[key])

            # If still no variants, try the "question" field (English fallback)
            if not variants and lang == "english":
                question_text = entry.get("question")
                if question_text:
                    variants.append(question_text)

            if not variants:
                logger.debug(
                    f"Base question {base_idx}: no variant for language '{lang}'"
                )
                continue

            # Create instance for EACH variant of this language
            for variant_idx, question_text in enumerate(variants):
                instances.append(
                    {
                        "base_question_id": base_idx,
                        "language": lang,
                        "variant_num": variant_idx + 1 if len(variants) > 1 else None,
                        "question": question_text,
                        "gold_sql": gold_sql,
                        "db_path": db_path,
                        "context_url": context_url,
                    }
                )

    logger.info(
        f"Loaded {len(instances)} instances from {len(gold_data)} base questions"
    )
    return instances
