import json
import sqlite3
from pathlib import Path
from typing import Any, List, Tuple

# ============================================================================
# CONFIGURATION: Edit these paths and settings
# ============================================================================
DB_PATH = "data/processed/wc.db"
QUERIES_JSON_PATH = "odi_queries.json"
LOG_PROGRESS = True
MAX_RESULTS_PREVIEW = 5

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


def normalize_for_comparison(value: Any) -> Any:
    """
    Normalize a value for comparison.
    - Convert tuples to tuples (for consistency)
    - Convert lists to tuples if they represent row data
    - Handle None values
    """
    if value is None:
        return None
    if isinstance(value, str):
        return value.strip().lower() if value else ""
    if isinstance(value, (list, tuple)):
        return tuple(normalize_for_comparison(v) for v in value)
    return value


def normalize_answer_rows(answer: Any) -> Tuple[Any, ...]:
    """Normalize a JSON answer into a tuple of comparable rows."""
    if answer is None:
        return tuple()
    if not isinstance(answer, list):
        return (normalize_for_comparison(answer),)
    return tuple(normalize_for_comparison(row) for row in answer)


def normalize_query_rows(rows: List[Tuple[Any, ...]]) -> Tuple[Any, ...]:
    """Normalize SQLite result rows into a tuple of comparable rows."""
    return tuple(normalize_for_comparison(row) for row in rows)


def compare_results(executed: List[Tuple], expected: List[Any]) -> bool:
    """
    Compare executed query results with expected answers.
    Handles nested lists and tuples.

    Returns True if results match, False otherwise.
    """
    executed_norm = normalize_query_rows(executed)
    expected_norm = normalize_answer_rows(expected)

    if not executed_norm and not expected_norm:
        return True
    if len(executed_norm) != len(expected_norm):
        return False

    for exec_row, exp_row in zip(executed_norm, expected_norm):
        if exec_row != exp_row:
            return False

    return True


def execute_query(
    conn: sqlite3.Connection, query: str
) -> Tuple[bool, List[Tuple], str]:
    """
    Execute a single query against the database.

    Returns:
        (success: bool, results: List[Tuple], error_msg: str)
    """
    try:
        cursor = conn.cursor()
        cursor.execute(query)
        results = [tuple(row) for row in cursor.fetchall()]
        return True, results, ""
    except Exception as e:
        return False, [], str(e)


def load_queries_from_json(json_path: str) -> List[dict]:
    """Load queries and expected answers from JSON file."""
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
        return []
    except Exception as e:
        print(f"Error loading JSON file: {e}")
        return []


def main():
    print("=" * 100)
    print("SQL Query Evaluation Script")
    print("=" * 100)
    print(f"Database: {DB_PATH}")
    print(f"Queries JSON: {QUERIES_JSON_PATH}")
    print()

    # Load queries from JSON
    db_path = Path(DB_PATH)
    json_path = Path(QUERIES_JSON_PATH)

    if not db_path.exists():
        print(f"ERROR: Database file not found: {DB_PATH}")
        return
    if not json_path.exists():
        print(f"ERROR: JSON file not found: {QUERIES_JSON_PATH}")
        return

    queries = load_queries_from_json(str(json_path))
    if not queries:
        print("ERROR: No queries loaded from JSON file.")
        return

    print(f"Loaded {len(queries)} queries from JSON file.")
    print()

    # Connect to database
    try:
        conn = sqlite3.connect(str(db_path))
    except Exception as e:
        print(f"ERROR: Failed to connect to database: {e}")
        return

    # Execution tracking
    total_queries = 0
    successful_executions = 0
    failed_executions = 0
    matched_answers = 0
    unmatched_answers = 0
    execution_errors = []

    # Execute each query
    for idx, query_obj in enumerate(queries, start=1):
        if not isinstance(query_obj, dict):
            continue

        total_queries += 1
        query = query_obj.get("query") or query_obj.get("sql_query")
        expected_answer = query_obj.get("answer", [])
        question = (query_obj.get("question") or "")[:80]

        if not query:
            if LOG_PROGRESS:
                print(f"[{idx}] SKIPPED: No query found | {question}...")
            continue

        # Log query execution
        if LOG_PROGRESS:
            print(f"[{idx}] Executing query... | {question}...")

        # Execute query
        success, results, error_msg = execute_query(conn, query)

        if not success:
            failed_executions += 1
            if LOG_PROGRESS:
                print(f"       FAILED: {error_msg}")
            execution_errors.append(
                {"index": idx, "question": question, "error": error_msg}
            )
            continue

        successful_executions += 1

        # Compare results with expected answer
        matches = compare_results(results, expected_answer)
        if matches:
            matched_answers += 1
            status = "✓ MATCH"
        else:
            unmatched_answers += 1
            status = "✗ MISMATCH"

        if LOG_PROGRESS:
            exec_prev = (
                str(normalize_query_rows(results)[:MAX_RESULTS_PREVIEW])
                if results
                else "(empty)"
            )
            exp_prev = (
                str(normalize_answer_rows(expected_answer)[:MAX_RESULTS_PREVIEW])
                if expected_answer
                else "(empty)"
            )
            print(f"       {status}")
            if not matches:
                print(f"         Expected: {exp_prev}")
                print(f"         Got:      {exec_prev}")

    # Close database connection
    conn.close()

    # Print summary
    print()
    print("=" * 100)
    print("SUMMARY")
    print("=" * 100)
    print(f"Total queries processed: {total_queries}")
    print(f"Successful executions:   {successful_executions}")
    print(f"Failed executions:       {failed_executions}")
    print(f"Matched answers:         {matched_answers}")
    print(f"Unmatched answers:       {unmatched_answers}")
    print(
        f"Match rate:              {(matched_answers / successful_executions * 100):.2f}%"
        if successful_executions > 0
        else "N/A"
    )
    print()

    if execution_errors:
        print("EXECUTION ERRORS:")
        print("-" * 100)
        for err in execution_errors:
            print(f"[{err['index']}] {err['question']}...")
            print(f"     Error: {err['error']}")
        print()

    print("=" * 100)


if __name__ == "__main__":
    main()
