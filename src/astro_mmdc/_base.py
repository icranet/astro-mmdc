from __future__ import annotations

import copy
import random
import re
import sys
import time
from typing import Any

import httpx

from astro_mmdc._version import __version__
from astro_mmdc.exceptions import APIError, NotFoundError, RateLimitError, ValidationError


_MAX_RETRIES = 3
_RETRY_BACKOFF = 1.0  # seconds, doubles each retry
_MAX_RETRY_SLEEP = 120.0  # cap server-provided Retry-After so a bad header can't stall us
_ALWAYS_RETRYABLE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
# Mirrors the server: anything else is silently not recorded, so fail here instead.
_END_USER_RE = re.compile(r"^[A-Za-z0-9._:-]{1,64}$")


def _retry_delay(seconds: float) -> float:
    # Cap, then add 0-25% jitter so synchronized clients don't retry in lockstep.
    return min(seconds, _MAX_RETRY_SLEEP) * (1.0 + random.uniform(0.0, 0.25))


def _version_tuple(value: str) -> tuple[int, ...]:
    return tuple(int(part) for part in value.split(".")[:3])


class BaseClient:
    def __init__(
        self,
        base_url: str = "https://mmdc.am",
        timeout: float = 30.0,
        app: str | None = None,
        api_key: str | None = None,
        end_user: str | None = None,
    ) -> None:
        headers = {"User-Agent": f"astro-mmdc/{__version__}"}
        if app:
            headers["X-MMDC-Client"] = app
        if api_key:
            headers["X-API-Key"] = api_key
        self._client = httpx.Client(base_url=base_url, timeout=timeout, headers=headers)
        self._owns_client = True
        self._extra_headers = _end_user_headers(end_user)
        # Shared with views so the outdated-SDK warning prints once per client.
        self._warn_state = {"min_version_warned": False}

    def with_end_user(self, end_user: str | None) -> BaseClient:
        """A view on the same connection pool that sends a different end user."""
        view = copy.copy(self)
        view._owns_client = False
        view._extra_headers = _end_user_headers(end_user)
        return view

    def request(
        self,
        method: str,
        path: str,
        *,
        idempotent: bool = False,
        raise_for_status: bool = True,
        deadline: float | None = None,
        **kwargs: Any,
    ) -> httpx.Response:
        # POSTs are replayed only when the call carries an Idempotency-Key or
        # the endpoint is idempotent — a bare POST retry could duplicate jobs.
        # raise_for_status=False hands error responses back to the caller;
        # deadline (time.monotonic()) stops retries that would sleep past it.
        retryable = (
            idempotent
            or method.upper() in _ALWAYS_RETRYABLE_METHODS
            or "Idempotency-Key" in (kwargs.get("headers") or {})
        )
        if self._extra_headers:
            kwargs["headers"] = {**self._extra_headers, **(kwargs.get("headers") or {})}
        last_exc: Exception | None = None
        for attempt in range(_MAX_RETRIES):
            try:
                response = self._client.request(method, path, **kwargs)
            except httpx.TransportError as exc:
                if not retryable:
                    raise
                last_exc = exc
                delay = _retry_delay(_RETRY_BACKOFF * (2**attempt))
                if _past(deadline, delay):
                    raise
                time.sleep(delay)
                continue

            self._warn_if_outdated(response)

            if response.status_code in (429, 502, 503, 504):
                retry_after = _parse_retry_after(response)
                if response.status_code == 429:
                    last_exc = RateLimitError(response.text, retry_after=retry_after)
                else:
                    last_exc = APIError(response.status_code, response.text)
                delay = _retry_delay(retry_after if retry_after else _RETRY_BACKOFF * (2**attempt))
                if not retryable or attempt == _MAX_RETRIES - 1 or _past(deadline, delay):
                    if not raise_for_status:
                        return response
                    raise last_exc
                time.sleep(delay)
                continue

            if raise_for_status:
                _raise_for_status(response)
            return response

        raise last_exc  # type: ignore[misc]

    def _warn_if_outdated(self, response: httpx.Response) -> None:
        if self._warn_state["min_version_warned"]:
            return
        minimum = response.headers.get("x-mmdc-min-version")
        if not minimum:
            return
        try:
            outdated = _version_tuple(__version__) < _version_tuple(minimum)
        except ValueError:
            return
        if outdated:
            print(
                f"astro-mmdc {__version__} is below the server minimum {minimum}; "
                f"run: pip install -U astro-mmdc",
                file=sys.stderr,
            )
            self._warn_state["min_version_warned"] = True

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> BaseClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


def _past(deadline: float | None, delay: float) -> bool:
    return deadline is not None and time.monotonic() + delay > deadline


def _end_user_headers(end_user: str | int | None) -> dict[str, str]:
    if end_user is None:
        return {}
    value = str(end_user).strip()
    if not _END_USER_RE.match(value):
        raise ValueError(
            f"end_user must be 1-64 characters from letters, digits and . _ : - "
            f"(an opaque id, not an email); got {end_user!r}"
        )
    return {"X-MMDC-End-User": value}


def _raise_for_status(response: httpx.Response) -> None:
    if response.is_success:
        return

    if response.status_code == 404:
        detail = _extract_detail(response)
        raise NotFoundError(detail)

    if response.status_code == 422:
        body = _try_json(response)
        raise ValidationError(
            message=body.get("error", response.text) if body else response.text,
            validation_type=body.get("validation_type") if body else None,
            details=body if body else {},
        )

    detail = _extract_detail(response)
    raise APIError(response.status_code, detail)


def _extract_detail(response: httpx.Response) -> str:
    body = _try_json(response)
    if body:
        return body.get("error") or body.get("detail") or response.text
    return response.text


def _try_json(response: httpx.Response) -> dict | None:
    try:
        data = response.json()
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _parse_retry_after(response: httpx.Response) -> float | None:
    value = response.headers.get("retry-after")
    if value is None:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None
