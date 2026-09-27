from __future__ import annotations

import time
from typing import Callable

from astro_mmdc._base import BaseClient
from astro_mmdc.exceptions import PollingTimeoutError

# Job statuses the server never leaves; shared by the SED and MADAM resources.
TERMINAL_STATUSES = frozenset({"done", "no_data", "error"})


def poll_until(
    client: BaseClient,
    path: str,
    check: Callable[[dict], bool],
    interval: float = 5.0,
    max_minutes: float = 8.0,
    max_interval: float = 30.0,
    backoff: float = 1.5,
) -> dict:
    """Poll GET ``path`` until ``check(json)`` returns True.

    The delay starts at ``interval`` and grows by ``backoff`` up to
    ``max_interval``; a payload reporting ``queue_position > 1`` jumps the
    delay straight to ``max_interval`` (deep in the queue, no point polling
    fast). Returns the final JSON response dict. Raises
    ``PollingTimeoutError`` after ``max_minutes``.
    """
    deadline = time.monotonic() + max_minutes * 60
    delay = interval
    while True:
        response = client.request("GET", path)
        data = response.json()
        if check(data):
            return data
        if time.monotonic() >= deadline:
            raise PollingTimeoutError(
                f"Polling {path} timed out after {max_minutes} minutes"
            )
        queue_position = data.get("queue_position")
        if isinstance(queue_position, int) and queue_position > 1:
            delay = max_interval
        time.sleep(min(delay, max(0.0, deadline - time.monotonic())))
        delay = min(delay * backoff, max_interval)
