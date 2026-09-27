import httpx
import respx

from astro_mmdc import MMDC
from astro_mmdc.exceptions import NotFoundError, PollingTimeoutError
from astro_mmdc.models.sed import SEDData, SourceInfo, SourcePosition


def test_prepare_creates_job(mock_api, client):
    mock_api.post("/api/vou_json/").mock(
        return_value=httpx.Response(
            201, json={"status": "created", "uuid": "abc-123"}
        )
    )
    result = client.sed.prepare(ra=187.28, dec=2.05, database_name="3C273")
    assert isinstance(result, SourcePosition)
    assert result.uuid == "abc-123"
    assert result.status == "processing"


def test_prepare_returns_existing(mock_api, client):
    mock_api.post("/api/vou_json/").mock(
        return_value=httpx.Response(
            200,
            json={
                "uuid": "abc-123",
                "source_name": "3C 273",
                "database_name": "3C273",
                "ra": 187.28,
                "dec": 2.05,
                "status": "done",
                "logs": None,
            },
        )
    )
    result = client.sed.prepare(ra=187.28, dec=2.05, database_name="3C273")
    assert result.status == "done"


def test_prepare_with_force(mock_api, client):
    route = mock_api.post("/api/vou_json/").mock(
        return_value=httpx.Response(
            201, json={"status": "created", "uuid": "new-uuid"}
        )
    )
    client.sed.prepare(ra=1.0, dec=2.0, database_name="test", force=True)
    assert "force=true" in str(route.calls[0].request.url)


def test_get_status(mock_api, client):
    mock_api.get("/api/vou_json/abc-123/").mock(
        return_value=httpx.Response(
            200,
            json={
                "uuid": "abc-123",
                "source_name": None,
                "database_name": "test",
                "ra": 1.0,
                "dec": 2.0,
                "status": "processing",
                "logs": None,
            },
        )
    )
    result = client.sed.get_status("abc-123")
    assert result.status == "processing"


def test_wait_for_completion(mock_api, client):
    responses = [
        httpx.Response(
            200,
            json={
                "uuid": "abc-123",
                "source_name": None,
                "database_name": "test",
                "ra": 1.0,
                "dec": 2.0,
                "status": "processing",
                "logs": None,
            },
        ),
        httpx.Response(
            200,
            json={
                "uuid": "abc-123",
                "source_name": None,
                "database_name": "test",
                "ra": 1.0,
                "dec": 2.0,
                "status": "done",
                "logs": "Completed",
            },
        ),
    ]
    mock_api.get("/api/vou_json/abc-123/").mock(side_effect=responses)
    result = client.sed.wait_for_completion("abc-123", poll_interval=0.01, max_minutes=1)
    assert result.status == "done"
    assert result.logs == "Completed"


def test_get_data(mock_api, client):
    mock_api.get("/api/freq_flux_data/abc-123/").mock(
        return_value=httpx.Response(
            200,
            json={
                "uuid": "abc-123",
                "source_name": "3C 273",
                "database_name": "3C273",
                "ra": 187.28,
                "dec": 2.05,
                "data": {"range_data": {}, "min_max": {}},
            },
        )
    )
    result = client.sed.get_data("abc-123")
    assert isinstance(result, SEDData)
    assert result.data == {"range_data": {}, "min_max": {}}


def test_get_data_with_filters(mock_api, client):
    route = mock_api.get("/api/freq_flux_data/abc-123/").mock(
        return_value=httpx.Response(
            200,
            json={
                "uuid": "abc-123",
                "source_name": None,
                "database_name": "test",
                "ra": 1.0,
                "dec": 2.0,
                "data": {},
            },
        )
    )
    client.sed.get_data(
        "abc-123", mjd_start=50000.0, mjd_end=60000.0, x_axis="freq_ev"
    )
    url = str(route.calls[0].request.url)
    assert "mjd_start=50000.0" in url
    assert "mjd_end=60000.0" in url
    assert "x_axis=freq_ev" in url


def test_get_info(mock_api, client):
    mock_api.get("/api/source_info/abc-123/").mock(
        return_value=httpx.Response(
            200,
            json={
                "source_name": "3C 273",
                "ra": 187.28,
                "dec": 2.05,
                "gal_lat": 64.36,
                "gal_long": 289.95,
                "redshift": 0.158,
                "W_peak": "13.5",
            },
        )
    )
    result = client.sed.get_info("abc-123")
    assert isinstance(result, SourceInfo)
    assert result.redshift == 0.158


def test_get_status_not_found(mock_api, client):
    mock_api.get("/api/vou_json/bad-uuid/").mock(
        return_value=httpx.Response(404, json={"error": "Not found"})
    )
    try:
        client.sed.get_status("bad-uuid")
        assert False, "Should have raised"
    except NotFoundError as exc:
        assert exc.status_code == 404


def test_download_csv(mock_api, client, tmp_path):
    csv_content = b"frequency,flux,flux_err\n1e9,1e-12,1e-13\n"
    mock_api.get("/api/csv/abc-123/").mock(
        return_value=httpx.Response(200, content=csv_content)
    )
    dest = tmp_path / "data.csv"
    result = client.sed.download_csv("abc-123", dest)
    assert result.read_bytes() == csv_content


def _position(status, logs=None):
    return {"uuid": "abc-123", "source_name": None, "database_name": "test",
            "ra": 1.0, "dec": 2.0, "status": status, "logs": logs}


def test_wait_for_completion_timeout_carries_uuid(mock_api, client):
    mock_api.get("/api/vou_json/abc-123/").mock(
        return_value=httpx.Response(200, json=_position("processing"))
    )
    try:
        client.sed.wait_for_completion("abc-123", poll_interval=0.01, max_minutes=0)
    except PollingTimeoutError as exc:
        assert exc.uuid == "abc-123"
    else:
        raise AssertionError("expected PollingTimeoutError")


def test_prepare_and_wait_error_returned_by_default_raised_on_request(mock_api, client):
    from astro_mmdc import SEDJobFailed

    mock_api.post("/api/vou_json/").mock(
        return_value=httpx.Response(200, json=_position("error", "boom"))
    )
    assert client.sed.prepare_and_wait(1.0, 2.0, "test").status == "error"
    try:
        client.sed.prepare_and_wait(1.0, 2.0, "test", raise_on_error=True)
    except SEDJobFailed as exc:
        assert exc.id == "abc-123" and exc.message == "boom"
    else:
        raise AssertionError("expected SEDJobFailed")
