from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from astro_mmdc.models.observations import Observation


class XrtPowerLaw(BaseModel):
    index: float | None = None
    index_err: float | None = None
    flux_2_10: float | None = None
    flux_2_10_err: float | None = None
    flux_05_2: float | None = None
    flux_05_2_err: float | None = None
    stat: float | None = None
    dof: int | None = None
    null_prob: float | None = None


class XrtLogParabola(BaseModel):
    alpha: float | None = None
    alpha_err: float | None = None
    beta: float | None = None
    beta_err: float | None = None
    flux_2_10: float | None = None
    flux_2_10_err: float | None = None
    flux_05_2: float | None = None
    flux_05_2_err: float | None = None
    stat: float | None = None
    dof: int | None = None
    null_prob: float | None = None


class XrtFits(BaseModel):
    # None when that model was not fitted.
    powerlaw: XrtPowerLaw | None = None
    logparabola: XrtLogParabola | None = None


class XrtObservation(BaseModel):
    """One XRT obsid: both spectral fits and its MMDCXRT/MMDCXRT_ORBIT points.

    ``delta_stat`` is ``powerlaw.stat - logparabola.stat``; ``preferred_model``
    is the server's verdict on it and may be None.
    """

    obsid: str
    mjd: float | None = None
    datamode: str | None = None
    stat_type: str | None = None
    delta_stat: float | None = None
    preferred_model: str | None = None
    # None for an obsid analysed before the fit table existed.
    fits: XrtFits | None = None
    points: list[Observation] = []


class AnalysisSubmission(BaseModel):
    """Answer to a POST. ``cached=True`` means the rows are already in
    ``results`` and no run was queued."""

    uuid: str
    status: str
    cached: bool
    count: int | None = None
    results: list[Observation] | None = None
    xrt_observations: list[XrtObservation] | None = None


class AnalysisJob(BaseModel):
    uuid: str
    status: str
    source_name: str | None = None
    ra: float
    dec: float
    sky_identifier: int
    mode: str
    instrument: str
    orbit: bool = True
    mjd_start: float | None = None
    mjd_end: float | None = None
    obsids: list[str] | None = None
    # XRT spectral fit table; never part of `results`.
    xrt_fits: list[dict] | None = None
    rows_ingested: int | None = None
    # None on a job that was covered by a wider run before it started.
    exit_code: int | None = None
    created_at: datetime
    finished_at: datetime | None = None

    # True when analyze() was answered from the coverage cache: the run
    # metadata below (created_at, rows_ingested, xrt_fits, ...) is the covering
    # job's, while the request fields and results are the caller's.
    cached: bool = False

    # Present on done/no_data unless include_results=False.
    count: int | None = None
    results: list[Observation] | None = None
    # XRT/swift only, alongside results; not capped by limit.
    xrt_observations: list[XrtObservation] | None = None
    # Tail of the container log, present only when status is "error".
    logs: str | None = None

    @property
    def is_finished(self) -> bool:
        return self.status in ("done", "no_data", "error")
