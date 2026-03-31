import copy
import json
import re
from difflib import SequenceMatcher
from pathlib import Path


RAW_DIR = Path("results/raw/t20/qwen")
PROCESSED_DIR = Path("results/processed/t20")
ODI_QUERIES_PATH = Path("t20_I_cricbench.json")

QUESTION_KEYS = (
    "question",
    "question_english",
    "question_hindi",
    "question_punjabi",
    "question_telugu",
)
MIN_MATCH_SCORE = 0.72
MAX_PROMPT_OPTIONS = 12


def normalize_text(value):
    if not isinstance(value, str):
        return ""
    text = value.strip().lower()
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"[^\w\s]", "", text, flags=re.UNICODE)
    return text


def get_question_variants(entry):
    variants = []
    for key in QUESTION_KEYS:
        value = entry.get(key)
        if isinstance(value, str) and value.strip():
            variants.append((key, value))
    return variants


def score_question_pair(reference_question, candidate_question):
    reference_norm = normalize_text(reference_question)
    candidate_norm = normalize_text(candidate_question)
    if not reference_norm or not candidate_norm:
        return 0.0

    if reference_norm == candidate_norm:
        return 1.0

    if reference_norm in candidate_norm or candidate_norm in reference_norm:
        shorter = min(len(reference_norm), len(candidate_norm))
        longer = max(len(reference_norm), len(candidate_norm))
        return min(1.0, 0.95 + (shorter / max(longer, 1)) * 0.05)

    return SequenceMatcher(None, reference_norm, candidate_norm).ratio()


def best_query_matches(reference_question, odi_queries):
    candidates = []
    for index, entry in enumerate(odi_queries):
        best_score = 0.0
        best_question_key = None
        best_question_text = None

        for key, candidate_question in get_question_variants(entry):
            score = score_question_pair(reference_question, candidate_question)
            if score > best_score:
                best_score = score
                best_question_key = key
                best_question_text = candidate_question

        if best_score >= MIN_MATCH_SCORE:
            candidates.append(
                {
                    "index": index,
                    "score": best_score,
                    "entry": entry,
                    "matched_key": best_question_key,
                    "matched_question": best_question_text,
                }
            )

    candidates.sort(key=lambda item: item["score"], reverse=True)
    return candidates


def choose_candidate(reference_question, candidates, file_name, group_id):
    if not candidates:
        return None

    perfect_matches = [
        candidate for candidate in candidates if abs(candidate["score"] - 1.0) < 1e-12
    ]
    if len(perfect_matches) == 1:
        chosen = perfect_matches[0]
        print(
            f"[MATCH] {file_name} | id={group_id} | exact match score=1.000 -> using query index {chosen['index']}"
        )
        return chosen

    if len(candidates) == 1:
        chosen = candidates[0]
        print(
            f"[MATCH] {file_name} | id={group_id} | single best candidate score={chosen['score']:.3f} -> auto-selecting"
        )
        return chosen

    print("-" * 120)
    print(f"[PROMPT] {file_name} | id={group_id}")
    print("Reference English question:")
    print(reference_question)
    print()
    print("Available options:")

    shown_candidates = candidates[:MAX_PROMPT_OPTIONS]
    for option_number, candidate in enumerate(shown_candidates, start=1):
        entry = candidate["entry"]
        print(
            f"[{option_number}] score={candidate['score']:.3f} | matched={candidate['matched_key']}"
        )
        for key in QUESTION_KEYS:
            value = entry.get(key)
            if isinstance(value, str) and value.strip():
                label = key.replace("question_", "")
                print(f"  {label}: {value}")
        print()

    while True:
        choice = (
            input(f"Choose 1-{len(shown_candidates)} or 's' to skip: ").strip().lower()
        )
        if choice == "s":
            return None
        if choice.isdigit():
            option_number = int(choice)
            if 1 <= option_number <= len(shown_candidates):
                return shown_candidates[option_number - 1]
        print("Invalid choice. Please enter a valid option number or 's'.")


def get_representative_row(group_rows):
    for row in group_rows:
        if row.get("language") == "English":
            return row
    return group_rows[0] if group_rows else None


