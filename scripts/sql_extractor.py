"""
SQL extraction from model response per section 3.5.
Exact spec: handle code fences, otherwise return raw response.
"""

import re


def clean_sql(response: str) -> str:
    """
    Extract SQL from model response per section 3.5.

    Algorithm:
    1. If a ```sql or ``` fenced block exists -> return its contents, stripped.
    2. Else -> return the raw response, stripped.

    Args:
        response: Raw model text output

    Returns:
        Cleaned SQL string
    """
    if not response or not isinstance(response, str):
        return ""

    response = response.strip()

    # Try to find ```sql or ``` fenced code block
    # Pattern: ``` or ```sql at start of line, content, ``` at end
    sql_block_pattern = r"```(?:sql)?\s*(.*?)\s*```"
    match = re.search(sql_block_pattern, response, re.DOTALL | re.IGNORECASE)

    if match:
        sql_text = match.group(1).strip()
        if sql_text:
            return sql_text

    # No fenced block found, return raw response
    return response
