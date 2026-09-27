from __future__ import annotations

import sys
import threading
import time
import warnings
from concurrent.futures import FIRST_EXCEPTION, ThreadPoolExecutor
from concurrent.futures import wait as _wait_futures
from pathlib import Path
from typing import Any, Callable, Iterable, Union

import httpx

from astro_mmdc._base import BaseClient, _parse_retry_after, _try_json
from astro_mmdc._polling import TERMINAL_STATUSES as _TERMINAL_STATUSES
from astro_mmdc._polling import poll_until
from astro_mmdc.exceptions import (
    APIError,
    MMDCError,
    NotFoundError,
    PollingTimeoutError,
    RateLimitError,
    SEDJobFailed,
    SEDNoData,
    SEDNotReady,
    SEDStaleWarning,
    SEDTimeoutError,
    ValidationError,
)
from astro_mmdc.models.sed import (
    SED,
    SEDData,
    SEDError,
    SEDEvent,
    SEDJobInfo,
    SEDProgress,
    SEDRefresh,
    Source,
    SourceInfo,
    SourcePosition,
)

# /api/sed/ statuses a job never leaves.
SED_TERMINAL = frozenset({"done", "no_data", "failed"})
_WAIT_S = 20  # per request; the server caps it at 25
_PROGRESS_WAIT_S = 2  # with a progress callback, so it sees each stage
_DEFAULT_TIMEOUT_S = 900.0
_MIN_INTERVAL_S = 1.0  # between request starts, however early the server answers
_MAX_PAUSE_S = 5.0  # cap on a Retry-After pause between polls

ProgressCallback = Callable[["SEDJob"], None]


