from __future__ import annotations


class MMDCError(Exception):
    """Base exception for all MMDC SDK errors."""


class APIError(MMDCError):
    """Raised when the API returns a non-2xx response."""

    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"HTTP {status_code}: {detail}")


class NotFoundError(APIError):
    """Raised on 404 responses."""

    def __init__(self, detail: str = "Not found") -> None:
        super().__init__(404, detail)


class RateLimitError(APIError):
    """Raised when the API returns 429 Too Many Requests after retries are exhausted."""

    def __init__(self, detail: str = "Rate limit exceeded", retry_after: float | None = None) -> None:
        self.retry_after = retry_after
        super().__init__(429, detail)


class ValidationError(MMDCError):
    """Raised when CSV or parameter validation fails (422)."""

    def __init__(
        self,
        message: str,
        validation_type: str | None = None,
        details: dict | None = None,
    ) -> None:
        self.validation_type = validation_type
        self.details = details or {}
        super().__init__(message)


class PollingTimeoutError(MMDCError):
    """Raised when polling exceeds the maximum wait time.

    ``uuid`` identifies the job when the caller has one, so a still-running
    job can be picked up again later.
    """

    def __init__(self, message: str, uuid: str | None = None) -> None:
        self.uuid = uuid
        super().__init__(message)


class BatchJobError(MMDCError):
    """Raised when a batch inference job reaches a terminal failure state on the server."""

    def __init__(self, batch_result_id: str, status: str) -> None:
        self.batch_result_id = batch_result_id
        self.status = status
        super().__init__(
            f"Batch job {batch_result_id} ended with status={status!r}"
        )


class AnalysisJobError(MMDCError):
    """Raised when a Swift/MADAM analysis job ends in the ``error`` state."""

    def __init__(self, uuid: str, status: str, logs: str | None = None) -> None:
        self.uuid = uuid
        self.status = status
        self.logs = logs
        tail = f"\n{logs.rstrip()}" if logs else ""
        super().__init__(f"Analysis job {uuid} ended with status={status!r}{tail}")


class SEDTimeoutError(PollingTimeoutError, TimeoutError):
    """Raised when an SED job is still running at the caller's timeout.

    The job keeps running on the server; ``id`` (also ``uuid``) picks it up
    again with ``client.sed.job(id)`` or ``client.sed.fetch(id)``.
    """

    def __init__(self, message: str, id: str | None) -> None:
        self.id = id
        super().__init__(message, uuid=id)

    def __reduce__(self) -> tuple:
        return (type(self), (self.args[0], self.id))


class SEDJobFailed(MMDCError):
    """Raised when an SED job ends ``failed``.

    ``code`` is the server's stable error code (``pipeline``, ``timeout``,
    ``abandoned``, ``enqueue``, ``internal``, ``empty_refresh``, ``failed``);
    ``retry_after_s`` is how long until a POST without ``refresh`` runs again.
    """

    def __init__(
        self, id: str | None, code: str, message: str, retry_after_s: int | None = None
    ) -> None:
        self.id = id
        self.code = code
        self.message = message
        self.retry_after_s = retry_after_s
        super().__init__(f"SED job {id} failed ({code}): {message}")

    def __reduce__(self) -> tuple:
        return (type(self), (self.id, self.code, self.message, self.retry_after_s))


class SEDNoData(MMDCError):
    """Raised when an SED job finished and found no points.

    ``sed`` is the empty result; its ``source`` is still filled in.
    """

    def __init__(self, id: str, sed: object | None = None) -> None:
        self.id = id
        self.sed = sed
        super().__init__(f"SED job {id} found no data at this position")

    def __reduce__(self) -> tuple:
        return (type(self), (self.id, self.sed))


class SEDNotReady(APIError):
    """Raised (HTTP 409) when the CSV of a job that is still running is asked for."""

    def __init__(self, id: str, detail: str = "The SED is not ready.") -> None:
        self.id = id
        super().__init__(409, detail)

    def __reduce__(self) -> tuple:
        return (type(self), (self.id, self.detail))


class SEDStaleWarning(UserWarning):
    """A refresh failed and the previous SED was returned, marked ``stale``."""
