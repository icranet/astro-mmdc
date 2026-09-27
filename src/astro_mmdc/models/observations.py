from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class Reference(BaseModel):
    citation: str
    bibcode: str | None = None
    url: str | None = None


class Observation(BaseModel):
    id: int
    catalog: str
    reference: Reference | None = None
    is_lightcurve: bool
    obsid: str | None = None
    ra: float
    dec: float
    sky_identifier: int
    flux: float
    # NULL for upper limits: a non-detection carries no measurement error.
    flux_err: float | None = None

    # SED-only fields
    frequency: float | None = None
    mjd_start: float | None = None
    mjd_end: float | None = None
    is_upper_limit: bool = False

    # LC-only fields
    mjd_mid: float | None = None
    filter_band: str | None = None
    spectral_index: float | None = None
    spectral_index_err: float | None = None

    created_at: datetime
