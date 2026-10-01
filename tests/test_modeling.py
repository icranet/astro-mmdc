import io
from unittest.mock import patch

import httpx

import pytest

from astro_mmdc import MMDC
from astro_mmdc.exceptions import APIError, BatchJobError, PollingTimeoutError, ValidationError
from astro_mmdc.models.modeling import BatchResult, BatchSubmission, CSVValidation, InferenceResult


def _minimal_poll_payload(status="queued", queue_position=None):
    return {
        "status": status,
        "model_type": "SSC",
        "created_at": "2026-09-14T10:00:00Z",
        "queue_position": queue_position,
        "pdf_link": None,
    }


def test_submit_batch(mock_api, client):
    mock_api.post("/api/modeling/batch_inference/").mock(
        return_value=httpx.Response(
            202, json={"batch_result_id": "batch-uuid-1"}
        )
    )
    csv_file = io.BytesIO(b"frequency,flux,flux_err\n1e9,1e-12,1e-13\n")
    result = client.modeling.submit_batch(
        csv_file, z=0.158, ebl=True, model_type="SSC"
    )
    assert isinstance(result, BatchSubmission)
    assert result.batch_result_id == "batch-uuid-1"


def test_submit_batch_with_fixed_params(mock_api, client):
    route = mock_api.post("/api/modeling/batch_inference/").mock(
        return_value=httpx.Response(
            202, json={"batch_result_id": "batch-uuid-2"}
        )
    )
    csv_file = io.BytesIO(b"frequency,flux,flux_err\n1e9,1e-12,1e-13\n")
    client.modeling.submit_batch(
        csv_file,
        z=0.5,
        ebl=False,
        model_type="SSC",
        fixed_parameters={"log_B": -1.5, "lorentz_factor": 20.0},
    )
    request = route.calls[0].request
    # Verify multipart form was sent
    assert b"model_type" in request.content
    assert b"SSC" in request.content


def test_submit_batch_hadronic(mock_api, client):
    mock_api.post("/api/modeling/batch_inference/").mock(
        return_value=httpx.Response(
            202, json={"batch_result_id": "hadronic-uuid"}
        )
    )
    csv_file = io.BytesIO(b"frequency,flux,flux_err\n1e9,1e-12,1e-13\n")
    result = client.modeling.submit_batch(
        csv_file,
        z=1.0,
        ebl=True,
        model_type="HADRONIC",
        likelihood_type="poisson",
        n_icecube=3,
        dt=12.0,
    )
    assert result.batch_result_id == "hadronic-uuid"


def test_submit_batch_sends_idempotency_key(mock_api, client):
    route = mock_api.post("/api/modeling/batch_inference/").mock(
        return_value=httpx.Response(202, json={"batch_result_id": "batch-uuid-3"})
    )
    csv_file = io.BytesIO(b"frequency,flux,flux_err\n1e9,1e-12,1e-13\n")
    client.modeling.submit_batch(csv_file, z=0.1, ebl=True, model_type="SSC")
    key = route.calls[0].request.headers["idempotency-key"]
    assert len(key) == 32


def test_submit_batch_retry_reuses_idempotency_key_and_content(mock_api, client):
    route = mock_api.post("/api/modeling/batch_inference/").mock(
        side_effect=[
            httpx.Response(503, text="unavailable"),
            httpx.Response(202, json={"batch_result_id": "batch-uuid-4"}),
        ]
    )
    csv_body = b"frequency,flux,flux_err\n1e9,1e-12,1e-13\n"
    with patch("astro_mmdc._base.time.sleep"):
        result = client.modeling.submit_batch(
            io.BytesIO(csv_body), z=0.1, ebl=True, model_type="SSC"
        )
    assert result.batch_result_id == "batch-uuid-4"
    assert route.call_count == 2
    first, second = route.calls[0].request, route.calls[1].request
    assert first.headers["idempotency-key"] == second.headers["idempotency-key"]
    # Retried multipart body carries the CSV again, not a drained stream.
    assert csv_body in second.read()


_DONE = {
    "status": "done",
    "model_type": "SSC",
    "pdf_link": "https://mmdc.am/media/results/plot.pdf",
}
_HELD = {"Preference-Applied": "wait=25", "Retry-After": "1"}


