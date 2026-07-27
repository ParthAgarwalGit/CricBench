import json
import logging
import os
import time
import urllib.error
import urllib.request
from typing import Optional

logger = logging.getLogger(__name__)


class SessionLimitError(Exception):
    

class _AuthError(Exception):
    

class _RetryableError(Exception):


def get_openai_auth_env():
    return os.environ.copy()


def _base_url() -> str:
    return os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")


def _api_key() -> str:
    return os.environ.get("OPENAI_API_KEY", "").strip()


def _headers(api_key: str) -> dict:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def _retry_after_seconds(headers, message: str = "") -> Optional[float]:
    retry_after = headers.get("Retry-After")
    if retry_after:
        try:
            return max(1.0, float(retry_after))
        except Exception:
            pass

    low = (message or "").lower()
    for token in ("retry after", "try again in", "wait"):
        if token in low:
            import re

            m = re.search(r"(?:retry after|try again in|wait)\s+(\d+(?:\.\d+)?)\s*s?",
                           low)
            if m:
                try:
                    return max(1.0, float(m.group(1)))
                except Exception:
                    pass
    return None


def _parse_error_body(body: str) -> tuple[str, str]:
    try:
        payload = json.loads(body)
    except Exception:
        return "", body.strip()

    if isinstance(payload, dict):
        err = payload.get("error", payload)
        if isinstance(err, dict):
            err_type = str(err.get("type") or err.get("code") or "").strip().lower()
            message = str(err.get("message") or payload.get("message") or body).strip()
            return err_type, message
        return "", str(err).strip()
    return "", body.strip()


def _is_limit_error(status: int, err_type: str, message: str) -> bool:
    low = f"{err_type} {message}".lower()
    return status == 429 or any(
        kw in low for kw in [
            "rate_limit",
            "rate limit",
            "quota",
            "insufficient_quota",
            "billing_hard_limit",
            "too many requests",
        ]
    )


def _is_retryable_status(status: int) -> bool:
    return status in {408, 409, 500, 502, 503, 504}


def _request_responses(
    prompt: str,
    system_prompt: str,
    model_slug: str,
    timeout_sec: float,
    max_output_tokens: int = 512,
    reasoning_effort: str = "low",
) -> dict:
    api_key = _api_key()
    if not api_key:
        raise _AuthError("OPENAI_API_KEY is not set")

    payload = {
        "model": model_slug,
        "instructions": system_prompt,
        "input": prompt,
        "max_output_tokens": max_output_tokens,
        "reasoning": {"effort": reasoning_effort},
    }

    req = urllib.request.Request(
        f"{_base_url()}/responses",
        data=json.dumps(payload).encode("utf-8"),
        headers=_headers(api_key),
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
        err_type, message = _parse_error_body(body)
        status = int(getattr(e, "code", 0) or 0)

        if status in {401, 403}:
            raise _AuthError(message or f"HTTP {status}") from e

        if _is_limit_error(status, err_type, message):
            retry_after = _retry_after_seconds(getattr(e, "headers", {}), message)
            if retry_after is not None:
                message = f"{message} (retry_after={retry_after:.0f}s)"
            raise SessionLimitError(message or f"HTTP {status}") from e

        if _is_retryable_status(status):
            raise _RetryableError(message or f"HTTP {status}") from e

        raise RuntimeError(message or f"HTTP {status}") from e
    except urllib.error.URLError as e:
        raise _RetryableError(str(e)) from e


def _extract_response_text(response: dict) -> str:
    if not isinstance(response, dict):
        return ""

    direct = response.get("output_text")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()

    chunks = []
    for item in response.get("output", []) or []:
        if not isinstance(item, dict):
            continue
        content = item.get("content", []) or []
        for part in content:
            if not isinstance(part, dict):
                continue
            text = part.get("text")
            if isinstance(text, str) and text:
                chunks.append(text)
    return "".join(chunks).strip()


def check_cli_auth(
    model_slug: str = "gpt-5.4-mini",
    timeout_sec: float = 30.0,
) -> Optional[str]:
    try:
        response = _request_responses(
            prompt="ok",
            system_prompt="Reply with ok.",
            model_slug=model_slug,
            timeout_sec=timeout_sec,
            max_output_tokens=4,
            reasoning_effort="low",
        )
    except _AuthError as e:
        return str(e)
    except SessionLimitError as e:
        return str(e)
    except _RetryableError as e:
        return f"probe failed: {type(e).__name__}: {e}"
    except Exception as e:
        return f"probe failed: {type(e).__name__}: {e}"

    text = _extract_response_text(response)
    if not text:
        return f"empty response (model={model_slug})"
    return None


def call_codex(
    prompt: str,
    system_prompt: str,
    model_slug: str = "gpt-5.4-mini",
    timeout_sec: float = 120.0,
    max_retries: int = 3,
    backoff_factor: float = 2.0,
) -> Optional[str]:
    for attempt in range(max_retries):
        try:
            logger.debug(f"Call attempt {attempt + 1}/{max_retries}")
            response = _request_responses(
                prompt=prompt,
                system_prompt=system_prompt,
                model_slug=model_slug,
                timeout_sec=timeout_sec,
                max_output_tokens=512,
                reasoning_effort="low",
            )
            response_text = _extract_response_text(response)
            if response_text:
                logger.info(f"Success on attempt {attempt + 1}")
                return response_text

            logger.error(f"Empty response (attempt {attempt + 1})")
            if attempt < max_retries - 1:
                _sleep_with_backoff(attempt, backoff_factor)
                continue
            return None

        except SessionLimitError:
            raise

        except _AuthError as e:
            logger.error(f"OpenAI auth error: {e}")
            return None

        except _RetryableError as e:
            logger.warning(f"Retryable OpenAI error: {e}")
            if attempt < max_retries - 1:
                _sleep_with_backoff(attempt, backoff_factor)
                continue
            return None

        except urllib.error.HTTPError as e:
            logger.error(f"HTTP error: {getattr(e, 'code', 'unknown')} {e}")
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