class SEDJob:
    """A handle on an SED job from :meth:`SEDResource.submit`.

    ``status`` is ``queued``, ``running``, ``done``, ``no_data`` or
    ``failed``. ``events`` collects every event received so far and
    ``new_events`` the ones from the latest answer. Nothing here talks to the
    server except :meth:`refresh`, :meth:`wait` and :meth:`result`.
    """

    def __init__(self, resource: SEDResource, data: dict, query: dict | None = None) -> None:
        self._resource = resource
        self._query = dict(query or {})
        self._sed: SED | None = None
        self.events: list[SEDEvent] = []
        self.new_events: list[SEDEvent] = []
        self.source: Source | None = None
        self.reused: bool | None = None
        self.stale = False
        self.refresh_info: SEDRefresh | None = None
        self.info: SEDJobInfo | None = None
        self.error: SEDError | None = None
        self._waited = False
        self._retry_after: float | None = None
        self._last_started: float | None = None
        self._last_ended = 0.0
        self._deadline: float | None = None
        self._apply_envelope(data)

    def __repr__(self) -> str:
        return f"<SEDJob {self.id} {self.status}>"

    # -- state ---------------------------------------------------------------

    @property
    def done(self) -> bool:
        """True once the job is ``done``, ``no_data`` or ``failed``."""
        return self.status in SED_TERMINAL

    @property
    def progress(self) -> SEDProgress | None:
        return self.info.progress if self.info else None

    def _apply_envelope(self, data: dict) -> None:
        """A POST or SED GET answer: the job is nested under ``job``."""
        self.id = data["id"]
        self.status = data["status"]
        if data.get("source") is not None:
            self.source = Source.model_validate(data["source"])
        if "reused" in data:
            self.reused = data["reused"]
        self.stale = bool(data.get("stale"))
        if data.get("refresh") is not None:
            self.refresh_info = SEDRefresh.model_validate(data["refresh"])
        self.links = data.get("links") or {}
        job = data.get("job")
        if isinstance(job, dict):
            self._apply_job(job, envelope=True)
        else:
            self.new_events = []
        if data.get("error") is not None:
            self.error = SEDError.model_validate(data["error"])
        if self.status in ("done", "no_data") and "sed" in data:
            self._sed = SED.from_api(data)

    def _apply_job(self, job: dict, envelope: bool = False) -> None:
        self.info = SEDJobInfo.model_validate(job)
        if not envelope:
            self.id = self.info.id
            self.status = self.info.status
        # Indexes are contiguous and we always ask from len(events), so append.
        self.new_events = [SEDEvent.model_validate(e) for e in job.get("events") or []]
        self.events.extend(self.new_events)
        if self.info.error is not None:
            self.error = self.info.error

    # -- talking to the server -----------------------------------------------

    def refresh(self, wait: float = 0) -> SEDJob:
        """One GET of the job (only new events); ``wait`` seconds of server-side wait."""
        started = time.monotonic()
        response, data = self._resource._call(
            "GET",
            f"/api/sed/jobs/{self.id}/",
            params={"events_since": len(self.events)},
            wait=wait,
            deadline=self._deadline,
        )
        self._note_pacing(response, wait, started)
        self._apply_job(data)
        return self

    def wait(
        self,
        timeout: float | None = _DEFAULT_TIMEOUT_S,
        progress: ProgressCallback | bool | None = None,
    ) -> SEDJob:
        """Block until the job is terminal; raises :class:`SEDTimeoutError` after ``timeout`` s.

        Uses the server's bounded wait and falls back to polling every 1-2 s
        when the server answers early. ``progress`` is called with this job
        after every answer; ``True`` prints the events to stderr.
        """
        notify = _progress_callback(progress)
        deadline = None if timeout is None else time.monotonic() + timeout
        self._deadline = deadline
        try:
            while not self.done:
                self._pause(deadline)
                remaining = None if deadline is None else deadline - time.monotonic()
                if remaining is not None and remaining <= 0:
                    raise SEDTimeoutError(
                        f"SED job {self.id} is still {self.status} after {timeout:g} s; "
                        f"pick it up later with client.sed.job({self.id!r})",
                        id=self.id,
                    )
                step = _PROGRESS_WAIT_S if notify else _WAIT_S
                wait = step if remaining is None else int(min(step, remaining))
                self.refresh(wait=wait)
                if notify:
                    notify(self)
        finally:
            self._deadline = None
        return self

    def _pause(self, deadline: float | None) -> None:
        """Space requests: at once after a server-side wait, else after Retry-After."""
        if self._last_started is None:
            return
        now = time.monotonic()
        if self._waited:
            pause = _MIN_INTERVAL_S - (now - self._last_started)
        else:
            pause = min(self._retry_after or 2.0, _MAX_PAUSE_S) - (now - self._last_ended)
        if deadline is not None:
            pause = min(pause, deadline - now)
        if pause > 0:
            time.sleep(pause)

    def result(
        self,
        timeout: float | None = _DEFAULT_TIMEOUT_S,
        progress: ProgressCallback | bool | None = None,
    ) -> SED:
        """Wait for the job and return its SED.

        Raises :class:`SEDNoData` (with the empty SED on ``.sed``),
        :class:`SEDJobFailed` or :class:`SEDTimeoutError`.
        """
        self.wait(timeout=timeout, progress=progress)
        if self.status == "failed":
            stale = self._previous_sed()
            if stale is not None:
                return stale
        self._raise_if_failed()
        if self._sed is None:
            _, data = self._resource._call("GET", f"/api/sed/{self.id}/", params=self._query)
            if data.get("status") not in ("done", "no_data"):
                job = SEDJob(self._resource, data, self._query)
                job._raise_if_failed()
                raise APIError(202, f"SED {self.id} is not ready ({data.get('status')})")
            self._sed = SED.from_api(data)
            if self._sed.job is None and self.info is not None:
                self._sed.job = self.info
        if self._sed.status == "no_data" and self._sed.has_points:
            raise SEDNoData(self._sed.id, self._sed)
        return self._sed

    def _previous_sed(self) -> SED | None:
        """After a failed refresh: the SED it was refreshing, marked stale (the spec's rule)."""
        old_id = self.info.refresh_of if self.info else None
        if not old_id:
            return None
        try:
            _, data = self._resource._call("GET", f"/api/sed/{old_id}/", params=self._query)
        except MMDCError:
            return None
        if data.get("status") != "done":
            return None
        err = self.error or SEDError(code="failed", message="The run failed.")
        sed = SED.from_api(data)
        sed = sed.model_copy(update={
            "stale": True,
            "refresh": sed.refresh or SEDRefresh(id=self.id, status="failed", error=err),
        })
        warnings.warn(
            f"SED refresh {self.id} failed ({err.code}); returning the previous SED "
            f"{sed.id}, marked stale",
            SEDStaleWarning,
            stacklevel=4,
        )
        return sed

    def _raise_if_failed(self) -> None:
        if self.status == "failed":
            err = self.error or SEDError(code="failed", message="The run failed.")
            raise SEDJobFailed(self.id, err.code, err.message, err.retry_after_s)

    def _note_pacing(self, response: httpx.Response, wait: float, started: float) -> None:
        self._waited = bool(wait) and "preference-applied" in response.headers
        self._retry_after = _parse_retry_after(response)
        self._last_started = started
        self._last_ended = time.monotonic()


