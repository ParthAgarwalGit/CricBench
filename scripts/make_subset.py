import json
import random
from collections import Counter
from pathlib import Path


INPUT_FILE_PATH = Path("t20_I_cricbench.json")
OUTPUT_FILE_PATH = Path("t20_I_cricbench_25pct.json")

# Deterministic sampling so the same 50 rows are produced every run.
RANDOM_SEED = 42

# 25 rows from the first 100 and 25 from the remaining 100.
# These quotas sum to the requested overall distribution:
# easy=16, medium=17, hard=17.
FIRST_HALF_TARGETS = {"easy": 8, "medium": 9, "hard": 8}
SECOND_HALF_TARGETS = {"easy": 8, "medium": 8, "hard": 9}


def normalize_difficulty(value):
    if not isinstance(value, str):
        return ""
    return value.strip().lower()


def select_from_half(indexed_rows, target_counts, rng, half_name):
    selected = []
    summary = Counter()

    for difficulty in ("easy", "medium", "hard"):
        candidates = [
            (index, row)
            for index, row in indexed_rows
            if normalize_difficulty(row.get("difficulty")) == difficulty
        ]

        required = target_counts.get(difficulty, 0)
        available = len(candidates)
        if available < required:
            raise ValueError(
                f"Not enough {difficulty} queries in {half_name}: required {required}, available {available}"
            )

        chosen = rng.sample(candidates, required)
        selected.extend(chosen)
        summary[difficulty] += len(chosen)

    return selected, summary


def main():
    if not INPUT_FILE_PATH.exists():
        raise FileNotFoundError(f"Input file not found: {INPUT_FILE_PATH}")

    data = json.loads(INPUT_FILE_PATH.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("Input JSON must be a list of query dictionaries")

    if len(data) < 200:
        raise ValueError(
            f"Expected at least 200 queries, found {len(data)} in {INPUT_FILE_PATH}"
        )

    first_half = list(enumerate(data[:100]))
    second_half = list(enumerate(data[100:], start=100))

    rng = random.Random(RANDOM_SEED)

    first_selected, first_summary = select_from_half(
        first_half, FIRST_HALF_TARGETS, rng, "first 100 queries"
    )
    second_selected, second_summary = select_from_half(
        second_half, SECOND_HALF_TARGETS, rng, "remaining 100 queries"
    )

    combined = first_selected + second_selected
    combined.sort(key=lambda item: item[0])
    output_data = [row for _, row in combined]

    if len(output_data) != 50:
        raise RuntimeError(f"Expected 50 selected queries, produced {len(output_data)}")

    total_summary = Counter()
    for _, row in combined:
        total_summary[normalize_difficulty(row.get("difficulty"))] += 1

    OUTPUT_FILE_PATH.write_text(
        json.dumps(output_data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"Wrote: {OUTPUT_FILE_PATH}")
    print(f"Selected total: {len(output_data)}")
    print(f"Difficulty counts: {dict(total_summary)}")
    print(f"First half counts: {dict(first_summary)}")
    print(f"Second half counts: {dict(second_summary)}")


if __name__ == "__main__":
    main()
