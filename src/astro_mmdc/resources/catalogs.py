from __future__ import annotations

import time

import httpx

from astro_mmdc._base import BaseClient, _min
from astro_mmdc.models.catalogs import CatalogEntry

# Above the proxy's 60 s, so a slow NED/SIMBAD lookup ends in the server's 504, not a client retry.
_READ_TIMEOUT = 75.0
_TOTAL_SECONDS = 150.0


class CatalogsResource:
    def __init__(self, client: BaseClient) -> None:
        self._client = client

    def autocomplete(self, query: str, *, timeout: float | None = None) -> list[CatalogEntry]:
        """Look up sources by name or position in MMDC's source catalogue.

        Parameters
        ----------
        query : str
            A source name, matched case- and space-insensitively as a
            substring (``"mrk 421"`` finds ``MRK421``); a position
            ``"RA DEC"`` or ``"RA,DEC"`` in degrees; or a single number,
            searched as RA only. A position out of range raises ``APIError``
            (HTTP 400).
        timeout : float, optional
            Seconds to wait, retries included. Each attempt is limited to the
            time left before ``timeout``, so the call returns in about
            ``timeout`` seconds (connect and read are separate phases, so the
            worst case is a bit under twice that). Pass it from interactive
            callers with their own fallback (a chat turn, a search box), for
            example ``timeout=10``, and catch ``httpx.TransportError``
            (timeouts are ``httpx.TimeoutException``) together with
            ``astro_mmdc.MMDCError`` (a 503/504 that runs into the deadline
            raises ``APIError``). ``None`` keeps the default: up to 75 s per
            request, past the server proxy's 60 s, and 150 s in all. Unlike
            ``client.sed``, ``None`` does not mean wait forever.

        Returns
        -------
        list[CatalogEntry]
            At most 40 entries with ``name``, ``ra``, ``dec`` (ICRS degrees)
            and ``refcatalog``, in no particular order: check ``name`` rather
            than taking the first entry. Empty when nothing matches.

        Notes
        -----
        A name with no catalogue match is resolved with NED, then SIMBAD, which
        can take up to a minute, but only while the caller's IP is under 100
        unresolved names per hour; past that an unknown name returns ``[]``.
        Behind ``for_user()`` all end users share your server's IP. A position
        with no catalogue entry nearby comes back as itself, with an empty
        ``name`` and ``refcatalog="INPUT"``.
        """
        if timeout is not None and timeout <= 0:
            raise ValueError("timeout must be > 0")
        base = self._client._client.timeout
        if timeout is None:
            read = _READ_TIMEOUT if base.read is None else max(base.read, _READ_TIMEOUT)
            limits = httpx.Timeout(connect=base.connect, read=read, write=base.write, pool=base.pool)
            total = _TOTAL_SECONDS
        else:
            limits = httpx.Timeout(
                connect=_min(base.connect, timeout), read=timeout,
                write=_min(base.write, timeout), pool=_min(base.pool, timeout),
            )
            total = timeout
        response = self._client.request(
            "POST",
            "/api/autocomplete/",
            json={"query": query},
            idempotent=True,
            deadline=time.monotonic() + total,
            cap_to_deadline=True,
            timeout=limits,
        )
        return [CatalogEntry.model_validate(row) for row in response.json()["results"]]