def test_wait_for_batch_holds_each_request_on_the_server(mock_api, client):
    responses = [
        httpx.Response(200, json=_minimal_poll_payload(queue_position=5), headers=_HELD),
        httpx.Response(200, json=_minimal_poll_payload(status="processing"), headers=_HELD),
        httpx.Response(200, json=_DONE),
    ]
    route = mock_api.get("/api/modeling/batch_result/batch-uuid-5/").mock(side_effect=responses)
    sleeps = []
    with patch("astro_mmdc.resources.modeling.time.sleep", side_effect=sleeps.append):
        result = client.modeling.wait_for_batch("batch-uuid-5")
    assert isinstance(result, BatchResult)
    assert result.pdf_link is not None
    assert sleeps == []  # the server waited, so each answer is followed by the next request at once
    for call in route.calls:
        assert call.request.headers["prefer"] == "wait=25"
        assert call.request.extensions["timeout"]["read"] == 30.0 + 25


def test_wait_for_batch_polls_when_the_server_did_not_wait(mock_api, client):
    responses = [
        httpx.Response(200, json=_minimal_poll_payload(), headers=[("Retry-After", "2"), ("Retry-After", "5")]),
        httpx.Response(200, json=_minimal_poll_payload(queue_position=4)),  # older server
        httpx.Response(200, json=_DONE),
    ]
    mock_api.get("/api/modeling/batch_result/batch-uuid-6/").mock(side_effect=responses)
    sleeps = []
    with patch("astro_mmdc.resources.modeling.time.sleep", side_effect=sleeps.append):
        client.modeling.wait_for_batch("batch-uuid-6")
    assert sleeps == [2.0, 5.0]  # the server's Retry-After (nginx appends its own), else poll_interval


def test_wait_for_batch_retry_after_never_exceeds_poll_interval(mock_api, client):
    responses = [
        httpx.Response(200, json=_minimal_poll_payload(), headers={"Retry-After": "60"}),
        httpx.Response(200, json=_DONE),
    ]
    mock_api.get("/api/modeling/batch_result/batch-uuid-7/").mock(side_effect=responses)
    sleeps = []
    with patch("astro_mmdc.resources.modeling.time.sleep", side_effect=sleeps.append):
        client.modeling.wait_for_batch("batch-uuid-7", poll_interval=3.0)
    assert sleeps == [3.0]


def test_wait_for_batch_done_without_pdf_returns(mock_api, client):
    mock_api.get("/api/modeling/batch_result/batch-uuid-8/").mock(
        return_value=httpx.Response(200, json={**_DONE, "pdf_link": None})
    )
    result = client.modeling.wait_for_batch("batch-uuid-8")
    assert result.status == "done"
    assert result.pdf_link is None


def test_wait_for_batch_never_asks_past_the_deadline(mock_api, client):
    route = mock_api.get("/api/modeling/batch_result/batch-uuid-9/").mock(
        return_value=httpx.Response(200, json=_minimal_poll_payload())
    )
    with pytest.raises(PollingTimeoutError):
        client.modeling.wait_for_batch("batch-uuid-9", max_minutes=0)
    assert route.call_count == 1
    assert "prefer" not in route.calls[0].request.headers


def test_wait_for_batch_retries_stop_at_the_deadline(mock_api, client):
    route = mock_api.get("/api/modeling/batch_result/batch-uuid-10/").mock(
        return_value=httpx.Response(504)
    )
    with patch("astro_mmdc._base.time.sleep") as sleep, pytest.raises(APIError):
        client.modeling.wait_for_batch("batch-uuid-10", max_minutes=0.001)
    assert route.call_count == 1  # a retry would sleep past the deadline
    sleep.assert_not_called()


def test_get_batch_result(mock_api, client):
    mock_api.get("/api/modeling/batch_result/batch-uuid-1/").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": {"x": [1.0], "y": [2.0]},
                "equal_weighted_posterior": None,
                "best_parameters": {
                    "log_B": {"value": -1.2, "error": 0.1},
                },
                "fixed_parameters": None,
                "model_type": "SSC",
                "z": 0.158,
                "multinest_stats": None,
                "pdf_link": "https://mmdc.am/media/results/plot.pdf",
                "csv_best_parameters_link": None,
                "csv_best_model_link": None,
                "uploaded_file": None,
            },
        )
    )
    result = client.modeling.get_batch_result("batch-uuid-1")
    assert isinstance(result, BatchResult)
    assert result.pdf_link is not None
    assert result.best_parameters["log_B"].value == -1.2


