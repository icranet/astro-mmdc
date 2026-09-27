from unittest.mock import patch

import httpx
import pytest

from astro_mmdc import MMDC

OBS = "/api/observations/"


def _header(route, i=0):
    return route.calls[i].request.headers.get("x-mmdc-end-user")


def test_no_end_user_by_default(mock_api, client):
    route = mock_api.get(OBS).mock(return_value=httpx.Response(200, json=[]))
    client.observations.query(limit=1)
    assert _header(route) is None


def test_constructor_end_user_is_sent(mock_api):
    route = mock_api.get(OBS).mock(return_value=httpx.Response(200, json=[]))
    with MMDC(api_key="k", end_user="abc12") as c:
        c.observations.query(limit=1)
    req = route.calls[0].request
    assert req.headers["x-mmdc-end-user"] == "abc12"
    assert req.headers["x-api-key"] == "k"


def test_for_user_overrides_and_shares_connection(mock_api):
    route = mock_api.get(OBS).mock(return_value=httpx.Response(200, json=[]))
    parent = MMDC(api_key="k", app="astrogenesis", end_user="default-user")
    alice = parent.for_user("alice")
    anon = parent.for_user(None)
    assert alice._base._client is parent._base._client

    alice.observations.query(limit=1)
    anon.observations.query(limit=1)
    parent.observations.query(limit=1)

    assert [_header(route, i) for i in range(3)] == ["alice", None, "default-user"]
    # Parent's identity headers carry over to the view.
    assert route.calls[0].request.headers["x-mmdc-client"] == "astrogenesis"
    assert route.calls[0].request.headers["x-api-key"] == "k"
    parent.close()


def test_closing_a_view_keeps_parent_open(mock_api):
    route = mock_api.get(OBS).mock(return_value=httpx.Response(200, json=[]))
    parent = MMDC()
    with parent.for_user("alice") as view:
        view.observations.query(limit=1)
    parent.observations.query(limit=1)
    assert route.call_count == 2
    parent.close()


def test_end_user_reaches_every_resource(mock_api):
    post = mock_api.post("/api/madam_analysis/").mock(
        return_value=httpx.Response(202, json={"uuid": "u", "status": "processing", "cached": False})
    )
    vou = mock_api.post("/api/vou_json/").mock(
        return_value=httpx.Response(201, json={"status": "created", "uuid": "v"})
    )
    c = MMDC().for_user("abc12")
    c.madam.submit(1.0, 2.0, obsids=["1"])
    c.sed.prepare(1.0, 2.0, database_name="x")
    assert _header(post) == "abc12"
    assert _header(vou) == "abc12"


def test_per_call_headers_still_win(mock_api):
    import io
    route = mock_api.post("/api/modeling/batch_inference/").mock(
        return_value=httpx.Response(202, json={"batch_result_id": "b"})
    )
    c = MMDC().for_user("abc12")
    c.modeling.submit_batch(io.BytesIO(b"frequency,flux,flux_err\n1,1,1\n"),
                            z=0.1, ebl=True, model_type="SSC")
    req = route.calls[0].request
    assert req.headers["x-mmdc-end-user"] == "abc12"
    assert "idempotency-key" in req.headers


@pytest.mark.parametrize("bad", ["someone@example.com", "a b", "x" * 65, ""])
def test_invalid_end_user_rejected_locally(bad):
    with pytest.raises(ValueError):
        MMDC(end_user=bad)
    with pytest.raises(ValueError):
        MMDC().for_user(bad)


def test_numeric_and_zero_ids_are_sent(mock_api):
    route = mock_api.get(OBS).mock(return_value=httpx.Response(200, json=[]))
    c = MMDC()
    c.for_user(0).observations.query(limit=1)
    c.for_user(42).observations.query(limit=1)
    assert [_header(route, i) for i in range(2)] == ["0", "42"]


def test_outdated_warning_prints_once_across_views(mock_api):
    mock_api.get(OBS).mock(
        return_value=httpx.Response(200, json=[], headers={"X-MMDC-Min-Version": "99.0.0"})
    )
    c = MMDC()
    with patch("astro_mmdc._base.print") as printed:
        for user in ("a", "b", "c"):
            c.for_user(user).observations.query(limit=1)
        c.observations.query(limit=1)
    assert printed.call_count == 1
