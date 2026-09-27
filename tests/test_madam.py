import json
from unittest.mock import patch

import httpx
import pytest

from astro_mmdc.exceptions import AnalysisJobError, APIError, PollingTimeoutError
from astro_mmdc.models.madam import AnalysisJob, AnalysisSubmission
from astro_mmdc.models.observations import Observation

UUID = "e9f27d0b-65d3-40ad-b213-06428fa781f6"

UVOT_ROW = {
    "id": 1,
    "catalog": "MMDCOUV",
    "reference": None,
    "is_lightcurve": False,
    "obsid": "00030901030",
    "ra": 133.703645, "dec": 20.108511,
    "sky_identifier": 1234567890,
    "flux": 2.599e-11, "flux_err": 9.766e-13,
    "frequency": 5.483e14, "mjd_start": 55000.1, "mjd_end": 55000.2,
    "is_upper_limit": False,
    "mjd_mid": None, "filter_band": "V",
    "spectral_index": None, "spectral_index_err": None,
    "created_at": "2026-09-20T10:00:00+04:00",
}


def _job(status="processing", **extra):
    payload = {
        "uuid": UUID,
        "status": status,
        "source_name": "OJ287",
        "ra": 133.703645,
        "dec": 20.108511,
        "sky_identifier": 1234567890,
        "mode": "time_range",
        "instrument": "uvot",
        "orbit": True,
        "mjd_start": 58849.0,
        "mjd_end": 59031.0,
        "obsids": None,
        "xrt_fits": None,
        "rows_ingested": 0,
        "exit_code": None,
        "created_at": "2026-09-20T10:00:00+04:00",
        "finished_at": None,
    }
    payload.update(extra)
    return payload


def test_submit_time_range(mock_api, client):
    route = mock_api.post("/api/madam_analysis/").mock(
        return_value=httpx.Response(
            202, json={"uuid": UUID, "status": "processing", "cached": False}
        )
    )
    result = client.madam.submit(
        133.703645, 20.108511, mjd_start=58849.0, mjd_end=59031.0, source_name="OJ287"
    )
    assert isinstance(result, AnalysisSubmission)
    assert result.uuid == UUID
    assert result.cached is False
    assert result.results is None

    body = json.loads(route.calls[0].request.content)
    assert body == {
        "ra": 133.703645, "dec": 20.108511, "instrument": "uvot",
        "mjd_start": 58849.0, "mjd_end": 59031.0, "source_name": "OJ287",
    }


def test_submit_obsids_xrt_orbit_force(mock_api, client):
    route = mock_api.post("/api/madam_analysis/").mock(
        return_value=httpx.Response(
            202, json={"uuid": UUID, "status": "processing", "cached": False}
        )
    )
    client.madam.submit(
        1.0, 2.0, obsids=["30901030", 30901031], instrument="xrt", orbit=False, force=True,
        limit=5,
    )
    assert "limit=5" in str(route.calls[0].request.url)
    body = json.loads(route.calls[0].request.content)
    assert body == {
        "ra": 1.0, "dec": 2.0, "instrument": "xrt",
        "obsids": ["30901030", "30901031"], "orbit": False, "force": True,
    }


@pytest.mark.parametrize(
    "kwargs",
    [
        {},
        {"mjd_start": 58849.0},
        {"mjd_end": 59031.0},
        {"obsids": []},
        {"mjd_start": 58849.0, "mjd_end": 59031.0, "obsids": ["1"]},
    ],
)
def test_submit_rejects_bad_mode_locally(mock_api, client, kwargs):
    # No route registered: a request would fail loudly under respx.
    with pytest.raises(ValueError):
        client.madam.submit(1.0, 2.0, **kwargs)


def test_submit_rejects_string_obsids(mock_api, client):
    with pytest.raises(TypeError):
        client.madam.submit(1.0, 2.0, obsids="00030901030")


def test_submit_server_validation_is_api_error(mock_api, client):
    mock_api.post("/api/madam_analysis/").mock(
        return_value=httpx.Response(
            400, json={"mjd_start": ["'mjd_start' must be >= 54682.6553"]}
        )
    )
    with pytest.raises(APIError) as exc:
        client.madam.submit(1.0, 2.0, mjd_start=50000.0, mjd_end=51000.0)
    assert exc.value.status_code == 400


def test_submit_cache_hit_carries_rows(mock_api, client):
    mock_api.post("/api/madam_analysis/").mock(
        return_value=httpx.Response(
            200,
            json={"uuid": UUID, "status": "done", "cached": True,
                  "count": 1, "results": [UVOT_ROW]},
        )
    )
    result = client.madam.submit(1.0, 2.0, obsids=["00030901030"])
    assert result.cached is True
    assert result.count == 1
    assert isinstance(result.results[0], Observation)
    assert result.results[0].filter_band == "V"


