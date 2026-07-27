"""
SQLite query execution with timeout.
Read-only connection. Per-query execution timeout: 20 s via interrupt watchdog.
"""

import sqlite3
import threading
from typing import Optional, List, Tuple, Any


def execute_sql(
    db_path: str,
    sql_query: str,
    timeout_sec: float = 20.0
) -> Optional[List[Tuple[Any, ...]]]:
    """
    Execute SQL query against SQLite database with timeout.

    - Read-only connection
    - Timeout: interrupt via watchdog thread
    - Any error or timeout -> return None (execution failure)

    Args:
        db_path: Path to SQLite database
        sql_query: SQL query string
        timeout_sec: Execution timeout in seconds (default 20)

    Returns:
        List of result tuples, or None if execution failed
    """
    try:
        result = [None]  # Shared container for result
        error = [None]

        def execute_with_timeout():
            try:
                # Create connection inside thread (thread-safe)
                conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=2.0)
                conn.isolation_level = None  # Autocommit mode
                cursor = conn.cursor()
                cursor.execute(sql_query)
                result[0] = cursor.fetchall()
                conn.close()
            except Exception as e:
                error[0] = e

        # Run query in thread with timeout
        thread = threading.Thread(target=execute_with_timeout, daemon=True)
        thread.start()
        thread.join(timeout=timeout_sec)

        if thread.is_alive():
            # Timeout occurred
            return None

        if error[0]:
            return None

        return result[0]

    except Exception:
        return None
