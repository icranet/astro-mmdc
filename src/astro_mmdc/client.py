from __future__ import annotations

import copy

from astro_mmdc._base import BaseClient
from astro_mmdc.resources.madam import MadamResource
from astro_mmdc.resources.modeling import ModelingResource
from astro_mmdc.resources.observations import ObservationsResource
from astro_mmdc.resources.sed import SEDResource


class MMDC:
    """Python SDK client for the MMDC astrophysics platform.

    Usage::

        from astro_mmdc import MMDC

        client = MMDC()
        job = client.sed.prepare(ra=187.28, dec=2.05, database_name="3C273")

    Or as a context manager::

        with MMDC() as client:
            result = client.modeling.batch_infer("data.csv", z=0.158, ebl=True, model_type="SSC")
            rows = client.observations.cone_search(ra=187.28, dec=2.05, radius_arcsec=10)
            uvot = client.madam.analyze(ra=166.11, dec=38.21, mjd_start=58849, mjd_end=59031)

    ``app`` names your application to the API (sent as ``X-MMDC-Client``);
    ``api_key`` authenticates for higher rate/concurrency tiers (sent as ``X-API-Key``);
    ``end_user`` is an opaque id for your own user, for per-user usage stats
    (sent as ``X-MMDC-End-User``, recorded only together with a valid ``api_key``).
    """

    def __init__(
        self,
        base_url: str = "https://mmdc.am",
        timeout: float = 30.0,
        app: str | None = None,
        api_key: str | None = None,
        end_user: str | None = None,
    ) -> None:
        self._init_resources(
            BaseClient(base_url=base_url, timeout=timeout, app=app,
                       api_key=api_key, end_user=end_user)
        )

    def _init_resources(self, base: BaseClient) -> None:
        self._base = base
        self.sed = SEDResource(self._base)
        self.modeling = ModelingResource(self._base)
        self.observations = ObservationsResource(self._base)
        self.madam = MadamResource(self._base)

    def for_user(self, end_user: str | int | None) -> MMDC:
        """A client that attributes its requests to ``end_user``.

        Shares this client's connection pool and settings, so it is cheap to
        create per request in a multi-user server; closing it does not close
        the parent. ``None`` sends no end user.
        """
        view = copy.copy(self)
        view._init_resources(self._base.with_end_user(end_user))
        return view

    def close(self) -> None:
        self._base.close()

    def __enter__(self) -> MMDC:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
