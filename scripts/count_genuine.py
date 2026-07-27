#!/usr/bin/env python3
"""Count unique scored instances in a checkpoint JSONL file."""

import argparse
import json
from pathlib import Path


def _record_key(record: dict, benchmark: str):
    if benchmark == "bird":
        return record.get("question_id")
    return (
        record.get("base_question_id"),
        record.get("language"),
        record.get("variant_num"),
    )


def count_genuine(checkpoint_path: str, benchmark: str) -> int:
    try:
        rows = [json.loads(line) for line in open(checkpoint_path, encoding="utf-8") if line.strip()]
    except FileNotFoundError:
        return 0

    keys = {
        _record_key(row, benchmark)
        for row in rows
        if row.get("raw_response") and not row.get("error")
    }
    return len(keys)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", default=None)
    parser.add_argument("--model", default="claude-haiku-4-5")
    parser.add_argument(
        "--benchmark",
        choices=["bird", "cricbench", "odi", "t20i", "test"],
        default="cricbench",
    )
    parser.add_argument("--dk", action="store_true")
    args = parser.parse_args()

    suffix = "_dk" if args.dk else ""
    checkpoint = args.checkpoint
    if checkpoint is None:
        checkpoint = f"outputs/raw/{args.model}_{args.benchmark}{suffix}.jsonl"

    print(count_genuine(checkpoint, args.benchmark))


if __name__ == "__main__":
    main()
