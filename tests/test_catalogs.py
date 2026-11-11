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


class _Clock:
    """Fake monotonic clock: requests and sleeps advance it."""

    def __init__(self):
        self.t = 0.0

    def sleep(self, seconds):
        self.t += seconds

    def answer(self, after, response):
        def respond(request):
            self.t += after
            if isinstance(response, Exception):
                raise response
            return response
        return respond


@pytest.fixture()
def clock():
    c = _Clock()
    with patch("astro_mmdc._base.time.sleep", side_effect=c.sleep), \
         patch("time.monotonic", side_effect=lambda: c.t):
        yield c


def test_autocomplete_stops_retrying_at_deadline(mock_api, client, clock):
    route = mock_api.post("/api/autocomplete/").mock(
        side_effect=clock.answer(149.5, httpx.Response(504))
    )
    with pytest.raises(APIError):
        client.catalogs.autocomplete("unknown name")
    assert route.call_count == 1


def test_autocomplete_timeout_sets_request_timeout(mock_api):
    from astro_mmdc import MMDC

    route = mock_api.post("/api/autocomplete/").mock(
        return_value=httpx.Response(200, json={"results": []})
    )
    with MMDC(timeout=30) as c:
        c.catalogs.autocomplete("mrk 421", timeout=10)
    t = route.calls.last.request.extensions["timeout"]
    assert t["read"] <= 10 and t["connect"] <= 10 and t["write"] <= 10 and t["pool"] <= 10
    assert t["read"] > 9


def test_autocomplete_timeout_keeps_lower_client_connect(mock_api):
    from astro_mmdc import MMDC

    route = mock_api.post("/api/autocomplete/").mock(
        return_value=httpx.Response(200, json={"results": []})
    )
    with MMDC(timeout=3) as c:
        c.catalogs.autocomplete("mrk 421", timeout=10)
    t = route.calls.last.request.extensions["timeout"]
    assert t["connect"] == 3 and t["write"] == 3 and t["pool"] == 3
    assert 9 < t["read"] <= 10


@pytest.mark.parametrize("bad", [0, -1])
def test_autocomplete_timeout_must_be_positive(client, bad):
    with pytest.raises(ValueError, match="timeout must be > 0"):
        client.catalogs.autocomplete("mrk 421", timeout=bad)


def test_autocomplete_retry_gets_only_the_time_left(mock_api, client, clock):
    route = mock_api.post("/api/autocomplete/").mock(side_effect=[
        clock.answer(8.0, httpx.Response(503)),
        httpx.Response(200, json={"results": []}),
    ])
    with patch("astro_mmdc._base.random.uniform", return_value=0.0):
        assert client.catalogs.autocomplete("mrk 421", timeout=10) == []
    assert route.call_count == 2
    first, retry = (call.request.extensions["timeout"] for call in route.calls)
    assert first["read"] == 10
    assert retry["read"] == pytest.approx(1.0)  # 10 - 8 s answer - 1 s backoff
    assert max(retry.values()) <= 1.0 + 1e-9


def test_autocomplete_timeout_stops_retries(mock_api, client, clock):
    route = mock_api.post("/api/autocomplete/").mock(
        side_effect=clock.answer(9.5, httpx.Response(503))
    )
    with pytest.raises(APIError):
        client.catalogs.autocomplete("unknown name", timeout=10)
    assert route.call_count == 1
    assert clock.t == 9.5  # no sleep


def test_autocomplete_timeout_read_timeout_not_retried(mock_api, client, clock):
    route = mock_api.post("/api/autocomplete/").mock(
        side_effect=clock.answer(10.0, httpx.ReadTimeout("slow"))
    )
    with pytest.raises(httpx.ReadTimeout):
        client.catalogs.autocomplete("unknown name", timeout=10)
    assert route.call_count == 1
