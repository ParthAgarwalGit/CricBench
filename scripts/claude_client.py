"""
Claude Haiku 4.5 client via `claude -p` subprocess.
Handles authentication via local credentials or API key.
"""

import subprocess
import json
import time
import logging
import platform
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class SessionLimitError(Exception):

def get_claude_auth_env():
    return os.environ.copy()

def check_cli_auth(
    model_slug: str = "claude-haiku-4-5",
    timeout_sec: float = 30.0,
) -> Optional[str]:
    """
    Probe `claude -p` once to confirm the CLI can reach the model.
    """
    try:
        result = subprocess.run(
            ["claude", "-p", "ok", "--model", model_slug,
             "--output-format", "json", "--max-turns", "1"],
            capture_output=True, text=True, timeout=timeout_sec,
            check=False, env=get_claude_auth_env(),
        )
    except Exception as e:
        return f"probe failed: {type(e).__name__}: {e}"

    out = (result.stdout or "").strip()
    if not out:
        return f"empty response (stderr: {(result.stderr or '')[:200]})"
    try:
        env = json.loads(out)
    except json.JSONDecodeError:
        return f"non-JSON response: {out[:200]}"
    if env.get("is_error"):
        return str(env.get("error") or env.get("result") or "unknown error").strip()
    return None


def call_claude(
    prompt: str,
    system_prompt: str,
    model_slug: str = "claude-haiku-4-5",
    timeout_sec: float = 120.0,
    max_retries: int = 3,
    backoff_factor: float = 2.0,
) -> Optional[str]:
    disallowed_tools = (
        "Bash,Read,Write,Edit,Glob,Grep,WebSearch,WebFetch,"
        "NotebookEdit,Task,TodoWrite"
    )

    for attempt in range(max_retries):
        try:
            logger.debug(f"Call attempt {attempt + 1}/{max_retries}")

            # Build command as list
            cmd_list = [
                "claude", "-p", prompt,
                "--model", model_slug,
                "--append-system-prompt", system_prompt,
                "--output-format", "json", "--max-turns", "1",
                "--disallowedTools", disallowed_tools,
            ]

            # Get auth environment
            auth_env = get_claude_auth_env()

            # Run subprocess with auth
            result = subprocess.run(
                cmd_list,
                capture_output=True,
                text=True,
                timeout=timeout_sec,
                check=False,
                env=auth_env,
            )

            # Parse response
            if not result.stdout or not result.stdout.strip():
                logger.error(f"Empty response (attempt {attempt + 1})")
                if attempt < max_retries - 1:
                    _sleep_with_backoff(attempt, backoff_factor)
                    continue
                return None

            try:
                envelope = json.loads(result.stdout)
                
                if envelope.get("is_error"):
                    err = str(envelope.get("error") or envelope.get("result")
                              or "unknown error").strip()
                    low = err.lower()
                    if "not logged in" in low or "/login" in low:
                        logger.error(
                            "Claude CLI not authenticated: %r. Run `claude` then "
                            "/login (or set ANTHROPIC_API_KEY) and re-run.", err
                        )
                        return None  # auth will not recover across retries
                    if "session limit" in low or "usage limit" in low:
                        # Subscription window exhausted -> caller pauses until reset
                        # and retries. NEVER score this as a wrong answer.
                        raise SessionLimitError(err)
                    if _is_retryable_error(err) and attempt < max_retries - 1:
                        logger.warning(f"Retryable error: {err}")
                        _sleep_with_backoff(attempt, backoff_factor)
                        continue
                    logger.error(f"Error: {err}")
                    return None

                response_text = envelope.get("result")
                if response_text is not None:
                    logger.info(f"Success on attempt {attempt + 1}")
                    return response_text

                error_msg = envelope.get("error")
                if error_msg and _is_retryable_error(error_msg) and attempt < max_retries - 1:
                    logger.warning(f"Retryable error: {error_msg}")
                    _sleep_with_backoff(attempt, backoff_factor)
                    continue

                logger.error(f"Error: {error_msg}")
                return None

            except json.JSONDecodeError as e:
                logger.error(f"JSON parse error: {str(e)[:50]}")
                if attempt < max_retries - 1:
                    _sleep_with_backoff(attempt, backoff_factor)
                    continue
                return None

        except SessionLimitError:
            raise  # propagate to the caller's pause-until-reset handler

        except subprocess.TimeoutExpired:
            logger.warning(f"Timeout on attempt {attempt + 1}")
            if attempt < max_retries - 1:
                _sleep_with_backoff(attempt, backoff_factor)
                continue
            return None

        except Exception as e:
            logger.error(f"Exception: {type(e).__name__}: {e}")
            if attempt < max_retries - 1:
                _sleep_with_backoff(attempt, backoff_factor)
                continue
            return None

    logger.error("All retries exhausted")
    return None


def _is_retryable_error(msg: str) -> bool:
    """Check if error is retryable."""
    return any(kw in str(msg).lower() for kw in [
        "timeout", "connection", "overload", "rate_limit", "temporarily"
    ])


def _sleep_with_backoff(attempt: int, factor: float = 2.0) -> None:
    """Exponential backoff."""
    delay = 1.0 * (factor ** attempt)
    logger.debug(f"Sleeping {delay:.1f}s")
    time.sleep(delay)
