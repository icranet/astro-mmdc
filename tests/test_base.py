import io
from unittest.mock import patch

import httpx
import pytest

from astro_mmdc import MMDC, __version__
from astro_mmdc.exceptions import APIError, RateLimitError


def test_user_agent_on_every_request(mock_api, client):
    route = mock_api.get("/api/modeling/batch_result/uuid-1/").mock(
        return_value=httpx.Response(200, json={"model_type": "SSC"})
    )
    client.modeling.get_batch_result("uuid-1")
    assert route.calls[0].request.headers["user-agent"] == f"astro-mmdc/{__version__}"


def test_no_client_headers_by_default(mock_api, client):
    route = mock_api.get("/api/modeling/batch_result/uuid-1/").mock(
        return_value=httpx.Response(200, json={"model_type": "SSC"})
    )
    client.modeling.get_batch_result("uuid-1")
    request = route.calls[0].request
    assert "x-mmdc-client" not in request.headers
    assert "x-api-key" not in request.headers


def test_app_and_api_key_headers(mock_api):
    route = mock_api.get("/api/modeling/batch_result/uuid-1/").mock(
        return_value=httpx.Response(200, json={"model_type": "SSC"})
    )
    with MMDC(app="my-pipeline", api_key="mmdc_secret123") as client:
        client.modeling.get_batch_result("uuid-1")
    request = route.calls[0].request
    assert request.headers["x-mmdc-client"] == "my-pipeline"
    assert request.headers["x-api-key"] == "mmdc_secret123"


def test_huge_retry_after_is_capped(mock_api, client):
    mock_api.get("/api/modeling/batch_result/uuid-1/").mock(
        return_value=httpx.Response(
            429, text="slow down", headers={"Retry-After": "100000"}
        )
    )
    sleeps = []
    with patch("astro_mmdc._base.time.sleep", side_effect=sleeps.append):
        with pytest.raises(RateLimitError):
            client.modeling.get_batch_result("uuid-1")
    assert len(sleeps) == 2  # 3 attempts, no sleep after the last
    assert all(s <= 150.0 for s in sleeps)  # 120s cap x max 1.25 jitter


def test_get_retried_on_503(mock_api, client):
    route = mock_api.get("/api/modeling/batch_result/uuid-1/").mock(
        side_effect=[
            httpx.Response(503, text="unavailable"),
            httpx.Response(200, json={"model_type": "SSC"}),
        ]
    )
    with patch("astro_mmdc._base.time.sleep"):
        result = client.modeling.get_batch_result("uuid-1")
    assert route.call_count == 2
    assert result.model_type == "SSC"


def test_bare_post_not_retried_on_502(mock_api, client):
    route = mock_api.post("/api/modeling/inference/").mock(
        return_value=httpx.Response(502, text="bad gateway")
    )
    with patch("astro_mmdc._base.time.sleep") as sleep:
        with pytest.raises(APIError) as exc_info:
            client.modeling.infer(
                z=0.1, ebl=True, model_type="SSC", parameters={"log_B": -1.0}
            )
    assert exc_info.value.status_code == 502
    assert route.call_count == 1
    sleep.assert_not_called()


def test_bare_post_not_retried_on_transport_error(mock_api, client):
    route = mock_api.post("/api/modeling/inference/").mock(
        side_effect=httpx.ConnectError("boom")
    )
    with pytest.raises(httpx.TransportError):
        client.modeling.infer(
            z=0.1, ebl=True, model_type="SSC", parameters={"log_B": -1.0}
        )
    assert route.call_count == 1


def test_min_version_warning_once(mock_api, client, capsys):
    mock_api.get("/api/modeling/batch_result/uuid-1/").mock(
        return_value=httpx.Response(
            200, json={"model_type": "SSC"}, headers={"X-MMDC-Min-Version": "9.9.9"}
        )
    )
    client.modeling.get_batch_result("uuid-1")
    client.modeling.get_batch_result("uuid-1")
    err = capsys.readouterr().err
    assert err.count("below the server minimum 9.9.9") == 1


def test_no_warning_when_current(mock_api, client, capsys):
    mock_api.get("/api/modeling/batch_result/uuid-1/").mock(
        return_value=httpx.Response(
            200, json={"model_type": "SSC"}, headers={"X-MMDC-Min-Version": __version__}
        )
    )
    client.modeling.get_batch_result("uuid-1")
    assert capsys.readouterr().err == ""


def test_no_warning_without_header(mock_api, client, capsys):
    mock_api.get("/api/modeling/batch_result/uuid-1/").mock(
        return_value=httpx.Response(200, json={"model_type": "SSC"})
    )
    client.modeling.get_batch_result("uuid-1")
    assert capsys.readouterr().err == ""
