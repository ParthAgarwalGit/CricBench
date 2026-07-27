"""
Local open-source model client, for any OpenAI-compatible chat-completions
server.
"""

import json
import logging
import os
import time
import urllib.error
import urllib.request
from typing import Optional

logger = logging.getLogger(__name__)


class SessionLimitError(Exception):


class _RetryableError(Exception):


def _base_url() -> str:
    return os.environ.get("LOCAL_MODEL_BASE_URL", "http://localhost:11434/v1").rstrip("/")


def _api_key() -> str:
    return os.environ.get("LOCAL_MODEL_API_KEY", "not-needed")


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {_api_key()}",
        "Content-Type": "application/json",
    }


def _request_chat_completion(
    prompt: str,
    system_prompt: str,
    model_slug: str,
    timeout_sec: float,
    max_tokens: int = 512,
) -> dict:
    payload = {
        "model": model_slug,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": max_tokens,
        "temperature": 0,
    }

    req = urllib.request.Request(
        f"{_base_url()}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers=_headers(),
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", errors="replace")
        except Exception:
            pass
        status = int(getattr(e, "code", 0) or 0)
        if status == 429:
            raise SessionLimitError(body or f"HTTP {status}") from e
        if status in {408, 500, 502, 503, 504}:
            raise _RetryableError(body or f"HTTP {status}") from e
        raise RuntimeError(body or f"HTTP {status}") from e
    except urllib.error.URLError as e:
        # Server not running / wrong port / connection refused, etc.
        raise _RetryableError(str(e)) from e


def _extract_text(response: dict) -> str:
    try:
        return (response["choices"][0]["message"]["content"] or "").strip()
    except Exception:
        return ""


def check_cli_auth(
    model_slug: str = "local-model",
    timeout_sec: float = 30.0,
) -> Optional[str]:
    try:
        response = _request_chat_completion(
            prompt="ok", system_prompt="Reply with ok.",
            model_slug=model_slug, timeout_sec=timeout_sec, max_tokens=4,
        )
    except SessionLimitError as e:
        return str(e)
    except _RetryableError as e:
        return (
            f"could not reach local server at {_base_url()}: {e}. "
            "Is it running? (e.g. `ollama serve`, or start your vLLM/LM Studio server)"
        )
    except Exception as e:
        return f"probe failed: {type(e).__name__}: {e}"

    if not _extract_text(response):
        return f"empty response from model={model_slug}"
    return None


def call_local(
    prompt: str,
    system_prompt: str,
    model_slug: str = "local-model",
    timeout_sec: float = 120.0,
    max_retries: int = 3,
    backoff_factor: float = 2.0,
) -> Optional[str]:
    for attempt in range(max_retries):
        try:
            logger.debug(f"Call attempt {attempt + 1}/{max_retries}")
            response = _request_chat_completion(
                prompt=prompt, system_prompt=system_prompt,
                model_slug=model_slug, timeout_sec=timeout_sec,
            )
            text = _extract_text(response)
            if text:
                logger.info(f"Success on attempt {attempt + 1}")
                return text

            logger.error(f"Empty response (attempt {attempt + 1})")
            if attempt < max_retries - 1:
                _sleep_with_backoff(attempt, backoff_factor)
                continue
            return None

        except SessionLimitError:
            raise

        except _RetryableError as e:
            logger.warning(f"Retryable error: {e}")
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


def _sleep_with_backoff(attempt: int, factor: float = 2.0) -> None:
    delay = 1.0 * (factor ** attempt)
    logger.debug(f"Sleeping {delay:.1f}s")
    time.sleep(delay)
