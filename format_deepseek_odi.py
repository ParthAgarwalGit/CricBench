import ast
import json
from pathlib import Path
from typing import Any


# Configure paths here. By default the script rewrites the source file in place.
INPUT_FILE = "deepseek_v3_test.json"
OUTPUT_FILE = "deepseek_v3_test.json"


def to_tuple_rows(value: Any) -> Any:
    """Convert nested list rows into tuples while preserving outer list structure."""
    if isinstance(value, list):
        if not value:
            return []

        # If this looks like a row of scalar values, convert it to a tuple.
        if all(not isinstance(item, (list, tuple, dict)) for item in value):
            return tuple(value)

        return [to_tuple_rows(item) for item in value]

    if isinstance(value, tuple):
        return tuple(to_tuple_rows(item) for item in value)

    return value


def format_gold_answer(raw_value: Any) -> Any:
    """Normalize a gold_answer entry into a string literal containing tuple rows."""
    parsed = raw_value

    if isinstance(raw_value, str):
        text = raw_value.strip()
        if not text:
            return raw_value
        try:
            parsed = ast.literal_eval(text)
        except Exception:
            return raw_value

    converted = to_tuple_rows(parsed)

    # Store as a string literal because the JSON file keeps answers as strings.
    return repr(converted)


def main() -> None:
    input_path = Path(INPUT_FILE)
    output_path = Path(OUTPUT_FILE)

    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    data = json.loads(input_path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("Expected the JSON root to be a list")

    updated_count = 0

    for row in data:
        if not isinstance(row, dict):
            continue

        if "gold_answer" not in row:
            continue

        original_value = row.get("gold_answer")
        formatted_value = format_gold_answer(original_value)

        if formatted_value != original_value:
            row["gold_answer"] = formatted_value
            updated_count += 1

    output_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"Updated gold_answer entries: {updated_count}")
    print(f"Written file: {output_path}")


if __name__ == "__main__":
    main()