def _progress_callback(progress: ProgressCallback | bool | None) -> ProgressCallback | None:
    if progress is True:
        return _print_progress
    if not progress:
        return None
    return progress  # type: ignore[return-value]


def _print_progress(job: SEDJob) -> None:
    for event in job.new_events:
        print(event.render(), file=sys.stderr)


SourceSpec = Union[tuple, dict, Any]


def _source_args(src: SourceSpec) -> tuple[Any, Any, str | None]:
    if isinstance(src, dict):
        return src["ra"], src["dec"], src.get("name")
    if isinstance(src, (tuple, list)):
        return src[0], src[1], src[2] if len(src) > 2 else None
    return src.ra, src.dec, getattr(src, "name", None)


def _deg(value: Any) -> float:
    """Degrees as a float, from a number, an astropy Angle or a Quantity."""
    if hasattr(value, "deg"):
        value = value.deg
    elif hasattr(value, "to_value"):
        value = value.to_value("deg")
    return float(value)


def _position(ra: Any, dec: Any) -> tuple[float, float]:
    if dec is None and hasattr(ra, "ra") and hasattr(ra, "dec"):  # a SkyCoord
        ra, dec = ra.ra, ra.dec
    if dec is None:
        raise TypeError("dec is required unless ra is a SkyCoord")
    return _deg(ra), _deg(dec)


class _Cancelled(Exception):
    """Stops a get_many worker after another source failed."""


def _filter_params(
    mjd_start: float | None,
    mjd_end: float | None,
    catalogs: Iterable[str] | None,
    undated: bool | None,
) -> dict:
    params: dict = {}
    if mjd_start is not None:
        params["mjd_start"] = mjd_start
    if mjd_end is not None:
        params["mjd_end"] = mjd_end
    if catalogs is not None:
        params["catalogs"] = ",".join(catalogs)
    if undated is not None:
        params["undated"] = "true" if undated else "false"
    return params


