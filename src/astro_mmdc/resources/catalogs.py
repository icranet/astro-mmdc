from __future__ import annotations

from astro_mmdc._base import BaseClient
from astro_mmdc.models.catalogs import CatalogueEntry


class CatalogsResource:
    def __init__(self, client: BaseClient) -> None:
        self._client = client

    def autocomplete(self, query: str) -> list[CatalogueEntry]:
        """Look up sources by name or position in MMDC's source catalogue.

        Parameters
        ----------
        query : str
            A source name, matched case- and space-insensitively as a
            substring (``"mrk 421"`` finds ``MRK421``), or a position
            ``"RA DEC"`` / ``"RA,DEC"`` in degrees. A name with no catalogue
            match is resolved with NED, then SIMBAD.

        Returns
        -------
        list[CatalogueEntry]
            At most 40 entries with ``name``, ``ra``, ``dec`` (ICRS degrees)
            and ``refcatalog``; empty when nothing matches. A position with
            no catalogue entry nearby comes back as itself, with an empty
            ``name`` and ``refcatalog="INPUT"``.
        """
        response = self._client.request(
            "POST", "/api/autocomplete/", json={"query": query}, idempotent=True
        )
        return [CatalogueEntry.model_validate(row) for row in response.json()["results"]]
