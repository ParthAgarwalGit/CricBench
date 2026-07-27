"""
Prompt construction.
"""

import sqlite3
from typing import Tuple


def get_schema_ddl(db_path: str) -> str:
    """
    Extract schema DDL from database via:
        SELECT sql FROM sqlite_master WHERE type='table' AND sql IS NOT NULL

    Args:
        db_path: Path to SQLite database file

    Returns:
        Schema DDL block (one CREATE TABLE per line)
    """
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND sql IS NOT NULL"
        )
        rows = cursor.fetchall()
        conn.close()

        if not rows:
            raise ValueError(f"No tables found in {db_path}")

        ddl_lines = [row[0] for row in rows if row[0]]
        return "\n\n".join(ddl_lines)
    except sqlite3.Error as e:
        raise RuntimeError(f"Failed to extract schema from {db_path}: {e}")


def build_prompts(
    question: str,
    db_path: str,
    benchmark: str = "cricbench",
    dk_prompt_path: str = None,
) -> Tuple[str, str]:
    """
    Build (system_prompt, user_prompt) tuple.

    Args:
        question: The natural language question
        db_path: Path to database (schema extracted live from this)
        benchmark: "cricbench" or "bird"
        dk_prompt_path: If set, the system prompt is loaded from this
            domain-knowledge template file and its "{schema_ddl}" placeholder
            is replaced with the live schema. When None, the built-in
            schema-only prompt for `benchmark` is used (unchanged baseline).

    Returns:
        (system_prompt, user_prompt) as strings
    """
    schema_ddl = get_schema_ddl(db_path)

    # User message
    user_prompt = f"Question: {question}\nOutput ONLY raw SQL."

    # Domain-knowledge condition: system prompt = external knowledge + schema.
    if dk_prompt_path:
        with open(dk_prompt_path, "r", encoding="utf-8") as fh:
            template = fh.read()
        if "{schema_ddl}" not in template:
            raise ValueError(
                f"DK prompt {dk_prompt_path} has no '{{schema_ddl}}' placeholder"
            )
        system_prompt = template.replace("{schema_ddl}", schema_ddl)
        return system_prompt, user_prompt

    # System prompt (benchmark-specific)
    if benchmark in ("cricbench", "odi", "t20i", "test"):
        system_prompt = f"""You are a SQL expert. Write a SQLite query using ONLY this schema:

{schema_ddl}

IMPORTANT:
- Use ONLY the tables and columns listed above.
- There is NO Innings table. To filter by innings, use the `inning` column.
- Legal deliveries: wides = 0 AND noballs = 0.
- Bowler wickets exclude: 'run out', 'retired hurt', 'obstructing the field'.
- Output ONLY raw SQL (no explanation, no markdown)."""

    elif benchmark == "bird":
        system_prompt = f"""You are a SQL expert. Write a SQLite query using ONLY this schema:

{schema_ddl}

IMPORTANT:
- Use ONLY the tables and columns listed above.
- Output ONLY raw SQL (no explanation, no markdown)."""

    else:
        raise ValueError(f"Unknown benchmark: {benchmark}")

    return system_prompt, user_prompt