class SEDResource:
    def __init__(self, client: BaseClient) -> None:
        self._client = client

    # -- /api/sed/ (v1) --------------------------------------------------------

    def get(
        self,
        ra: float,
        dec: float | None = None,
        name: str | None = None,
        *,
        refresh: bool = False,
        progress: ProgressCallback | bool | None = None,
        timeout: float | None = _DEFAULT_TIMEOUT_S,
        mjd_start: float | None = None,
        mjd_end: float | None = None,
        catalogs: Iterable[str] | None = None,
        undated: bool | None = None,
    ) -> SED:
        """The SED at a sky position, running the pipeline if we have none yet.

        Most sources are cached and come back in one request. A new source
        takes up to a few minutes; ``progress`` is called with the
        :class:`SEDJob` after every answer (``True`` prints the job's log).
        ``refresh=True`` starts a new run even when a result exists; if that
        run fails, the previous SED comes back with ``stale=True`` and a
        :class:`SEDStaleWarning`. The MJD/catalogue filters are applied by
        the server. ``ra``/``dec`` are degrees (floats, astropy Angles), or
        pass an astropy ``SkyCoord`` as ``ra``.

        Raises :class:`SEDNoData`, :class:`SEDJobFailed` or
        :class:`SEDTimeoutError` (carrying the job ``id``); never blocks past
        ``timeout``.
        """
        started = time.monotonic()
        deadline = None if timeout is None else started + timeout
        job = self._submit(
            ra, dec, name, refresh=refresh, wait=_initial_wait(timeout, bool(progress)), sed=True,
            query=_filter_params(mjd_start, mjd_end, catalogs, undated), deadline=deadline,
        )
        _raise_if_enqueue_timed_out(job, deadline, timeout)
        notify = _progress_callback(progress)
        if notify:
            notify(job)
        return job.result(timeout=_left(timeout, started), progress=notify)

    def submit(
        self,
        ra: float,
        dec: float | None = None,
        name: str | None = None,
        *,
        refresh: bool = False,
        wait: float = 0,
        sed: bool = True,
        mjd_start: float | None = None,
        mjd_end: float | None = None,
        catalogs: Iterable[str] | None = None,
        undated: bool | None = None,
    ) -> SEDJob:
        """Create or reuse the SED job for a position; returns a :class:`SEDJob` at once.

        ``wait`` (seconds, at most 25) lets the server hold the answer until
        the job ends. A job within 2″ is reused. The filters apply to the
        SED that :meth:`SEDJob.result` returns.
        """
        return self._submit(
            ra, dec, name, refresh=refresh, wait=wait, sed=sed,
            query=_filter_params(mjd_start, mjd_end, catalogs, undated), deadline=None,
        )

    def _submit(
        self,
        ra: Any,
        dec: Any,
        name: str | None,
        *,
        refresh: bool,
        wait: float,
        sed: bool,
        query: dict,
        deadline: float | None,
    ) -> SEDJob:
        ra, dec = _position(ra, dec)
        body: dict = {"ra": ra, "dec": dec}
        if name is not None:
            body["name"] = name
        if refresh:
            body["refresh"] = True
        if not sed:
            query = {**query, "sed": "false"}
        started = time.monotonic()
        response, data = self._call(
            "POST", "/api/sed/", json=body, params=query, wait=wait, deadline=deadline
        )
        job = SEDJob(self, data, query)
        job._note_pacing(response, wait, started)
        if response.status_code == 503 and job.error is not None:
            header = _parse_retry_after(response)
            if header is not None:
                job.error.retry_after_s = max(job.error.retry_after_s or 0, int(header))
        return job

    def get_many(
        self,
        sources: Iterable[SourceSpec],
        *,
        max_concurrency: int = 2,
        refresh: bool = False,
        timeout: float | None = _DEFAULT_TIMEOUT_S,
        return_exceptions: bool = False,
        **filters: Any,
    ) -> list[Any]:
        """:meth:`get` for many positions, ``max_concurrency`` at a time.

        ``sources`` items are ``(ra, dec)`` / ``(ra, dec, name)`` tuples,
        dicts with ``ra``, ``dec`` and optional ``name``, or objects with
        those attributes. Results come back in input order. With
        ``return_exceptions=True`` a failed source gives its exception
        (e.g. :class:`SEDNoData`) in its slot instead of raising; otherwise
        the first failure is raised at once and the other sources stop (a
        job already running on the server keeps running there).
        An astropy ``SkyCoord`` (scalar) works as an item too.
        """
        specs = [_source_args(s) for s in sources]
        stop = threading.Event()

        def check(job: SEDJob) -> None:
            if stop.is_set():
                raise _Cancelled()

        def one(spec: tuple[Any, Any, str | None]) -> Any:
            if stop.is_set():
                raise _Cancelled()
            ra, dec, name = spec
            try:
                return self.get(ra, dec, name, refresh=refresh, timeout=timeout,
                                progress=check, **filters)
            except _Cancelled:
                raise
            except Exception as exc:  # noqa: BLE001 - handed back to the caller
                if not return_exceptions:
                    stop.set()  # before this worker can pick up the next source
                    raise
                return exc

        pool = ThreadPoolExecutor(max_workers=max(1, max_concurrency))
        try:
            futures = [pool.submit(one, spec) for spec in specs]
            done, _ = _wait_futures(futures, return_when=FIRST_EXCEPTION)
            failed = [f for f in futures if f in done and f.exception() is not None]
            if failed:
                stop.set()
                raise failed[0].exception()  # type: ignore[misc]
            return [f.result() for f in futures]
        finally:
            stop.set()
            pool.shutdown(wait=False, cancel_futures=True)

    def source(
        self,
        ra: float,
        dec: float | None = None,
        name: str | None = None,
        *,
        refresh: bool = False,
        timeout: float | None = _DEFAULT_TIMEOUT_S,
    ) -> Source:
        """Source info only (redshift, synchrotron peak), without the points.

        Waits for the job like :meth:`get`, since the redshift is looked up
        during the run. A ``no_data`` position still returns its source.
        """
        started = time.monotonic()
        deadline = None if timeout is None else started + timeout
        job = self._submit(ra, dec, name, refresh=refresh, wait=_initial_wait(timeout),
                           sed=False, query={}, deadline=deadline)
        _raise_if_enqueue_timed_out(job, deadline, timeout)
        if not job.done:
            job.wait(timeout=_left(timeout, started))
            job._raise_if_failed()
            _, data = self._call("GET", f"/api/sed/{job.id}/", params={"sed": "false"})
            return Source.model_validate(data["source"])
        job._raise_if_failed()
        assert job.source is not None
        return job.source

    def job(self, id: str, *, wait: float = 0) -> SEDJob:
        """The job with this id (status, progress, all its events)."""
        started = time.monotonic()
        response, data = self._call("GET", f"/api/sed/jobs/{id}/", wait=wait)
        job = SEDJob(self, {"id": data["id"], "status": data["status"], "job": data})
        job._note_pacing(response, wait, started)
        return job

    def fetch(
        self,
        id: str,
        *,
        timeout: float | None = _DEFAULT_TIMEOUT_S,
        progress: ProgressCallback | bool | None = None,
        mjd_start: float | None = None,
        mjd_end: float | None = None,
        catalogs: Iterable[str] | None = None,
        undated: bool | None = None,
    ) -> SED:
        """The SED of job ``id``, waiting for the job if it is still running.

        A job replaced by a refresh answers with the current SED (new ``id``).
        """
        query = _filter_params(mjd_start, mjd_end, catalogs, undated)
        _, data = self._call("GET", f"/api/sed/{id}/", params=query)
        return SEDJob(self, data, query).result(timeout=timeout, progress=progress)

    def csv(
        self,
        id: str,
        dest: str | Path | None = None,
        *,
        mjd_start: float | None = None,
        mjd_end: float | None = None,
        catalogs: Iterable[str] | None = None,
        undated: bool | None = None,
    ) -> str:
        """The server's CSV of a finished SED; also written to ``dest`` if given.

        Raises :class:`SEDNotReady` while the job runs and :class:`SEDJobFailed`
        for a failed job.
        """
        params = {"format": "csv", **_filter_params(mjd_start, mjd_end, catalogs, undated)}
        response, _ = self._call("GET", f"/api/sed/{id}/", params=params, parse=False)
        if dest is not None:
            Path(dest).write_bytes(response.content)
        return response.text

    def _call(
        self,
        method: str,
        path: str,
        *,
        wait: float = 0,
        parse: bool = True,
        deadline: float | None = None,
        **kwargs: Any,
    ) -> tuple[httpx.Response, dict]:
        """One request to /api/sed/; maps the spec's error answers to exceptions."""
        headers = dict(kwargs.pop("headers", None) or {})
        wait = int(max(0, min(wait, 25)))
        if wait:
            headers["Prefer"] = f"wait={wait}"
            base = self._client._client.timeout
            if base.read is not None:
                kwargs["timeout"] = httpx.Timeout(
                    connect=base.connect, read=base.read + wait, write=base.write, pool=base.pool
                )
        response = self._client.request(
            method, path, headers=headers, idempotent=True, raise_for_status=False,
            deadline=deadline, **kwargs,
        )
        body = _try_json(response) or {}
        status = response.status_code
        if status == 503 and "id" in body:
            return response, body  # enqueue failure: a failed job, see submit()
        if status >= 400:
            err = body.get("error") if isinstance(body.get("error"), dict) else {}
            message = err.get("message") or response.text
            if status == 400:
                raise ValidationError(
                    message, validation_type=err.get("code"), details=err.get("fields") or {}
                )
            job_id = path.rstrip("/").rsplit("/", 1)[-1]
            if status == 404:
                raise NotFoundError(message)
            if status == 409 and err.get("code") == "failed":
                raise SEDJobFailed(job_id, "failed", message)
            if status == 409:
                raise SEDNotReady(job_id, message)
            if status == 429:
                raise RateLimitError(message, retry_after=_parse_retry_after(response))
            raise APIError(status, message)
        return response, (body if parse else {})

    def prepare(
        self,
        ra: float,
        dec: float,
        database_name: str,
        source_name: str | None = None,
        force: bool = False,
    ) -> SourcePosition:
        """Submit an SED data preparation job.

        Returns immediately with the job's UUID and initial status.
        """
        params = {"force": "true"} if force else {}
        body: dict = {"ra": ra, "dec": dec, "database_name": database_name}
        if source_name is not None:
            body["source_name"] = source_name

        response = self._client.request(
            "POST", "/api/vou_json/", json=body, params=params
        )
        data = response.json()

        # 201 returns {"status": "created", "uuid": "..."} — normalise to full shape
        if response.status_code == 201:
            return SourcePosition(
                uuid=data["uuid"],
                source_name=source_name,
                database_name=database_name,
                ra=ra,
                dec=dec,
                status="processing",
                logs=None,
            )
        return SourcePosition.model_validate(data)

    def get_status(self, uuid: str) -> SourcePosition:
        """Check the status of an SED preparation job."""
        response = self._client.request("GET", f"/api/vou_json/{uuid}/")
        return SourcePosition.model_validate(response.json())

    def wait_for_completion(
        self,
        uuid: str,
        poll_interval: float = 5.0,
        max_minutes: float = 15.0,
        raise_on_error: bool = False,
    ) -> SourcePosition:
        """Poll until the SED job reaches a terminal status (done/no_data/error).

        An ``error`` status is returned unless ``raise_on_error=True``, which
        raises :class:`SEDJobFailed`. A timeout raises
        :class:`PollingTimeoutError` carrying ``uuid``.
        """
        try:
            data = poll_until(
                self._client,
                f"/api/vou_json/{uuid}/",
                check=lambda d: d.get("status") in _TERMINAL_STATUSES,
                interval=poll_interval,
                max_minutes=max_minutes,
            )
        except PollingTimeoutError as exc:
            raise PollingTimeoutError(
                f"SED job {uuid} still processing after {max_minutes:g} minutes; "
                f"check it later with client.sed.get_status({uuid!r})",
                uuid=uuid,
            ) from exc
        job = SourcePosition.model_validate(data)
        if raise_on_error:
            _raise_old_error(job)
        return job

    def prepare_and_wait(
        self,
        ra: float,
        dec: float,
        database_name: str,
        source_name: str | None = None,
        force: bool = False,
        poll_interval: float = 5.0,
        max_minutes: float = 15.0,
        raise_on_error: bool = False,
    ) -> SourcePosition:
        """Submit an SED job and wait until it completes.

        Prefer :meth:`get`. ``raise_on_error`` as in :meth:`wait_for_completion`.
        """
        job = self.prepare(ra, dec, database_name, source_name=source_name, force=force)
        if job.status in _TERMINAL_STATUSES:
            if raise_on_error:
                _raise_old_error(job)
            return job
        return self.wait_for_completion(
            job.uuid, poll_interval=poll_interval, max_minutes=max_minutes,
            raise_on_error=raise_on_error,
        )

    def get_data(
        self,
        uuid: str,
        *,
        mjd_start: float | None = None,
        mjd_end: float | None = None,
        exclude_catalogs: list[str] | None = None,
        exclude_freq_ranges: list[str] | None = None,
        x_axis: str | None = None,
        y_axis: str | None = None,
    ) -> SEDData:
        """Retrieve SED frequency/flux data for a completed job."""
        params: dict = {}
        if mjd_start is not None:
            params["mjd_start"] = mjd_start
        if mjd_end is not None:
            params["mjd_end"] = mjd_end
        if exclude_catalogs:
            params["exclude_catalogs"] = exclude_catalogs
        if exclude_freq_ranges:
            params["exclude_freq_ranges"] = exclude_freq_ranges
        if x_axis is not None:
            params["x_axis"] = x_axis
        if y_axis is not None:
            params["y_axis"] = y_axis

        response = self._client.request("GET", f"/api/freq_flux_data/{uuid}/", params=params)
        return SEDData.model_validate(response.json())

    def get_info(self, uuid: str) -> SourceInfo:
        """Get source metadata (coordinates, redshift, etc.)."""
        response = self._client.request("GET", f"/api/source_info/{uuid}/")
        return SourceInfo.model_validate(response.json())

    def download_csv(
        self,
        uuid: str,
        dest: str | Path,
        *,
        mjd_start: float | None = None,
        mjd_end: float | None = None,
        exclude_catalogs: list[str] | None = None,
        exclude_freq_ranges: list[str] | None = None,
        x_axis: str | None = None,
        y_axis: str | None = None,
    ) -> Path:
        """Download SED data as a CSV file."""
        params: dict = {}
        if mjd_start is not None:
            params["mjd_start"] = mjd_start
        if mjd_end is not None:
            params["mjd_end"] = mjd_end
        if exclude_catalogs:
            params["exclude_catalogs"] = exclude_catalogs
        if exclude_freq_ranges:
            params["exclude_freq_ranges"] = exclude_freq_ranges
        if x_axis is not None:
            params["x_axis"] = x_axis
        if y_axis is not None:
            params["y_axis"] = y_axis

        response = self._client.request("GET", f"/api/csv/{uuid}/", params=params)
        dest_path = Path(dest)
        dest_path.write_bytes(response.content)
        return dest_path


def _raise_old_error(job: SourcePosition) -> None:
    if job.status == "error":
        raise SEDJobFailed(job.uuid, "failed", (job.logs or "The run failed.").strip()[-2000:])


def _raise_if_enqueue_timed_out(
    job: SEDJob, deadline: float | None, timeout: float | None
) -> None:
    """A 503 whose retry would outlast the caller's timeout is a timeout, not a failure."""
    if job.status != "failed" or job.error is None or job.error.code != "enqueue":
        return
    if deadline is None or deadline - time.monotonic() >= (job.error.retry_after_s or 0):
        return
    raise SEDTimeoutError(
        f"SED job {job.id} could not be queued yet and the {timeout:g} s timeout leaves no "
        f"time to retry (the server asks for {job.error.retry_after_s} s)",
        id=job.id,
    )


def _initial_wait(timeout: float | None, progress: bool = False) -> float:
    step = _PROGRESS_WAIT_S if progress else _WAIT_S
    return step if timeout is None else max(0.0, min(step, timeout))


def _left(timeout: float | None, started: float) -> float | None:
    if timeout is None:
        return None
    return max(0.0, timeout - (time.monotonic() - started))