def test_wait_for_batch(mock_api, client):
    responses = [
        httpx.Response(
            200,
            json={
                "data": None,
                "equal_weighted_posterior": None,
                "best_parameters": None,
                "fixed_parameters": None,
                "model_type": "SSC",
                "z": 0.158,
                "multinest_stats": None,
                "pdf_link": None,
                "csv_best_parameters_link": None,
                "csv_best_model_link": None,
                "uploaded_file": None,
            },
        ),
        httpx.Response(
            200,
            json={
                "data": {"x": [1.0]},
                "equal_weighted_posterior": None,
                "best_parameters": None,
                "fixed_parameters": None,
                "model_type": "SSC",
                "z": 0.158,
                "multinest_stats": None,
                "pdf_link": "https://mmdc.am/media/results/plot.pdf",
                "csv_best_parameters_link": None,
                "csv_best_model_link": None,
                "uploaded_file": None,
            },
        ),
    ]
    mock_api.get("/api/modeling/batch_result/batch-uuid-1/").mock(
        side_effect=responses
    )
    result = client.modeling.wait_for_batch(
        "batch-uuid-1", poll_interval=0.01, max_minutes=1
    )
    assert result.pdf_link is not None


def test_wait_for_batch_fails_fast_on_error_status(mock_api, client):
    mock_api.get("/api/modeling/batch_result/bad-uuid/").mock(
        return_value=httpx.Response(
            200,
            json={
                "status": "error",
                "data": None,
                "equal_weighted_posterior": None,
                "best_parameters": None,
                "fixed_parameters": None,
                "model_type": "EIC",
                "z": 0.361,
                "multinest_stats": None,
                "pdf_link": None,
                "csv_best_parameters_link": None,
                "csv_best_model_link": None,
                "uploaded_file": None,
            },
        )
    )
    with pytest.raises(BatchJobError) as exc_info:
        client.modeling.wait_for_batch(
            "bad-uuid", poll_interval=0.01, max_minutes=1
        )
    assert exc_info.value.status == "error"
    assert exc_info.value.batch_result_id == "bad-uuid"


def test_validate_csv_success(mock_api, client):
    mock_api.post("/api/modeling/validate_csv/").mock(
        return_value=httpx.Response(
            200,
            json={
                "success": True,
                "message": "CSV validation passed",
                "data_points": 10,
                "columns": ["frequency", "flux", "flux_err"],
                "frequency_range": [1e9, 1e15],
                "flux_range": [1e-14, 1e-10],
                "preview": [{"frequency": 1e9, "flux": 1e-12, "flux_err": 1e-13}],
            },
        )
    )
    csv_file = io.BytesIO(b"frequency,flux,flux_err\n1e9,1e-12,1e-13\n")
    result = client.modeling.validate_csv(csv_file)
    assert isinstance(result, CSVValidation)
    assert result.success is True
    assert result.data_points == 10


def test_validate_csv_failure(mock_api, client):
    mock_api.post("/api/modeling/validate_csv/").mock(
        return_value=httpx.Response(
            422,
            json={
                "error": "Missing required columns",
                "validation_type": "missing_columns",
                "missing": ["flux_err"],
                "found": ["frequency", "flux"],
                "required": ["frequency", "flux", "flux_err"],
            },
        )
    )
    csv_file = io.BytesIO(b"frequency,flux\n1e9,1e-12\n")
    try:
        client.modeling.validate_csv(csv_file)
        assert False, "Should have raised"
    except ValidationError as exc:
        assert exc.validation_type == "missing_columns"


def test_csv_to_json(mock_api, client):
    mock_api.post("/api/modeling/csv_to_json/").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": {"x": [1e9], "y": [1e-12], "dy": [1e-13]},
                "status": "success",
            },
        )
    )
    csv_file = io.BytesIO(b"frequency,flux,flux_err\n1e9,1e-12,1e-13\n")
    result = client.modeling.csv_to_json(csv_file)
    assert result["status"] == "success"