def update_group_with_odi_entry(group_rows, odi_entry):
    gold_sql = odi_entry.get("query", "")
    gold_answer = copy.deepcopy(odi_entry.get("answer", []))
    gold_column_names = copy.deepcopy(odi_entry.get("column_names", []))

    for row in group_rows:
        row["gold_sql"] = gold_sql
        row["gold_answer"] = gold_answer
        row["gold_column_names"] = gold_column_names


def process_file(raw_path, processed_path, odi_queries):
    print("=" * 120)
    print(f"[FILE] Processing {raw_path}")

    raw_data = json.loads(raw_path.read_text(encoding="utf-8"))
    if not isinstance(raw_data, list):
        raise ValueError(f"Expected a JSON list in {raw_path}")

    grouped_rows = {}
    group_order = []
    for row in raw_data:
        if not isinstance(row, dict):
            continue
        group_id = row.get("id")
        if group_id not in grouped_rows:
            grouped_rows[group_id] = []
            group_order.append(group_id)
        grouped_rows[group_id].append(row)

    updated_groups = 0
    unmatched_groups = []
    ambiguous_groups = []

    for group_id in group_order:
        group_rows = grouped_rows[group_id]
        representative_row = get_representative_row(group_rows)
        if representative_row is None:
            continue

        reference_question = (
            representative_row.get("question")
            or representative_row.get("question_english")
            or ""
        )
        if not isinstance(reference_question, str) or not reference_question.strip():
            print(
                f"[WARN] {raw_path.name} | id={group_id} | missing representative question, skipped"
            )
            unmatched_groups.append(group_id)
            continue

        candidates = best_query_matches(reference_question, odi_queries)
        if not candidates:
            print(f"[WARN] {raw_path.name} | id={group_id} | no match found")
            unmatched_groups.append(group_id)
            continue

        top_score = candidates[0]["score"]
        exact_count = sum(
            1 for candidate in candidates if abs(candidate["score"] - 1.0) < 1e-12
        )

        if top_score < 1.0 and len(candidates) > 1:
            ambiguous_groups.append(group_id)
            chosen = choose_candidate(
                reference_question, candidates, raw_path.name, group_id
            )
        elif top_score == 1.0 and exact_count > 1:
            ambiguous_groups.append(group_id)
            chosen = choose_candidate(
                reference_question, candidates, raw_path.name, group_id
            )
        else:
            chosen = candidates[0]
            print(
                f"[MATCH] {raw_path.name} | id={group_id} | score={chosen['score']:.3f} | matched_key={chosen['matched_key']}"
            )

        if chosen is None:
            unmatched_groups.append(group_id)
            continue

        update_group_with_odi_entry(group_rows, chosen["entry"])
        updated_groups += 1

    processed_path.parent.mkdir(parents=True, exist_ok=True)
    processed_path.write_text(
        json.dumps(raw_data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"[FILE] Written {processed_path}")
    print(f"[FILE] Updated groups: {updated_groups}")
    print(f"[FILE] Ambiguous groups: {ambiguous_groups}")
    print(f"[FILE] Unmatched groups: {unmatched_groups}")


def main():
    if not RAW_DIR.exists():
        raise FileNotFoundError(f"Raw directory not found: {RAW_DIR}")
    if not ODI_QUERIES_PATH.exists():
        raise FileNotFoundError(f"ODI query file not found: {ODI_QUERIES_PATH}")

    odi_queries = json.loads(ODI_QUERIES_PATH.read_text(encoding="utf-8"))
    if not isinstance(odi_queries, list):
        raise ValueError("ODI queries JSON root must be a list")

    json_files = sorted(path for path in RAW_DIR.rglob("*.json") if path.is_file())
    print(f"[INFO] Found {len(json_files)} raw JSON files in {RAW_DIR}")

    for raw_path in json_files:
        relative_path = raw_path.relative_to(RAW_DIR)
        processed_path = PROCESSED_DIR / relative_path
        process_file(raw_path, processed_path, odi_queries)

    print("=" * 120)
    print("[INFO] ODI synchronization complete")


if __name__ == "__main__":
    main()
