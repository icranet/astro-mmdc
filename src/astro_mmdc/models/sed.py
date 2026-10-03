from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field, model_validator

from astro_mmdc import units as _units


class SourcePosition(BaseModel):
    uuid: str
    source_name: str | None = None
    database_name: str
    ra: float
    dec: float
    status: str
    logs: str | None = None


class SourceInfo(BaseModel):
    source_name: str | None = None
    ra: float
    dec: float
    gal_lat: float
    gal_long: float
    redshift: float | None = None
    W_peak: str


class SEDData(BaseModel):
    uuid: str
    source_name: str | None = None
    database_name: str
    ra: float
    dec: float
    data: dict


# --- /api/sed/ (v1) -------------------------------------------------------


class WPeak(BaseModel):
    """Synchrotron peak: ``log_nu`` is log10(ν_peak / Hz); ``limit`` is ``lower``/``upper``/None."""

    log_nu: float
    err: float | None = None
    limit: str | None = None
    text: str = ""


class Source(BaseModel):
    name: str = ""
    ra: float
    dec: float
    gal_l: float | None = None
    gal_b: float | None = None
    redshift: float | None = None
    w_peak: WPeak | None = None


class SEDStageProgress(BaseModel):
    done: int
    total: int
    elapsed_s: float | None = None


class SEDProgress(BaseModel):
    """Latest progress of a running job.

    ``stage``/``done``/``total`` are the headline for one progress bar
    (phase1, phase2, lightcurves, finishing); ``stages`` has every stage
    reported so far, since light curves run beside phase 2.
    """

    stage: str
    done: int
    total: int
    elapsed_s: float | None = None
    stages: dict[str, SEDStageProgress] = Field(default_factory=dict)


class SEDEvent(BaseModel):
    """One structured log line of a job (events v1), kept in arrival order.

    ``t`` can step back ~0.1 s between neighbours; do not sort by it.
    ``points`` is the search's entries on a ``catalog`` event and the SED
    points stored on the ``summary`` event.
    """

    v: int = 1
    t: float | None = None
    level: str = "info"
    kind: str | None = None
    phase: str | None = None
    subject: str = ""
    outcome: str | None = None
    points: int | None = None
    source: str | None = None
    duration_s: float | None = None
    names: list[str] | None = None
    done: int | None = None
    total: int | None = None
    text: str = ""

    def render(self) -> str:
        """The line as the job's ``logs`` show it: ``[mm:ss] LEVEL  Subject  text``."""
        m, s = divmod(int(self.t or 0), 60)
        return f"[{m:02d}:{s:02d}] {self.level.upper():<5}  {self.subject:<12}  {self.text}"


class SEDError(BaseModel):
    code: str
    message: str = ""
    retry_after_s: int | None = None


class SEDRefresh(BaseModel):
    """A refresh run of this SED: running, or failed (then the SED is ``stale``)."""

    id: str
    status: str
    error: SEDError | None = None
    links: dict[str, str] = Field(default_factory=dict)


class SEDJobInfo(BaseModel):
    id: str
    status: str
    created_at: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    elapsed_s: float | None = None
    refresh_of: str | None = None
    replaced_by: str | None = None
    progress: SEDProgress | None = None
    events_next: int = 0
    events_truncated: bool | None = None
    missed_catalogs: list[str] | None = None
    error: SEDError | None = None
    links: dict[str, str] = Field(default_factory=dict)


class SEDCatalog(BaseModel):
    name: str
    band: str | None = None
    reference: str | None = None
    color: str | None = None


UNDATED_MJD = 50000.0
"""``mjd_start`` = ``mjd_end`` of an undated catalogue value."""

_COLUMNS = (
    "freq_hz", "nufnu", "nufnu_err", "is_ul", "mjd_start", "mjd_end", "undated", "catalog_idx",
)
CSV_HEADER = (
    "freq_hz", "nufnu", "nufnu_err", "is_ul", "mjd_start", "mjd_end",
    "catalog", "band", "reference",
)