def test_get_with_results(mock_api, client):
    mock_api.get(f"/api/madam_analysis/{UUID}/").mock(
        return_value=httpx.Response(
            200, json=_job("done", rows_ingested=1, exit_code=0,
                           count=1, results=[UVOT_ROW])
        )
    )
    job = client.madam.get(UUID)
    assert isinstance(job, AnalysisJob)
    assert job.is_finished
    assert job.count == 1
    assert job.results[0].catalog == "MMDCOUV"


def test_get_without_results_and_limit(mock_api, client):
    route = mock_api.get(f"/api/madam_analysis/{UUID}/").mock(
        return_value=httpx.Response(200, json=_job("processing"))
    )
    job = client.madam.get(UUID, include_results=False, limit=10)
    assert job.results is None
    url = str(route.calls[0].request.url)
    assert "include_results=false" in url
    assert "limit=10" in url


def test_wait_polls_cheaply_then_fetches_rows(mock_api, client):
    route = mock_api.get(f"/api/madam_analysis/{UUID}/").mock(
        side_effect=[
            httpx.Response(200, json=_job("processing")),
            httpx.Response(200, json=_job("done", exit_code=0)),
            httpx.Response(200, json=_job("done", exit_code=0, count=1, results=[UVOT_ROW])),
        ]
    )
    sleeps = []
    with patch("astro_mmdc._polling.time.sleep", side_effect=sleeps.append):
        job = client.madam.wait_for_completion(UUID)
    assert job.status == "done"
    assert job.count == 1
    assert sleeps == [60.0]
    urls = [str(c.request.url) for c in route.calls]
    assert all("include_results=false" in u for u in urls[:2])
    assert "include_results" not in urls[2]


def test_wait_backoff_caps_at_two_minutes(mock_api, client):
    mock_api.get(f"/api/madam_analysis/{UUID}/").mock(
        side_effect=[httpx.Response(200, json=_job("processing"))] * 4
        + [httpx.Response(200, json=_job("no_data"))] * 2
    )
    sleeps = []
    with patch("astro_mmdc._polling.time.sleep", side_effect=sleeps.append):
        job = client.madam.wait_for_completion(UUID)
    assert job.status == "no_data"
    assert sleeps == [60.0, 90.0, 120.0, 120.0]


def test_wait_raises_on_error_with_logs(mock_api, client):
    mock_api.get(f"/api/madam_analysis/{UUID}/").mock(
        return_value=httpx.Response(
            200, json=_job("error", exit_code=1, logs="Traceback ...\nboom\n")
        )
    )
    with pytest.raises(AnalysisJobError) as exc:
        client.madam.wait_for_completion(UUID)
    assert exc.value.uuid == UUID
    assert exc.value.logs.endswith("boom\n")
    assert "boom" in str(exc.value)


def test_wait_times_out(mock_api, client):
    mock_api.get(f"/api/madam_analysis/{UUID}/").mock(
        return_value=httpx.Response(200, json=_job("processing"))
    )
    with patch("astro_mmdc._polling.time.sleep"):
        with pytest.raises(PollingTimeoutError) as exc:
            client.madam.wait_for_completion(UUID, poll_interval=0.0, max_minutes=0.0)
    assert exc.value.uuid == UUID
    assert UUID in str(exc.value)


def test_analyze_cache_hit_keeps_requested_window_rows(mock_api, client):
    mock_api.post("/api/madam_analysis/").mock(
        return_value=httpx.Response(
            200,
            json={"uuid": UUID, "status": "done", "cached": True,
                  "count": 1, "results": [UVOT_ROW]},
        )
    )
    # The covering job was a wider swift run; the returned job must describe
    # the request that was made, with the rows the POST served.
    get = mock_api.get(f"/api/madam_analysis/{UUID}/").mock(
        return_value=httpx.Response(
            200,
            json=_job("done", instrument="swift", mjd_start=55000.0, mjd_end=60000.0,
                      xrt_fits=[{"obsid": "x"}], rows_ingested=900),
        )
    )
    job = client.madam.analyze(1.0, 2.0, mjd_start=58849.0, mjd_end=59031.0)
    assert job.cached is True
    assert (job.mjd_start, job.mjd_end, job.mode) == (58849.0, 59031.0, "time_range")
    assert job.instrument == "uvot"
    assert job.xrt_fits is None
    assert job.rows_ingested == 900  # covering run's metadata is kept
    assert job.count == 1
    assert job.results[0].obsid == "00030901030"
    assert "include_results=false" in str(get.calls[0].request.url)


def test_analyze_cache_hit_obsid_mode_keeps_xrt_fits(mock_api, client):
    mock_api.post("/api/madam_analysis/").mock(
        return_value=httpx.Response(
            200, json={"uuid": UUID, "status": "done", "cached": True, "count": 0, "results": []}
        )
    )
    mock_api.get(f"/api/madam_analysis/{UUID}/").mock(
        return_value=httpx.Response(
            200, json=_job("done", instrument="swift", xrt_fits=[{"obsid": "00030901030"}])
        )
    )
    job = client.madam.analyze(1.0, 2.0, obsids=[30901030], instrument="xrt")
    assert job.cached and job.mode == "obsid" and job.obsids == ["30901030"]
    assert job.mjd_start is None
    assert job.xrt_fits == [{"obsid": "00030901030"}]