def test_infer(mock_api, client):
    mock_api.post("/api/modeling/inference/").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": {
                    "best": {
                        "nu": [1e9, 1e10, 1e11],
                        "nuFnu": [1e-12, 1e-11, 1e-12],
                    }
                }
            },
        )
    )
    result = client.modeling.infer(
        z=0.158,
        ebl=True,
        model_type="SSC",
        parameters={
            "log_B": -1.5,
            "log_electron_luminosity": 44.0,
            "log_gamma_cut": 5.0,
            "log_gamma_min": 2.0,
            "log_radius": 16.0,
            "lorentz_factor": 20.0,
            "spectral_index": 2.2,
        },
    )
    assert isinstance(result, InferenceResult)
    assert len(result.nu) == 3


def test_infer_hadronic(mock_api, client):
    mock_api.post("/api/modeling/inference/").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": {
                    "best": {
                        "nu": [1e9, 1e15],
                        "nuFnu": [1e-12, 1e-11],
                        "neutrino_energy": [1e14, 1e15],
                        "eFe_nu_tot": [1e-13, 1e-12],
                    }
                }
            },
        )
    )
    result = client.modeling.infer(
        z=0.5,
        ebl=True,
        model_type="hadronic",
        parameters={
            "log_B": -1.0,
            "log_Le": 44.0,
            "log_gamma_e_min": 2.0,
            "log_gamma_e_cut": 5.0,
            "log_gamma_p_cut": 9.0,
            "log_Lp": 46.0,
            "log_R": 16.0,
            "lorentz_factor": 10.0,
            "pe": 2.2,
            "pp": 2.0,
        },
    )
    assert isinstance(result, InferenceResult)
    assert result.neutrino_energy == [1e14, 1e15]


def test_api_error_on_500(mock_api, client):
    mock_api.post("/api/modeling/batch_inference/").mock(
        return_value=httpx.Response(
            500, json={"error": "Failed to process the request"}
        )
    )
    csv_file = io.BytesIO(b"frequency,flux,flux_err\n1e9,1e-12,1e-13\n")
    try:
        client.modeling.submit_batch(csv_file, z=0.5, ebl=True, model_type="SSC")
        assert False, "Should have raised"
    except APIError as exc:
        assert exc.status_code == 500


def test_batch_result_plot(tmp_path):
    matplotlib = pytest.importorskip("matplotlib")
    matplotlib.use("Agg")
    result = BatchResult(
        model_type="EIC",
        data={
            "best": {"nu": [1e10, 1e15, 1e20], "nuFnu": [1e-12, 1e-11, 1e-12]},
            "0": {"nu": [1e10, 1e15, 1e20], "nuFnu": [9e-13, 9e-12, 9e-13]},
        },
    )
    out = tmp_path / "sed.png"
    assert result.plot(out) == str(out)
    assert out.exists() and out.stat().st_size > 0


def test_batch_result_plot_uses_uploaded_points(tmp_path):
    pytest.importorskip("matplotlib")
    # No CSV passed — observations come from uploaded_file echoed by the API.
    result = BatchResult(
        model_type="SSC",
        data={"best": {"nu": [1e10, 1e20], "nuFnu": [1e-12, 1e-12]}},
        uploaded_file={
            "frequency": [1e12, 1e16],
            "flux": [5e-12, 8e-12],
            "flux_err": [1e-12, 2e-12],
        },
    )
    out = tmp_path / "sed.png"
    result.plot(out, title="src")
    assert out.exists()


def test_batch_result_plot_observed_csv_override(tmp_path):
    pytest.importorskip("matplotlib")
    pytest.importorskip("pandas")
    csv = tmp_path / "obs.csv"
    csv.write_text("frequency,flux,flux_err\n1e12,5e-12,1e-12\n1e16,8e-12,2e-12\n")
    result = BatchResult(
        model_type="SSC",
        data={"best": {"nu": [1e10, 1e20], "nuFnu": [1e-12, 1e-12]}},
    )
    out = tmp_path / "sed.png"
    result.plot(out, observed_csv=str(csv))
    assert out.exists()


def test_batch_result_plot_empty_data_raises():
    pytest.importorskip("matplotlib")
    with pytest.raises(ValueError, match="result.data is empty"):
        BatchResult(model_type="SSC").plot("unused.png")
