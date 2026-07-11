import json
import re
from difflib import SequenceMatcher
from pathlib import Path


# Configure paths/behavior here. Script runs with no CLI arguments.
DEEPSEEK_FILE = "t20_final_basic_deepseek-chat_v3_t20.json"
CRICBENCH_FILE = "t20_I_cricbench.json"
OUTPUT_FILE = "t20_final_basic_deepseek-chat_v3_t20.partial_synced.json"
MAX_CANDIDATES = 8
CHOICE_MAP_RAW = ""
NO_PROMPT = False


def normalize_text(value):
    if not isinstance(value, str):
        return ""
    text = value.strip().lower()
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"[^\w\s]", "", text, flags=re.UNICODE)
    return text


def is_null_like_sql(value):
    if value is None:
        return True
    if not isinstance(value, str):
        return False
    normalized = value.strip().lower()
    return normalized in {"", "null", "none"}


def get_cricbench_sql(entry):
    return entry.get("query") or entry.get("sql_query")


def get_cricbench_questions(entry):
    questions = []
    for key in (
        "question",
        "question_english",
        "question_hindi",
        "question_punjabi",
        "question_telugu",
    ):
        value = entry.get(key)
        if isinstance(value, str) and value.strip():
            questions.append(value)
    return questions


def partial_match_score(a, b):
    a_norm = normalize_text(a)
    b_norm = normalize_text(b)
    if not a_norm or not b_norm:
        return 0.0, False

    if a_norm in b_norm or b_norm in a_norm:
        shorter = min(len(a_norm), len(b_norm))
        longer = max(len(a_norm), len(b_norm))
        score = 0.95 + (shorter / max(longer, 1)) * 0.05
        return min(score, 1.0), True

    ratio = SequenceMatcher(None, a_norm, b_norm).ratio()
    return ratio, ratio >= 0.72


def build_candidate_list(group_rows, cricbench_data):
    deepseek_questions = []
    for row in group_rows:
        question = row.get("question")
        if isinstance(question, str) and question.strip():
            deepseek_questions.append(question)

    candidate_scores = {}
    candidate_examples = {}

    for deep_q in deepseek_questions:
        for idx, entry in enumerate(cricbench_data):
            entry_questions = get_cricbench_questions(entry)
            best_for_entry = 0.0
            best_q = None

            for cb_q in entry_questions:
                score, matched = partial_match_score(deep_q, cb_q)
                if matched and score > best_for_entry:
                    best_for_entry = score
                    best_q = cb_q

            if best_for_entry > 0:
                prev = candidate_scores.get(idx, 0.0)
                if best_for_entry > prev:
                    candidate_scores[idx] = best_for_entry
                    candidate_examples[idx] = best_q

    ranked = sorted(candidate_scores.items(), key=lambda item: item[1], reverse=True)
    candidates = []
    for idx, score in ranked:
        candidates.append(
            {
                "cricbench_index": idx,
                "score": score,
                "entry": cricbench_data[idx],
                "matched_question": candidate_examples.get(idx, ""),
            }
        )
    return candidates


def choose_candidate_interactively(qid, candidates):
    if not candidates:
        return None

    if len(candidates) == 1:
        chosen = candidates[0]
        print(
            f"ID {qid}: single partial match found (score={chosen['score']:.3f}). Auto-selecting."
        )
        return chosen

    print("-" * 100)
    print(
        f"ID {qid}: multiple partial matches found. Choose one index to apply, or 's' to skip."
    )

    for i, candidate in enumerate(candidates, start=1):
        entry = candidate["entry"]
        preview = (entry.get("question") or "").replace("\n", " ")
        preview = preview[:180] + ("..." if len(preview) > 180 else "")
        print(
            f"[{i}] score={candidate['score']:.3f} | cric_idx={candidate['cricbench_index']} | {preview}"
        )

    while True:
        choice = input("Enter choice number or 's' to skip: ").strip().lower()
        if choice == "s":
            return None
        if choice.isdigit():
            num = int(choice)
            if 1 <= num <= len(candidates):
                return candidates[num - 1]
        print("Invalid choice. Please enter a valid number or 's'.")


def apply_match_to_group(group_rows, cric_entry):
    sql_value = get_cricbench_sql(cric_entry)
    answer_value = cric_entry.get("answer", [])
    columns_value = cric_entry.get("column_names", [])

    for row in group_rows:
        row["gold_sql"] = sql_value
        row["gold_answer"] = answer_value
        row["gold_column_names"] = columns_value
        if "gold_column_name" in row:
            row["gold_column_name"] = columns_value


def parse_choice_map(value):
    result = {}
    if not value:
        return result

    for chunk in value.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        if "=" not in chunk:
            raise ValueError(
                f"Invalid choice-map item '{chunk}'. Expected format like 19=2 or 27=s"
            )
        left, right = chunk.split("=", 1)
        qid = int(left.strip())
        choice = right.strip().lower()
        result[qid] = choice
    return result


