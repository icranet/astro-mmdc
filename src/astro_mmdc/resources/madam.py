from __future__ import annotations

from astro_mmdc._base import BaseClient
from astro_mmdc._polling import TERMINAL_STATUSES, poll_until
from astro_mmdc.exceptions import AnalysisJobError, PollingTimeoutError
from astro_mmdc.models.madam import AnalysisJob, AnalysisSubmission

# A run downloads Swift data and runs HEASoft photometry: minutes to hours.
_DEFAULT_POLL_INTERVAL = 60.0
_DEFAULT_MAX_MINUTES = 240.0


class MadamResource:
    """On-demand Swift UVOT/XRT photometry through the MADAM pipeline.

    Results land in the observations table under ``MMDCOUV`` (UVOT),
    ``MMDCXRT`` and ``MMDCXRT_ORBIT`` (XRT), so a finished job's rows are
    also reachable through ``client.observations``.
    """

    def __init__(self, client: BaseClient) -> None:
        self._client = client

    def submit(
        self,
        ra: float,
        dec: float,
        *,
        mjd_start: float | None = None,
        mjd_end: float | None = None,
        obsids: list[str] | None = None,
        instrument: str = "uvot",
        source_name: str | None = None,
        orbit: bool | None = None,
        force: bool = False,
        limit: int | None = None,
    ) -> AnalysisSubmission:
        """Request an analysis. Returns immediately.

        Exactly one of a time window (``mjd_start`` + ``mjd_end``) or a
        non-empty ``obsids`` list must be given. ``instrument`` is ``"uvot"``
        (default), ``"xrt"`` or ``"swift"`` (both). ``orbit`` toggles per-orbit
        XRT products and is only accepted for ``instrument="xrt"``.

        If the request is already covered by an earlier run the answer comes
        back with ``cached=True`` and the rows in ``results``; otherwise a job
        is queued and ``status`` is ``"processing"``. ``force=True`` bypasses
        the coverage cache. ``limit`` caps the rows of a cached answer.
        """
        if isinstance(obsids, str):
            raise TypeError("obsids must be a list of obsid strings, not a single string.")
        has_window = mjd_start is not None or mjd_end is not None
        if has_window and obsids:
            raise ValueError("Give either mjd_start and mjd_end or obsids, not both.")
        if not has_window and not obsids:
            raise ValueError("Give either mjd_start and mjd_end, or a non-empty obsids list.")
        if has_window and (mjd_start is None or mjd_end is None):
            raise ValueError("mjd_start and mjd_end must be given together.")

        body: dict = {"ra": ra, "dec": dec, "instrument": instrument}
        if has_window:
            body["mjd_start"] = mjd_start
            body["mjd_end"] = mjd_end
        else:
            body["obsids"] = [str(o) for o in obsids or []]
        if source_name is not None:
            body["source_name"] = source_name
        if orbit is not None:
            body["orbit"] = orbit
        if force:
            body["force"] = True
        params = {"limit": limit} if limit is not None else {}

        response = self._client.request(
            "POST", "/api/madam_analysis/", json=body, params=params
        )
        return AnalysisSubmission.model_validate(response.json())

    def get(
        self,
        uuid: str,
        *,
        include_results: bool = True,
        limit: int | None = None,
    ) -> AnalysisJob:
        """Fetch a job. ``include_results=False`` skips the rows for cheap polling."""
        params: dict = {}
        if not include_results:
            params["include_results"] = "false"
        if limit is not None:
            params["limit"] = limit
        response = self._client.request(
            "GET", f"/api/madam_analysis/{uuid}/", params=params
        )
        return AnalysisJob.model_validate(response.json())

    def wait_for_completion(
        self,
        uuid: str,
        poll_interval: float = _DEFAULT_POLL_INTERVAL,
        max_minutes: float = _DEFAULT_MAX_MINUTES,
        limit: int | None = None,
    ) -> AnalysisJob:
        """Poll until the job is done or no_data, then return it with its rows.

        Raises :class:`AnalysisJobError` if the server reports ``error``, and
        :class:`PollingTimeoutError` (carrying ``uuid``) after ``max_minutes``;
        the job keeps running on the server and can be collected later with
        :meth:`get`. Polls without results and fetches them once at the end.
        """

        def _check(d: dict) -> bool:
            status = d.get("status")
            if status == "error":
                raise AnalysisJobError(uuid, status, d.get("logs"))
            return status in TERMINAL_STATUSES

        try:
            poll_until(
                self._client,
                f"/api/madam_analysis/{uuid}/?include_results=false",
                check=_check,
                interval=poll_interval,
                max_minutes=max_minutes,
                max_interval=max(poll_interval, 2 * _DEFAULT_POLL_INTERVAL),
            )
        except PollingTimeoutError as exc:
            raise PollingTimeoutError(
                f"Analysis job {uuid} still running after {max_minutes:g} minutes; "
                f"collect it later with client.madam.get({uuid!r})",
                uuid=uuid,
            ) from exc
        return self.get(uuid, limit=limit)

    def analyze(
        self,
        ra: float,
        dec: float,
        *,
        mjd_start: float | None = None,
        mjd_end: float | None = None,
        obsids: list[str] | None = None,
        instrument: str = "uvot",
        source_name: str | None = None,
        orbit: bool | None = None,
        force: bool = False,
        limit: int | None = None,
        poll_interval: float = _DEFAULT_POLL_INTERVAL,
        max_minutes: float = _DEFAULT_MAX_MINUTES,
    ) -> AnalysisJob:
        """Submit and wait. Same arguments as :meth:`submit`.

        On a cache hit (``job.cached``) the request fields and rows are the
        caller's; the run metadata is the covering job's, which may have been
        wider or a ``swift`` run.
        """
        submission = self.submit(
            ra,
            dec,
            mjd_start=mjd_start,
            mjd_end=mjd_end,
            obsids=obsids,
            instrument=instrument,
            source_name=source_name,
            orbit=orbit,
            force=force,
            limit=limit,
        )
        if submission.cached:
            job = self.get(submission.uuid, include_results=False)
            job.cached = True
            job.instrument = instrument
            if obsids:
                job.mode = "obsid"
                job.mjd_start = job.mjd_end = None
                job.obsids = [str(o) for o in obsids]
            else:
                job.mode = "time_range"
                job.mjd_start, job.mjd_end = mjd_start, mjd_end
                job.obsids = None
            if instrument == "uvot":
                job.xrt_fits = None
            job.count = submission.count
            job.results = submission.results
            job.xrt_observations = submission.xrt_observations
            return job
        return self.wait_for_completion(
            submission.uuid,
            poll_interval=poll_interval,
            max_minutes=max_minutes,
            limit=limit,
        )
