import json
import sqlite3
import time
from pathlib import Path


INPUT_FILE_PATH = Path("t20_I_cricbench.json")
OUTPUT_FILE_PATH = Path("t20_I_cricbench_with_answers.json")
DB_FILE_PATH = Path("data/processed/t20_I.db")
QUERY_TIMEOUT_SECONDS = 10
ROW_COUNT_THRESHOLD = 50


def execute_query_with_timeout(connection, query, timeout_seconds):
    deadline = time.monotonic() + timeout_seconds

    def timeout_handler():
        return 1 if time.monotonic() > deadline else 0

    # The handler is called every N SQLite virtual machine steps.
    connection.set_progress_handler(timeout_handler, 10000)
    try:
        cursor = connection.execute(query)
        rows = cursor.fetchall()
        description = cursor.description or []
        return rows, description
    finally:
        connection.set_progress_handler(None, 0)


def row_to_tuple_string(row):
    if len(row) == 1:
        return f"('{row[0]}')"
    return str(tuple(row))


def get_record_id(item, fallback_index):
    return item.get("id", fallback_index)


def execute_queries_and_update(data, connection):
    updated = []
    total = len(data)
    report = {
        "zero_answer_rows_ids": [],
        "over_50_rows_ids": [],
        "warnings": [],
        "errors": [],
    }
    print(f"[INFO] Starting query execution for {total} records")

    for index, item in enumerate(data):
        query_number = index + 1
        record_id = get_record_id(item, query_number)
        print(f"[INFO] Processing query {query_number}/{total}")
        query = item.get("query") or item.get("sql_query")
        current = dict(item)

        if not query:
            current["column_names"] = []
            current["answer"] = []
            current["execution_error"] = "Missing 'query' or 'sql_query' key"
            report["warnings"].append(
                {
                    "id": record_id,
                    "query_number": query_number,
                    "message": current["execution_error"],
                }
            )
            print(f"[WARN] Query {query_number}: missing SQL key, skipped")
            updated.append(current)
            continue

        try:
            rows, description = execute_query_with_timeout(
                connection,
                query,
                QUERY_TIMEOUT_SECONDS,
            )

            current["column_names"] = [column[0] for column in description]
            current["answer"] = [row_to_tuple_string(row) for row in rows]
            current.pop("execution_error", None)

            if len(current["answer"]) == 0:
                report["zero_answer_rows_ids"].append(record_id)
                print(f"[WARN] Query {query_number}: 0 answer rows (id={record_id})")

            if len(current["answer"]) > ROW_COUNT_THRESHOLD:
                report["over_50_rows_ids"].append(record_id)
                print(
                    f"[WARN] Query {query_number}: answer rows exceeded {ROW_COUNT_THRESHOLD} (id={record_id}, rows={len(current['answer'])})"
                )

            print(
                f"[INFO] Query {query_number}: updated column_names={len(current['column_names'])}, answer_rows={len(current['answer'])}"
            )

        except sqlite3.Error as error:
            current["column_names"] = []
            current["answer"] = []
            error_text = str(error)
            if (
                isinstance(error, sqlite3.OperationalError)
                and "interrupted" in error_text.lower()
            ):
                current["execution_error"] = (
                    f"Row {index} SQL timeout after {QUERY_TIMEOUT_SECONDS}s"
                )
                report["errors"].append(
                    {
                        "id": record_id,
                        "query_number": query_number,
                        "message": current["execution_error"],
                    }
                )
                print(
                    f"[ERROR] Query {query_number}: timed out after {QUERY_TIMEOUT_SECONDS}s"
                )
            else:
                current["execution_error"] = f"Row {index} SQL error: {error}"
                report["errors"].append(
                    {
                        "id": record_id,
                        "query_number": query_number,
                        "message": current["execution_error"],
                    }
                )
                print(f"[ERROR] Query {query_number}: {error}")

        updated.append(current)

    return updated, report


def main():
    print(f"[INFO] Reading input file: {INPUT_FILE_PATH}")
    with INPUT_FILE_PATH.open("r", encoding="utf-8") as file:
        data = json.load(file)

    if not isinstance(data, list):
        raise ValueError("Input JSON root must be a list of dictionaries")
    print(f"[INFO] Loaded {len(data)} records from input")

    print(f"[INFO] Connecting to database: {DB_FILE_PATH}")
    with sqlite3.connect(DB_FILE_PATH) as connection:
        print("[INFO] Connected to database")
        updated_data, report = execute_queries_and_update(data, connection)

    print(f"[INFO] Writing output file: {OUTPUT_FILE_PATH}")
    with OUTPUT_FILE_PATH.open("w", encoding="utf-8") as file:
        json.dump(updated_data, file, indent=4, ensure_ascii=False)

    print(f"[INFO] Updated {len(updated_data)} records")
    print(f"[INFO] Saved output to {OUTPUT_FILE_PATH}")
    print("[INFO] Execution report summary:")
    print(
        f"[INFO] zero_answer_rows_ids={len(report['zero_answer_rows_ids'])}, over_50_rows_ids={len(report['over_50_rows_ids'])}, warnings={len(report['warnings'])}, errors={len(report['errors'])}"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