def choose_candidate(qid, candidates, preselected_choice=None, allow_prompt=True):
    if not candidates:
        return None

    if len(candidates) == 1:
        chosen = candidates[0]
        print(
            f"ID {qid}: single partial match found (score={chosen['score']:.3f}). Auto-selecting."
        )
        return chosen

    # Use preselected choice if provided (supports non-interactive execution).
    if preselected_choice is not None:
        if preselected_choice == "s":
            print(f"ID {qid}: preselected choice is skip.")
            return None
        if preselected_choice.isdigit():
            idx = int(preselected_choice)
            if 1 <= idx <= len(candidates):
                print(f"ID {qid}: using preselected choice [{idx}].")
                return candidates[idx - 1]
        print(
            f"ID {qid}: invalid preselected choice '{preselected_choice}'. Falling back to prompt/skip."
        )

    if not allow_prompt:
        print("-" * 100)
        print(
            f"ID {qid}: multiple candidates found but prompting disabled. Choose via --choice-map."
        )
        for i, candidate in enumerate(candidates, start=1):
            entry = candidate["entry"]
            preview = (entry.get("question") or "").replace("\n", " ")
            preview = preview[:180] + ("..." if len(preview) > 180 else "")
            print(
                f"[{i}] score={candidate['score']:.3f} | cric_idx={candidate['cricbench_index']} | {preview}"
            )
        return None

    return choose_candidate_interactively(qid, candidates)


def choose_candidate_for_null_sql(
    qid, candidates, preselected_choice=None, allow_prompt=True
):
    if not candidates:
        return None, "no_match"

    perfect = [c for c in candidates if abs(c.get("score", 0.0) - 1.0) < 1e-12]
    if len(perfect) == 1:
        chosen = perfect[0]
        print(
            f"ID {qid}: unique perfect match found (score=1.000). Auto-selecting cric_idx={chosen['cricbench_index']}."
        )
        return chosen, "auto_perfect"

    if len(perfect) > 1:
        print(
            f"ID {qid}: multiple perfect matches found ({len(perfect)}). Asking for choice."
        )

    chosen = choose_candidate(
        qid,
        candidates,
        preselected_choice=preselected_choice,
        allow_prompt=allow_prompt,
    )
    if chosen is None:
        return None, "manual_skipped"
    return chosen, "manual_selected"


def main():
    deepseek_path = Path(DEEPSEEK_FILE)
    cricbench_path = Path(CRICBENCH_FILE)
    output_path = Path(OUTPUT_FILE)

    deepseek_data = json.loads(deepseek_path.read_text(encoding="utf-8"))
    cricbench_data = json.loads(cricbench_path.read_text(encoding="utf-8"))

    if not isinstance(deepseek_data, list):
        raise ValueError("DeepSeek file must contain a JSON list")
    if not isinstance(cricbench_data, list):
        raise ValueError("CricBench file must contain a JSON list")

    grouped = {}
    for row in deepseek_data:
        qid = row.get("id")
        grouped.setdefault(qid, []).append(row)

    choice_map = parse_choice_map(CHOICE_MAP_RAW)
    allow_prompt = not NO_PROMPT
    unmatched_null_gold_sql_ids = []
    updated_ids = set()
    updated_rows = 0
    null_sql_auto_perfect_ids = set()
    null_sql_manual_selected_ids = set()

    # Process all ids where any row has null/empty gold_sql
    null_gold_ids = []
    for qid, group_rows in grouped.items():
        if any(is_null_like_sql(row.get("gold_sql")) for row in group_rows):
            null_gold_ids.append(qid)

    for qid in null_gold_ids:
        group_rows = grouped[qid]

        candidates = build_candidate_list(group_rows, cricbench_data)
        if MAX_CANDIDATES > 0:
            candidates = candidates[:MAX_CANDIDATES]

        selected, selection_mode = choose_candidate_for_null_sql(
            qid,
            candidates,
            preselected_choice=choice_map.get(qid),
            allow_prompt=allow_prompt,
        )
        if selected is None:
            unmatched_null_gold_sql_ids.append(qid)
        else:
            apply_match_to_group(group_rows, selected["entry"])
            updated_ids.add(qid)
            updated_rows += len(group_rows)
            if selection_mode == "auto_perfect":
                null_sql_auto_perfect_ids.add(qid)
            else:
                null_sql_manual_selected_ids.add(qid)

    output_path.write_text(
        json.dumps(deepseek_data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print("\n" + "=" * 100)
    print("Sync complete")
    print(f"Updated ids: {len(updated_ids)}")
    print(f"Updated rows: {updated_rows}")
    print(
        "Null gold_sql auto-perfect ids: "
        f"{len(null_sql_auto_perfect_ids)} -> {sorted(null_sql_auto_perfect_ids)}"
    )
    print(
        "Null gold_sql manual-selected ids: "
        f"{len(null_sql_manual_selected_ids)} -> {sorted(null_sql_manual_selected_ids)}"
    )
    print(
        f"Null gold_sql pass unmatched ids: {sorted(set(unmatched_null_gold_sql_ids))}"
    )
    print(f"Written file: {output_path}")


if __name__ == "__main__":
    main()
