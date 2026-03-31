import argparse
import json
import re
from collections import defaultdict
from pathlib import Path


DEFAULT_DEEPSEEK_FILE = "t20_final_basic_deepseek-cht_v3_t20.json"
DEFAULT_CRICBENCH_FILE = "t20_I_cricbench.json"


def normalize_sql(sql_text):
    if not isinstance(sql_text, str):
        return ""
    collapsed = re.sub(r"\s+", " ", sql_text.strip())
    return collapsed.rstrip(";").strip().lower()


def normalize_question(question_text):
    if not isinstance(question_text, str):
        return ""
    text = question_text.lower().strip()
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"[^\w\s]", "", text)
    return text


def build_cricbench_lookups(cricbench_data):
    sql_lookup = {}
    question_lookup = {}

    for row in cricbench_data:
        if not isinstance(row, dict):
            continue

        query_text = row.get("query") or row.get("sql_query")
        sql_key = normalize_sql(query_text)
        if sql_key and sql_key not in sql_lookup:
            sql_lookup[sql_key] = row

        for q_key in (
            "question",
            "question_english",
            "question_hindi",
            "question_punjabi",
            "question_telugu",
        ):
            q_text = row.get(q_key)
            q_norm = normalize_question(q_text)
            if q_norm and q_norm not in question_lookup:
                question_lookup[q_norm] = row

    return sql_lookup, question_lookup


def find_match_for_group(group_rows, sql_lookup, question_lookup):
    for row in group_rows:
        for sql_key_name in ("gold_sql", "generated_sql"):
            sql_key = normalize_sql(row.get(sql_key_name))
            if sql_key and sql_key in sql_lookup:
                return sql_lookup[sql_key]

    for row in group_rows:
        q_key = normalize_question(row.get("question"))
        if q_key and q_key in question_lookup:
            return question_lookup[q_key]

    return None


def sync_gold_fields(deepseek_data, cricbench_data):
    sql_lookup, question_lookup = build_cricbench_lookups(cricbench_data)

    grouped = defaultdict(list)
    for row in deepseek_data:
        grouped[row.get("id")].append(row)

    updated_rows = 0
    updated_ids = 0
    unmatched_ids = []

    for qid, group_rows in grouped.items():
        match = find_match_for_group(group_rows, sql_lookup, question_lookup)
        if match is None:
            unmatched_ids.append(qid)
            continue

        new_gold_answer = match.get("answer", [])
        new_gold_columns = match.get("column_names", [])

        for row in group_rows:
            row["gold_answer"] = new_gold_answer
            row["gold_column_names"] = new_gold_columns
            updated_rows += 1

        updated_ids += 1

    return updated_rows, updated_ids, unmatched_ids


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Copy gold_answer and gold_column_names into DeepSeek result rows "
            "from matching records in t20_I_cricbench.json. "
            "All rows sharing the same id are updated together."
        )
    )
    parser.add_argument(
        "--deepseek-file",
        default=DEFAULT_DEEPSEEK_FILE,
        help="Path to the deepseek result JSON file",
    )
    parser.add_argument(
        "--cricbench-file",
        default=DEFAULT_CRICBENCH_FILE,
        help="Path to t20_I_cricbench JSON file",
    )
    parser.add_argument(
        "--output-file",
        default=None,
        help="Output path. If omitted, deepseek file is overwritten in place.",
    )
    args = parser.parse_args()

    deepseek_path = Path(args.deepseek_file)
    cricbench_path = Path(args.cricbench_file)
    output_path = Path(args.output_file) if args.output_file else deepseek_path

    deepseek_data = json.loads(deepseek_path.read_text(encoding="utf-8"))
    cricbench_data = json.loads(cricbench_path.read_text(encoding="utf-8"))

    if not isinstance(deepseek_data, list):
        raise ValueError("DeepSeek file root must be a JSON list")
    if not isinstance(cricbench_data, list):
        raise ValueError("CricBench file root must be a JSON list")

    updated_rows, updated_ids, unmatched_ids = sync_gold_fields(
        deepseek_data, cricbench_data
    )

    output_path.write_text(
        json.dumps(deepseek_data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"Updated rows: {updated_rows}")
    print(f"Updated ids: {updated_ids}")
    print(f"Unmatched ids: {len(unmatched_ids)}")
    if unmatched_ids:
        print("Unmatched id list:", unmatched_ids)
    print(f"Written file: {output_path}")


if __name__ == "__main__":
    main()