class SED(BaseModel):
    """An SED from ``/api/sed/``: the source, its job and the points as columns.

    Columns are plain lists (one entry per point, ``None`` where missing):
    ``freq_hz`` (Hz), ``nufnu`` (erg cm⁻² s⁻¹; the limit for an upper limit),
    ``nufnu_err``, ``is_ul``, ``mjd_start``/``mjd_end`` (both 50000 for an
    undated catalogue value), ``undated`` (True for those) and ``catalog_idx``
    into :attr:`catalogs`.
    """

    id: str
    status: str
    reused: bool | None = None
    stale: bool = False
    refresh: SEDRefresh | None = None
    source: Source
    job: SEDJobInfo | None = None
    has_points: bool = Field(
        True, description="False when the answer was asked for without points (sed=false)."
    )
    units: dict[str, str] = Field(default_factory=dict)
    filters: dict[str, Any] = Field(default_factory=dict)
    catalogs: list[SEDCatalog] = Field(default_factory=list)
    freq_hz: list[Optional[float]] = Field(default_factory=list)
    nufnu: list[Optional[float]] = Field(default_factory=list)
    nufnu_err: list[Optional[float]] = Field(default_factory=list)
    is_ul: list[bool] = Field(default_factory=list)
    mjd_start: list[Optional[float]] = Field(default_factory=list)
    mjd_end: list[Optional[float]] = Field(default_factory=list)
    undated: list[bool] = Field(default_factory=list)
    catalog_idx: list[int] = Field(default_factory=list)
    links: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _fill_undated(self) -> SED:
        # Older servers send no undated column: derive it from the MJDs.
        if len(self.undated) != len(self.mjd_start):
            self.undated = [_undated(s, e) for s, e in zip(self.mjd_start, self.mjd_end)]
        return self

    @classmethod
    def from_api(cls, data: dict) -> SED:
        """Build from a POST /api/sed/ or GET /api/sed/<id>/ answer."""
        sed = data.get("sed")
        fields: dict[str, Any] = {
            k: data.get(k) for k in ("id", "status", "reused", "refresh", "source", "job", "links")
        }
        fields["stale"] = bool(data.get("stale"))
        fields["has_points"] = isinstance(sed, dict)
        if isinstance(sed, dict):
            for key in ("units", "filters", "catalogs", *_COLUMNS):
                if sed.get(key) is not None:
                    fields[key] = sed[key]
        return cls.model_validate({k: v for k, v in fields.items() if v is not None})

    # -- reading -----------------------------------------------------------

    @property
    def points(self) -> int:
        return len(self.freq_hz)

    def __len__(self) -> int:
        return self.points

    @property
    def catalog(self) -> list[str]:
        """The catalogue name of every point."""
        names = [c.name for c in self.catalogs]
        return [names[i] for i in self.catalog_idx]

    @property
    def is_undated(self) -> list[bool]:
        """The :attr:`undated` column: True for every undated catalogue value."""
        return self.undated

    @property
    def missed_catalogs(self) -> list[str] | None:
        """Catalogues that could not be queried in this run (a refresh may help)."""
        return self.job.missed_catalogs if self.job else None

    def rows(self) -> list[dict[str, Any]]:
        """One dict per point, with the CSV's columns."""
        out = []
        for i in range(self.points):
            cat = self.catalogs[self.catalog_idx[i]]
            out.append({
                "freq_hz": self.freq_hz[i],
                "nufnu": self.nufnu[i],
                "nufnu_err": self.nufnu_err[i],
                "is_ul": self.is_ul[i],
                "mjd_start": self.mjd_start[i],
                "mjd_end": self.mjd_end[i],
                "catalog": cat.name,
                "band": cat.band,
                "reference": cat.reference,
            })
        return out

    @property
    def table(self) -> Any:
        """The points as a pandas DataFrame (needs pandas)."""
        return self.to_pandas()

    def to_pandas(self, x: str | None = None, y: str | None = None) -> Any:
        """The points as a pandas DataFrame, with the CSV's columns.

        Given ``x`` and/or ``y`` units, adds ``x``, ``y`` and ``y_err`` columns
        converted as in :meth:`converted`.
        """
        try:
            import pandas as pd
        except ImportError as exc:
            raise ImportError(
                "SED.table needs pandas: pip install pandas (or astro-mmdc[plot])"
            ) from exc
        df = pd.DataFrame(self.rows(), columns=list(CSV_HEADER))
        df["undated"] = self.undated
        if x is not None or y is not None:
            conv = self.converted(x=x or "Hz", y=y or "erg cm-2 s-1")
            df["x"], df["y"], df["y_err"] = conv["x"], conv["y"], conv["y_err"]
        return df

    def converted(
        self, x: str = "Hz", y: str = "erg cm-2 s-1"
    ) -> dict[str, list[Optional[float]]]:
        """The points in the website's axis units: ``{"x", "y", "y_err"}`` lists.

        ``x``: ``Hz`` or ``eV``. ``y``: ``erg cm-2 s-1``, ``TeV cm-2 s-1``,
        ``norm`` (dN/dE in eV⁻¹ cm⁻² s⁻¹), ``Jy Hz``, ``W m-2`` or ``Jy``. The
        website's axis keys (``freq_ev``, ``flux_jyhz``, ...) work too.
        """
        return {
            "x": _units.convert_x(self.freq_hz, x),
            "y": _units.convert_y(self.nufnu, self.freq_hz, y),
            "y_err": _units.convert_y(self.nufnu_err, self.freq_hz, y),
        }

    # -- filtering (client side, same rules as the server) -----------------

    def between(
        self,
        mjd_start: float | None = None,
        mjd_end: float | None = None,
        *,
        undated: bool | None = None,
    ) -> SED:
        """Points whose midpoint (start + end) / 2 lies in the window ``[mjd_start, mjd_end]``.

        Ends included, as on the server; an interval counts on its midpoint only.
        Either end of the window may be ``None``. Undated points (MJD 50000) are not in any
        window: as on the server, ``undated=None`` drops them when a window is
        given and keeps them otherwise; ``True`` or ``False`` keeps or drops them.
        """
        if undated is None:
            undated = mjd_start is None and mjd_end is None

        def keep(i: int) -> bool:
            if self.undated[i]:
                return undated
            s, e = self.mjd_start[i], self.mjd_end[i]
            s = e if s is None else s
            e = s if e is None else e
            mid = (s + e) / 2
            if mjd_start is not None and mid < mjd_start:
                return False
            if mjd_end is not None and mid > mjd_end:
                return False
            return True

        filters = {**self.filters, "mjd_start": mjd_start, "mjd_end": mjd_end, "undated": undated}
        return self._subset([i for i in range(self.points) if keep(i)], filters)

    def select(
        self, catalogs: list[str] | None = None, *, exclude: list[str] | None = None
    ) -> SED:
        """Keep only ``catalogs`` and/or drop ``exclude`` (names as in :attr:`catalogs`)."""
        wanted = set(catalogs) if catalogs is not None else None
        dropped = set(exclude or ())
        names = [c.name for c in self.catalogs]
        idx = [
            i for i in range(self.points)
            if (wanted is None or names[self.catalog_idx[i]] in wanted)
            and names[self.catalog_idx[i]] not in dropped
        ]
        catalogs_filter = sorted(wanted) if wanted is not None else None
        return self._subset(idx, {**self.filters, "catalogs": catalogs_filter})

    def _subset(self, idx: list[int], filters: dict[str, Any]) -> SED:
        used = sorted({self.catalog_idx[i] for i in idx})
        remap = {old: new for new, old in enumerate(used)}
        cols = {c: [getattr(self, c)[i] for i in idx] for c in _COLUMNS}
        cols["catalog_idx"] = [remap[self.catalog_idx[i]] for i in idx]
        return self.model_copy(update={
            **cols,
            "catalogs": [self.catalogs[i] for i in used],
            "filters": filters,
        })

    # -- output ------------------------------------------------------------

    def to_csv(self, path: str | Path | None = None) -> str:
        """The points as CSV text, in the server's CSV format; also written to ``path`` if given."""
        buf = io.StringIO()
        writer = csv.writer(buf, lineterminator="\n")
        writer.writerow(CSV_HEADER)
        for row in self.rows():
            writer.writerow([_csv_value(row[c]) for c in CSV_HEADER])
        text = buf.getvalue()
        if path is not None:
            Path(path).write_text(text, encoding="utf-8")
        return text

    def plot(
        self,
        path: str | Path | None = None,
        *,
        x: str = "Hz",
        y: str = "erg cm-2 s-1",
        ax: Any = None,
        title: str | None = None,
        legend: bool = True,
        figsize: tuple[float, float] = (10, 6),
        dpi: int = 150,
    ) -> Any:
        """Draw the SED (needs ``astro-mmdc[plot]``) and return the matplotlib Axes.

        Colours are the website's per-catalogue colours; upper limits are
        down triangles; points with νFν ≤ 0 are left out (log axes).
        Saves to ``path`` when given.
        """
        from astro_mmdc._plotting import plot_points

        return plot_points(
            self, path, x=x, y=y, ax=ax, title=title, legend=legend, figsize=figsize, dpi=dpi
        )


def _undated(start: float | None, end: float | None) -> bool:
    # Fallback for responses without the column: older servers sent null, newer ones 50000.
    return start == end and (start is None or start == UNDATED_MJD)


def _csv_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return repr(value)
    return str(value)