def test_analyze_submits_then_waits(mock_api, client):
    mock_api.post("/api/madam_analysis/").mock(
        return_value=httpx.Response(
            202, json={"uuid": UUID, "status": "processing", "cached": False}
        )
    )
    mock_api.get(f"/api/madam_analysis/{UUID}/").mock(
        side_effect=[
            httpx.Response(200, json=_job("processing")),
            httpx.Response(200, json=_job("done", exit_code=0)),
            httpx.Response(200, json=_job("done", exit_code=0, count=1, results=[UVOT_ROW])),
        ]
    )
    with patch("astro_mmdc._polling.time.sleep"):
        job = client.madam.analyze(1.0, 2.0, obsids=["00030901030"], poll_interval=1.0)
    assert job.status == "done"
    assert job.cached is False
    assert job.results[0].flux == 2.599e-11


def test_xrt_fits_is_kept_off_results(mock_api, client):
    fits = [{"obsid": "00030901030", "gamma": 2.1, "flux": 1e-11}]
    mock_api.get(f"/api/madam_analysis/{UUID}/").mock(
        return_value=httpx.Response(
            200, json=_job("done", instrument="xrt", xrt_fits=fits, count=0, results=[])
        )
    )
    job = client.madam.get(UUID)
    assert job.xrt_fits == fits
    assert job.results == []


XRT_ROW = {**UVOT_ROW, "catalog": "MMDCXRT", "filter_band": None, "frequency": 1.4e17}

XRT_OBSERVATION = {
    "obsid": "00038422001", "mjd": 55462.00308, "datamode": "pc",
    "stat_type": "cstat", "delta_stat": 13.79, "preferred_model": "logparabola",
    "fits": {
        "powerlaw": {"index": 0.471973, "index_err": 0.2085, "flux_2_10": 1.9445e-11,
                     "flux_2_10_err": 4.2e-12, "flux_05_2": 1.1792e-12,
                     "flux_05_2_err": 2.4e-13, "stat": 136.3, "dof": 149,
                     "null_prob": 0.243},
        "logparabola": {"alpha": -1.2982, "alpha_err": 0.9453, "beta": 2.13389,
                        "beta_err": 1.0649, "flux_2_10": 1.3143e-11,
                        "flux_2_10_err": 2.2e-12, "flux_05_2": 1.0783e-12,
                        "flux_05_2_err": 2.8e-13, "stat": 122.51, "dof": 148,
                        "null_prob": 0.592},
    },
    "points": [XRT_ROW],
}


def test_xrt_observations_are_typed(mock_api, client):
    mock_api.get(f"/api/madam_analysis/{UUID}/").mock(
        return_value=httpx.Response(
            200,
            json=_job("done", instrument="xrt", count=1, results=[XRT_ROW],
                      xrt_observations=[XRT_OBSERVATION]),
        )
    )
    [obs] = client.madam.get(UUID).xrt_observations
    assert obs.preferred_model == "logparabola"
    assert obs.fits.powerlaw.dof == 149
    assert obs.fits.logparabola.beta == 2.13389
    assert obs.points[0].catalog == "MMDCXRT"


def test_xrt_observations_tolerate_missing_fits(mock_api, client):
    bare = {"obsid": "00035905184", "mjd": None, "datamode": None, "stat_type": None,
            "delta_stat": None, "preferred_model": None, "fits": None, "points": []}
    half = {**XRT_OBSERVATION, "fits": {"powerlaw": XRT_OBSERVATION["fits"]["powerlaw"],
                                        "logparabola": None}}
    mock_api.get(f"/api/madam_analysis/{UUID}/").mock(
        return_value=httpx.Response(
            200, json=_job("done", instrument="xrt", xrt_observations=[bare, half])
        )
    )
    bare_obs, half_obs = client.madam.get(UUID).xrt_observations
    assert bare_obs.fits is None
    assert half_obs.fits.logparabola is None


def test_analyze_cache_hit_takes_xrt_observations_from_the_post(mock_api, client):
    mock_api.post("/api/madam_analysis/").mock(
        return_value=httpx.Response(
            200,
            json={"uuid": UUID, "status": "done", "cached": True, "count": 1,
                  "results": [XRT_ROW], "xrt_observations": [XRT_OBSERVATION]},
        )
    )
    mock_api.get(f"/api/madam_analysis/{UUID}/").mock(
        return_value=httpx.Response(200, json=_job("done", instrument="swift"))
    )
    job = client.madam.analyze(1.0, 2.0, obsids=["00038422001"], instrument="xrt")
    assert job.cached
    assert [o.obsid for o in job.xrt_observations] == ["00038422001"]


def test_uvot_job_has_no_xrt_observations(mock_api, client):
    mock_api.get(f"/api/madam_analysis/{UUID}/").mock(
        return_value=httpx.Response(200, json=_job("done", count=0, results=[]))
    )
    assert client.madam.get(UUID).xrt_observations is None
