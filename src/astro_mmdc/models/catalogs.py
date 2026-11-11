from __future__ import annotations

from pydantic import BaseModel


class CatalogEntry(BaseModel):
    name: str
    ra: float
    dec: float
    refcatalog: str
