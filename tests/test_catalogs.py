import json
from unittest.mock import patch

import httpx
import pytest

from astro_mmdc import APIError
from astro_mmdc.models.catalogs import CatalogEntry


def test_autocomplete_returns_typed_entries(mock_api, client):
    route = mock_api.post("/api/autocomplete/").mock(
        return_value=httpx.Response(200, json={"results": [
            {"name": "CTA102", "ra": 338.151667, "dec": 11.7308333, "refcatalog": "VERON06"},
            {"name": "CTA 102", "ra": 338.1517, "dec": 11.7308, "refcatalog": "NED"},
        ]})
    )
    hits = client.catalogs.autocomplete("cta102")
    assert json.loads(route.calls.last.request.content) == {"query": "cta102"}
    assert all(isinstance(h, CatalogEntry) for h in hits)
    assert hits[0].name == "CTA102"
    assert hits[0].ra == 338.151667
    assert hits[0].dec == 11.7308333
    assert hits[0].refcatalog == "VERON06"


def test_autocomplete_no_match_is_empty(mock_api, client):
    mock_api.post("/api/autocomplete/").mock(
        return_value=httpx.Response(200, json={"results": []})
    )
    assert client.catalogs.autocomplete("no such source") == []


def test_autocomplete_position_echo(mock_api, client):
    mock_api.post("/api/autocomplete/").mock(
        return_value=httpx.Response(200, json={"results": [
            {"name": "", "ra": 10.0, "dec": -5.5, "refcatalog": "INPUT", "q_flag": None},
        ]})
    )
    [hit] = client.catalogs.autocomplete("10 -5.5")
    assert hit.name == ""
    assert hit.refcatalog == "INPUT"


def test_autocomplete_bad_query_raises(mock_api, client):
    mock_api.post("/api/autocomplete/").mock(
        return_value=httpx.Response(400, json={"query": ["Query is required."]})
    )
    with pytest.raises(APIError):
        client.catalogs.autocomplete(" ")


def test_autocomplete_retries_transient_5xx(mock_api, client):
    route = mock_api.post("/api/autocomplete/").mock(side_effect=[
        httpx.Response(503),
        httpx.Response(200, json={"results": []}),
    ])
    with patch("astro_mmdc._base.time.sleep"):
        assert client.catalogs.autocomplete("mrk 421") == []
    assert route.call_count == 2


def test_autocomplete_waits_past_proxy_timeout(mock_api, client):
    route = mock_api.post("/api/autocomplete/").mock(
        return_value=httpx.Response(200, json={"results": []})
    )
    client.catalogs.autocomplete("mrk 421")
    timeout = route.calls.last.request.extensions["timeout"]
    assert timeout["read"] > 60
    assert timeout["connect"] == client._base._client.timeout.connect


def test_autocomplete_stops_retrying_at_deadline(mock_api, client):
    route = mock_api.post("/api/autocomplete/").mock(return_value=httpx.Response(504))
    clock = iter([0.0, 200.0])  # deadline set at t=0, first 504 back at t=200
    with patch("astro_mmdc._base.time.sleep"), \
         patch("time.monotonic", side_effect=lambda: next(clock)):
        with pytest.raises(APIError):
            client.catalogs.autocomplete("unknown name")
    assert route.call_count == 1
