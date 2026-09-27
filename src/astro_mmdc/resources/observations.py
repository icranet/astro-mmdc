from __future__ import annotations

from astro_mmdc._base import BaseClient
from astro_mmdc.models.observations import Observation


class ObservationsResource:
    def __init__(self, client: BaseClient) -> None:
        self._client = client

    def query(
        self,
        *,
        catalog: str | None = None,
        filter_band: str | None = None,
        is_lightcurve: bool | None = None,
        is_upper_limit: bool | None = None,
        obsid: str | None = None,
        mjd_min: float | None = None,
        mjd_max: float | None = None,
        ordering: str | None = None,
        limit: int | None = None,
    ) -> list[Observation]:
        """Query the unified observations endpoint.

        Parameters
        ----------
        catalog : str, optional
            Catalog code. One of ``MMDCGR``, ``MMDCOUV``, ``MMDCXRT``,
            ``MMDCXRT_ORBIT``, ``MMDCNuX``, ``ASAS-SN``, ``ZTF``,
            ``PanSTARRS-LC``, ``SMARTS``. ``MMDCXRT`` holds Swift-XRT
            snapshot-level products and ``MMDCXRT_ORBIT`` the orbit-level ones;
            they share an obsid, so query both for all XRT data.
        filter_band : str, optional
            Photometric band code (e.g. ``R``, ``V``, ``G``, ``W1``).
        is_lightcurve : bool, optional
            ``True`` returns only lightcurve rows; ``False`` returns only SED rows.
        is_upper_limit : bool, optional
            Filter by upper-limit flag.
        obsid : str, optional
            Exact observation id, matched verbatim. Swift/NuSTAR obsids are
            stored zero-padded to 11 digits, so pass ``"00030375224"`` rather
            than ``"30375224"``.
        mjd_min, mjd_max : float, optional
            Bounds on ``mjd_mid`` (LC) or the ``mjd_start``/``mjd_end`` window (SED).
        ordering : str, optional
            Sort key. Prefix with ``-`` for descending.
            Allowed: ``mjd_mid``, ``mjd_start``, ``mjd_end``, ``flux``, ``flux_err``,
            ``spectral_index``, ``sep_arcsec``, ``created_at``.
        limit : int, optional
            Cap the number of rows returned after filtering.
        """
        params = _build_params(
            catalog=catalog,
            filter_band=filter_band,
            is_lightcurve=is_lightcurve,
            is_upper_limit=is_upper_limit,
            obsid=obsid,
            mjd_min=mjd_min,
            mjd_max=mjd_max,
            ordering=ordering,
            limit=limit,
        )
        response = self._client.request("GET", "/api/observations/", params=params)
        return [Observation.model_validate(row) for row in response.json()]

    def cone_search(
        self,
        ra: float,
        dec: float,
        radius_arcsec: float = 5.0,
        *,
        catalog: str | None = None,
        filter_band: str | None = None,
        is_lightcurve: bool | None = None,
        is_upper_limit: bool | None = None,
        obsid: str | None = None,
        mjd_min: float | None = None,
        mjd_max: float | None = None,
        ordering: str | None = None,
        limit: int | None = None,
    ) -> list[Observation]:
        """Cone search around (ra, dec) using a HEALPix-indexed prefilter.

        Defaults to a 5 arcsec radius. The server caps the prefilter at 4096
        HEALPix pixels; larger radii fall back to a great-circle scan and may
        be slower.
        """
        params = _build_params(
            ra=ra,
            dec=dec,
            radius_arcsec=radius_arcsec,
            catalog=catalog,
            filter_band=filter_band,
            is_lightcurve=is_lightcurve,
            is_upper_limit=is_upper_limit,
            obsid=obsid,
            mjd_min=mjd_min,
            mjd_max=mjd_max,
            ordering=ordering,
            limit=limit,
        )
        response = self._client.request("GET", "/api/observations/", params=params)
        return [Observation.model_validate(row) for row in response.json()]


def _build_params(**kwargs: object) -> dict[str, str]:
    """Drop None values and serialize bools as 'true'/'false'."""
    params: dict[str, str] = {}
    for key, value in kwargs.items():
        if value is None:
            continue
        if isinstance(value, bool):
            params[key] = "true" if value else "false"
        else:
            params[key] = str(value)
    return params
