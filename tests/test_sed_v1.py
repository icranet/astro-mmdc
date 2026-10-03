"""/api/sed/ v1: every answer in docs/api/SED_API.md, mocked."""

import copy
import csv
import io
import json

import httpx
import pytest

from astro_mmdc import MMDC, SED, SEDJob, SEDJobFailed, SEDNoData, SEDTimeoutError
from astro_mmdc import units
from astro_mmdc.exceptions import NotFoundError, PollingTimeoutError, ValidationError

JID = "0b6f1c3e-5a3e-4c55-9d7e-2f0f1f7f4a11"
NEW = "5d1e7b8a-0c2f-4f1e-9a57-6b0a3c9d2e44"
SOURCE = {
    "name": "Mrk 421", "ra": 166.113808, "dec": 38.208833, "gal_l": 179.831677,
    "gal_b": 65.031476, "redshift": 0.0308,
    "w_peak": {"log_nu": 17.5, "err": None, "limit": "lower", "text": "> 17.5"},
}
SED_OBJ = {
    "points": 3,
    "units": {"freq_hz": "Hz", "nufnu": "erg cm-2 s-1", "mjd": "d"},
    "filters": {"mjd_start": None, "mjd_end": None, "catalogs": None, "undated": True},
    "catalogs": [
        {"name": "NVSS", "band": "radio_waves",
         "reference": "Condon et al. 1998, AJ, 115, 1693", "color": "#e45a8a"},
        {"name": "NEOWISE", "band": "infrared",
         "reference": "Mainzer et al. 2014, ApJ, 792, 30", "color": "#4aa5c9"},
    ],
    "freq_hz": [1.4e9, 6.52e13, 6.52e13],
    "nufnu": [1.1e-14, 3.2e-11, 2.9e-11],
    "nufnu_err": [3.0e-16, 1.1e-12, None],
    "is_ul": [False, False, True],
    "mjd_start": [None, 56669.2, 56850.9],
    "mjd_end": [None, 56669.2, 56850.9],
    "catalog_idx": [0, 1, 1],
}
SERVER_CSV = (
    "freq_hz,nufnu,nufnu_err,is_ul,mjd_start,mjd_end,catalog,band,reference\n"
    '1400000000.0,1.1e-14,3e-16,false,,,NVSS,radio_waves,"Condon et al. 1998, AJ, 115, 1693"\n'
    '65200000000000.0,3.2e-11,1.1e-12,false,56669.2,56669.2,NEOWISE,infrared,"Mainzer et al. 2014, ApJ, 792, 30"\n'
    '65200000000000.0,2.9e-11,,true,56850.9,56850.9,NEOWISE,infrared,"Mainzer et al. 2014, ApJ, 792, 30"\n'
)


def links(i):
    return {"self": f"/api/sed/{i}/", "job": f"/api/sed/jobs/{i}/", "csv": f"/api/sed/{i}/?format=csv"}


def event(n, text="line", **kw):
    e = {"v": 1, "t": float(n), "level": "info", "kind": "catalog", "phase": "phase1",
         "subject": f"Cat{n}", "outcome": "data", "points": 1, "source": "local",
         "duration_s": 0.5, "names": None, "done": None, "total": None, "text": text}
    e.update(kw)
    return e


def job(status, i=JID, events=None, events_next=None, progress=None, error=None, missed=None):
    j = {"id": i, "status": status, "created_at": "2026-09-27T14:02:11.402+04:00",
         "started_at": None, "finished_at": None, "elapsed_s": None, "refresh_of": None,
         "replaced_by": None, "progress": progress, "events_next": events_next or 0,
         "missed_catalogs": missed, "error": error,
         "links": {"self": f"/api/sed/jobs/{i}/", "result": f"/api/sed/{i}/"}}
    if events is not None:
        j["events"] = events
        j["events_truncated"] = False
        j["events_next"] = events_next if events_next is not None else len(events)
    return j


def envelope(status, i=JID, sed=SED_OBJ, reused=True, **jobkw):
    body = {"id": i, "status": status, "reused": reused, "stale": False, "refresh": None,
            "source": SOURCE, "job": job(status, i, **jobkw), "links": links(i)}
    if sed is not None:
        body["sed"] = copy.deepcopy(sed)
    return body


EMPTY = {**SED_OBJ, "points": 0, "catalogs": [], "freq_hz": [], "nufnu": [], "nufnu_err": [],
         "is_ul": [], "mjd_start": [], "mjd_end": [], "catalog_idx": []}
FAILED_ERR = {"code": "timeout", "message": "The run took too long and was stopped.",
              "retry_after_s": 1260}
RUNNING = {"Retry-After": "1", "Preference-Applied": "wait=20", "Location": f"/api/sed/jobs/{NEW}/"}


@pytest.fixture()
def sleeps(monkeypatch):
    """Record every sleep instead of sleeping."""
    calls = []
    monkeypatch.setattr("astro_mmdc.resources.sed.time.sleep", calls.append)
    monkeypatch.setattr("astro_mmdc._base.time.sleep", calls.append)
    return calls


# -- one call ------------------------------------------------------------------


def test_get_cached_done_is_one_request(mock_api, client, sleeps):
    route = mock_api.post("/api/sed/").mock(return_value=httpx.Response(200, json=envelope("done")))
    sed = client.sed.get(166.113808, 38.208833, "Mrk 421")
    assert route.call_count == 1
    req = route.calls[0].request
    assert json.loads(req.content) == {"ra": 166.113808, "dec": 38.208833, "name": "Mrk 421"}
    assert req.headers["Prefer"] == "wait=20"
    assert isinstance(sed, SED)
    assert sed.id == JID and sed.status == "done" and sed.reused is True
    assert sed.source.redshift == 0.0308 and sed.source.w_peak.log_nu == 17.5
    assert sed.points == len(sed) == 3
    assert sed.catalog == ["NVSS", "NEOWISE", "NEOWISE"]
    assert sed.nufnu_err == [3.0e-16, 1.1e-12, None]
    assert [c.name for c in sed.catalogs] == ["NVSS", "NEOWISE"]
    assert sleeps == []


def test_get_sends_refresh_and_filters(mock_api, client):
    route = mock_api.post("/api/sed/").mock(return_value=httpx.Response(200, json=envelope("done")))
    client.sed.get(1.0, 2.0, refresh=True, mjd_start=56000, mjd_end=57000,
                   catalogs=["NVSS", "NEOWISE"], undated=False)
    req = route.calls[0].request
    assert json.loads(req.content) == {"ra": 1.0, "dec": 2.0, "refresh": True}
    q = req.url.params
    assert q["mjd_start"] == "56000" and q["mjd_end"] == "57000"
    assert q["catalogs"] == "NVSS,NEOWISE" and q["undated"] == "false"


def test_202_then_done_follows_job_then_fetches_sed(mock_api, client, sleeps):
    mock_api.post("/api/sed/").mock(return_value=httpx.Response(
        202, headers=RUNNING,
        json=envelope("running", NEW, sed=None, reused=False, events=[event(0)],
                      progress={"stage": "phase1", "done": 1, "total": 19, "elapsed_s": 0.5})))
    job_route = mock_api.get(f"/api/sed/jobs/{NEW}/").mock(side_effect=[
        httpx.Response(200, headers={"Retry-After": "1", "Preference-Applied": "wait=20"},
                       json=job("running", NEW, events=[event(1), event(2)], events_next=3,
                                progress={"stage": "phase2", "done": 5, "total": 59,
                                          "elapsed_s": 21.0, "stages": {
                                              "phase1": {"done": 19, "total": 19, "elapsed_s": 2.9},
                                              "phase2": {"done": 5, "total": 59, "elapsed_s": 21.0},
                                              "lightcurves": {"done": 1, "total": 3,
                                                              "elapsed_s": 20.1}}})),
        httpx.Response(200, json=job("done", NEW, events=[event(3)], events_next=4, missed=["ZTF"])),
    ])
    sed_route = mock_api.get(f"/api/sed/{NEW}/").mock(
        return_value=httpx.Response(200, json={k: v for k, v in envelope("done", NEW).items()
                                                if k != "reused"}))
    seen, stages = [], []
    sed = client.sed.get(194.05, -5.79, "3C 279", progress=lambda j: stages.append(
        {k: (v.done, v.total) for k, v in j.progress.stages.items()} if j.progress else None
    ) or seen.append(
        (j.status, j.progress.stage if j.progress else None, [e.subject for e in j.new_events])))

    assert seen == [
        ("running", "phase1", ["Cat0"]),
        ("running", "phase2", ["Cat1", "Cat2"]),
        ("done", None, ["Cat3"]),
    ]
    assert stages == [{}, {"phase1": (19, 19), "phase2": (5, 59), "lightcurves": (1, 3)}, None]
    since = [c.request.url.params["events_since"] for c in job_route.calls]
    assert since == ["1", "3"]
    # A progress callback follows the job with short waits so it sees each stage.
    assert all(c.request.headers["Prefer"] == "wait=2" for c in job_route.calls)
    assert sed_route.call_count == 1 and sed.id == NEW
    # The server waited each time, so no client-side pause.
    assert all(s <= 1.0 for s in sleeps)


def test_no_data_raises_with_empty_sed(mock_api, client):
    mock_api.post("/api/sed/").mock(return_value=httpx.Response(
        200, json=envelope("no_data", sed=EMPTY)))
    with pytest.raises(SEDNoData) as exc:
        client.sed.get(33.1, -71.3)
    assert exc.value.id == JID
    assert exc.value.sed.points == 0 and exc.value.sed.source.name == "Mrk 421"


def test_failed_cooldown_raises_with_code_and_retry(mock_api, client):
    body = envelope("failed", sed=None, error=FAILED_ERR)
    body["error"] = FAILED_ERR
    mock_api.post("/api/sed/").mock(return_value=httpx.Response(200, json=body))
    with pytest.raises(SEDJobFailed) as exc:
        client.sed.get(1.6083, 72.9836)
    assert (exc.value.id, exc.value.code, exc.value.retry_after_s) == (JID, "timeout", 1260)


def test_job_failing_while_followed(mock_api, client, sleeps):
    mock_api.post("/api/sed/").mock(return_value=httpx.Response(
        202, headers=RUNNING, json=envelope("queued", NEW, sed=None, events=[])))
    err = {"code": "abandoned", "message": "The worker stopped.", "retry_after_s": 1800}
    mock_api.get(f"/api/sed/jobs/{NEW}/").mock(return_value=httpx.Response(
        200, json=job("failed", NEW, events=[event(0, level="error", subject="Failed")],
                      error=err)))
    job_ = client.sed.submit(1.0, 2.0)
    with pytest.raises(SEDJobFailed) as exc:
        job_.result()
    assert exc.value.code == "abandoned" and exc.value.id == NEW
    assert job_.events[-1].subject == "Failed"


def test_400_raises_validation_error(mock_api, client):
    mock_api.post("/api/sed/").mock(return_value=httpx.Response(400, json={"error": {
        "code": "invalid", "message": "The request is not valid.",
        "fields": {"dec": ["Ensure this value is less than or equal to 90."]}}}))
    with pytest.raises(ValidationError) as exc:
        client.sed.get(1.0, 95.0)
    assert exc.value.validation_type == "invalid"
    assert "dec" in exc.value.details


def test_404_unknown_id(mock_api, client):
    mock_api.get("/api/sed/jobs/nope/").mock(return_value=httpx.Response(
        404, json={"error": {"code": "not_found", "message": "No SED job with this id."}}))
    with pytest.raises(NotFoundError, match="No SED job"):
        client.sed.job("nope")


def test_503_enqueue_retries_then_fails_with_retry_after(mock_api, client, sleeps):
    body = {"id": NEW, "status": "failed",
            "error": {"code": "enqueue", "message": "The job could not be queued.",
                      "retry_after_s": 30}, "links": links(NEW)}
    route = mock_api.post("/api/sed/").mock(return_value=httpx.Response(
        503, headers={"Retry-After": "30"}, json=body))
    with pytest.raises(SEDJobFailed) as exc:
        client.sed.get(1.0, 2.0)
    assert exc.value.code == "enqueue" and exc.value.retry_after_s == 30
    # POST /api/sed/ is idempotent by position, so it is retried after Retry-After.
    assert route.call_count == 3
    assert all(30 <= s <= 37.5 for s in sleeps)


def test_503_then_success(mock_api, client, sleeps):
    mock_api.post("/api/sed/").mock(side_effect=[
        httpx.Response(503, headers={"Retry-After": "30"}, json={
            "id": NEW, "status": "failed", "error": {"code": "enqueue", "message": "x",
                                                    "retry_after_s": 0}}),
        httpx.Response(200, json=envelope("done")),
    ])
    assert client.sed.get(1.0, 2.0).status == "done"


def test_over_cap_answer_falls_back_to_short_polling(mock_api, client, sleeps):
    # Over the wait cap the server answers at once with Retry-After: 2 and no Preference-Applied.
    mock_api.post("/api/sed/").mock(return_value=httpx.Response(
        202, headers={"Retry-After": "2"}, json=envelope("running", NEW, sed=None, events=[])))
    mock_api.get(f"/api/sed/jobs/{NEW}/").mock(side_effect=[
        httpx.Response(200, headers={"Retry-After": "2"}, json=job("running", NEW, events=[])),
        httpx.Response(200, headers={"Retry-After": "2"}, json=job("running", NEW, events=[])),
        httpx.Response(200, json=job("done", NEW, events=[])),
    ])
    mock_api.get(f"/api/sed/{NEW}/").mock(return_value=httpx.Response(200, json=envelope("done", NEW)))
    client.sed.get(1.0, 2.0)
    # One pause after the POST that did not wait, then one after each early job answer.
    assert len(sleeps) == 3 and all(1.9 <= s <= 2.0 for s in sleeps)


def test_timeout_carries_job_id(mock_api, client, sleeps, monkeypatch):
    clock = iter(range(0, 10_000, 10))
    monkeypatch.setattr("astro_mmdc.resources.sed.time.monotonic", lambda: next(clock))
    mock_api.post("/api/sed/").mock(return_value=httpx.Response(
        202, headers=RUNNING, json=envelope("running", NEW, sed=None, events=[])))
    mock_api.get(f"/api/sed/jobs/{NEW}/").mock(return_value=httpx.Response(
        200, headers={"Retry-After": "1", "Preference-Applied": "wait=20"},
        json=job("running", NEW, events=[])))
    with pytest.raises(SEDTimeoutError) as exc:
        client.sed.get(1.0, 2.0, timeout=100)
    assert exc.value.id == exc.value.uuid == NEW
    assert isinstance(exc.value, TimeoutError) and isinstance(exc.value, PollingTimeoutError)


def test_wait_is_capped_by_remaining_timeout(mock_api, client, sleeps):
    route = mock_api.post("/api/sed/").mock(return_value=httpx.Response(200, json=envelope("done")))
    client.sed.get(1.0, 2.0, timeout=5)
    assert route.calls[0].request.headers["Prefer"] == "wait=5"


def test_events_since_paging_on_refresh(mock_api, client):
    mock_api.post("/api/sed/").mock(return_value=httpx.Response(200, json=envelope(
        "done", events_next=3)))
    route = mock_api.get(f"/api/sed/jobs/{JID}/").mock(side_effect=[
        httpx.Response(200, json=job("done", events=[event(0), event(1)], events_next=3)),
        httpx.Response(200, json=job("done", events=[event(2)], events_next=3)),
    ])
    j = client.sed.submit(1.0, 2.0)
    assert j.events == [] and j.done
    j.refresh()
    j.refresh()
    assert [c.request.url.params["events_since"] for c in route.calls] == ["0", "2"]
    assert [e.subject for e in j.events] == ["Cat0", "Cat1", "Cat2"]
    assert j.events[0].render() == "[00:00] INFO   Cat0          line"


def test_submit_handle_and_stale_refresh_info(mock_api, client):
    body = envelope("done")
    body["stale"] = True
    body["refresh"] = {"id": NEW, "status": "failed", "error": FAILED_ERR,
                       "links": {"job": f"/api/sed/jobs/{NEW}/"}}
    mock_api.post("/api/sed/").mock(return_value=httpx.Response(200, json=body))
    j = client.sed.submit(1.0, 2.0)
    assert isinstance(j, SEDJob) and j.id == JID and j.status == "done" and j.stale
    sed = j.result()
    assert sed.stale and sed.refresh.status == "failed" and sed.refresh.error.code == "timeout"


def test_source_only(mock_api, client):
    route = mock_api.post("/api/sed/").mock(return_value=httpx.Response(
        200, json=envelope("done", sed=None)))
    src = client.sed.source(166.113808, 38.208833)
    assert route.calls[0].request.url.params["sed"] == "false"
    assert src.redshift == 0.0308 and src.w_peak.text == "> 17.5"


def test_source_only_waits_for_new_job(mock_api, client, sleeps):
    mock_api.post("/api/sed/").mock(return_value=httpx.Response(
        202, headers=RUNNING, json=envelope("running", NEW, sed=None, events=[])))
    mock_api.get(f"/api/sed/jobs/{NEW}/").mock(return_value=httpx.Response(
        200, json=job("done", NEW, events=[])))
    sed_route = mock_api.get(f"/api/sed/{NEW}/").mock(return_value=httpx.Response(
        200, json=envelope("done", NEW, sed=None)))
    assert client.sed.source(1.0, 2.0).redshift == 0.0308
    assert sed_route.calls[0].request.url.params["sed"] == "false"


def test_fetch_by_id_and_replaced_id(mock_api, client):
    mock_api.get(f"/api/sed/{JID}/").mock(return_value=httpx.Response(
        200, headers={"Content-Location": f"/api/sed/{NEW}/"}, json=envelope("done", NEW)))
    assert client.sed.fetch(JID).id == NEW


def test_server_csv_and_409(mock_api, client, tmp_path):
    mock_api.get(f"/api/sed/{JID}/", params={"format": "csv"}).mock(
        return_value=httpx.Response(200, text=SERVER_CSV))
    dest = tmp_path / "x.csv"
    assert client.sed.csv(JID, dest) == SERVER_CSV and dest.read_text() == SERVER_CSV
    mock_api.get(f"/api/sed/{NEW}/", params={"format": "csv"}).mock(return_value=httpx.Response(
        409, json={"error": {"code": "not_ready", "message": "The SED is not ready."}}))
    with pytest.raises(Exception, match="not ready"):
        client.sed.csv(NEW)


def test_get_many_in_order_with_exceptions(mock_api, client):
    def answer(request):
        ra = json.loads(request.content)["ra"]
        if ra == 2.0:
            return httpx.Response(200, json=envelope("no_data", sed=EMPTY))
        return httpx.Response(200, json=envelope("done", i=f"id-{ra}"))

    mock_api.post("/api/sed/").mock(side_effect=answer)
    out = client.sed.get_many([(1.0, 1.0), {"ra": 2.0, "dec": 2.0}, (3.0, 3.0, "c")],
                              return_exceptions=True)
    assert out[0].id == "id-1.0" and isinstance(out[1], SEDNoData) and out[2].id == "id-3.0"
    with pytest.raises(SEDNoData):
        client.sed.get_many([(2.0, 2.0)])


def test_end_user_header_on_new_calls(mock_api):
    route = mock_api.post("/api/sed/").mock(return_value=httpx.Response(200, json=envelope("done")))
    with MMDC(api_key="k") as c:
        c.for_user("u-1").sed.get(1.0, 2.0)
    assert route.calls[0].request.headers["X-MMDC-End-User"] == "u-1"
    assert route.calls[0].request.headers["X-API-Key"] == "k"


def test_progress_true_prints_events(mock_api, client, capsys, sleeps):
    mock_api.post("/api/sed/").mock(return_value=httpx.Response(
        202, headers=RUNNING, json=envelope("running", NEW, sed=None, events=[event(0, "hello")])))
    mock_api.get(f"/api/sed/jobs/{NEW}/").mock(return_value=httpx.Response(
        200, json=job("done", NEW, events=[])))
    mock_api.get(f"/api/sed/{NEW}/").mock(return_value=httpx.Response(200, json=envelope("done", NEW)))
    client.sed.get(1.0, 2.0, progress=True)
    assert "[00:00] INFO   Cat0          hello" in capsys.readouterr().err


# -- the SED object ----------------------------------------------------------------


def make_sed():
    return SED.from_api(envelope("done"))


def test_to_csv_matches_server_csv(tmp_path):
    sed = make_sed()
    assert sed.to_csv() == SERVER_CSV and SERVER_CSV.endswith("\n") and "\r" not in SERVER_CSV
    p = tmp_path / "s.csv"
    sed.to_csv(p)
    assert list(csv.reader(io.StringIO(p.read_text())))[1][6] == "NVSS"


def make_sed_50000(column=True):
    obj = {**SED_OBJ, "mjd_start": [50000.0, 56669.2, 56850.9], "mjd_end": [50000.0, 56669.2, 56850.9]}
    if column:
        obj["undated"] = [True, False, False]
    return SED.from_api(envelope("done", sed=obj))


@pytest.mark.parametrize("make", [make_sed, make_sed_50000, lambda: make_sed_50000(False)])
def test_between_drops_undated_with_a_window(make):
    sed = make()  # undated column, or derived from None / 50000 MJDs (older servers)
    assert sed.undated == sed.is_undated == [True, False, False]
    b = sed.between(56600, 56700)
    assert b.freq_hz == [6.52e13] and [c.name for c in b.catalogs] == ["NEOWISE"]
    assert b.undated == [False] and b.filters["undated"] is False
    assert sed.between(49000, 56700).catalog == ["NEOWISE"]  # covering 50000 is not enough
    assert sed.between().catalog == ["NVSS", "NEOWISE", "NEOWISE"]
    assert sed.between(undated=False).catalog == ["NEOWISE", "NEOWISE"]
    assert sed.between(56600, 56700, undated=True).catalog == ["NVSS", "NEOWISE"]
    only = sed.between(56800, None)
    assert only.nufnu == [2.9e-11] and only.catalog_idx == [0] and only.is_ul == [True]
    assert sed.points == 3  # the original is untouched


def test_between_uses_the_midpoint_in_a_closed_window():
    obj = {
        **SED_OBJ,
        "points": 4,
        "freq_hz": [1.4e9, 6.52e13, 6.52e13, 6.52e13],
        "nufnu": [1.0, 2.0, 3.0, 4.0],
        "nufnu_err": [None] * 4,
        "is_ul": [False] * 4,
        "catalog_idx": [0, 1, 1, 1],
        # Midpoints 57999.5 (ends at the window start), 58000.25 and 58001.25 (bins
        # sharing the edge 58000.5), and 58001.0 (exactly the window end).
        "mjd_start": [57999.0, 58000.0, 58000.5, 58000.5],
        "mjd_end": [58000.0, 58000.5, 58002.0, 58001.5],
        "undated": [False] * 4,
    }
    sed = SED.from_api(envelope("done", sed=obj))
    assert sed.between(58000, 58001).nufnu == [2.0, 4.0]
    assert sed.between(58001, 58002).nufnu == [3.0, 4.0]  # a midpoint on the start counts too
    assert sed.between(None, 57999.5).nufnu == [1.0]
    assert sed.between(57999.5, None).points == 4


def test_undated_fallback_needs_both_ends():
    obj = {**SED_OBJ, "mjd_start": [None, 50000.0, 50000.0], "mjd_end": [None, 50001.0, 50000.0]}
    sed = SED.from_api(envelope("done", sed=obj))
    assert sed.undated == [True, False, True]
    assert sed.to_pandas()["undated"].tolist() == [True, False, True]


def test_window_sends_undated_false_unless_given(mock_api, client):
    route = mock_api.get(f"/api/sed/{JID}/").mock(return_value=httpx.Response(200, text=SERVER_CSV))
    client.sed.csv(JID, mjd_start=58020, mjd_end=58022)
    q = route.calls.last.request.url.params
    assert q["mjd_start"] == "58020" and q["mjd_end"] == "58022" and q["undated"] == "false"
    client.sed.csv(JID, mjd_start=58020, undated=True)
    assert route.calls.last.request.url.params["undated"] == "true"
    client.sed.csv(JID)
    assert "undated" not in route.calls.last.request.url.params


def test_select_and_exclude():
    sed = make_sed()
    assert sed.select(["NEOWISE"]).catalog == ["NEOWISE", "NEOWISE"]
    assert sed.select(exclude=["NEOWISE"]).catalog == ["NVSS"]


def test_table_and_rows():
    sed = make_sed()
    df = sed.table
    assert list(df.columns) == ["freq_hz", "nufnu", "nufnu_err", "is_ul", "mjd_start",
                                "mjd_end", "catalog", "band", "reference", "undated"]
    assert len(df) == 3 and df["catalog"].tolist() == ["NVSS", "NEOWISE", "NEOWISE"]
    conv = sed.to_pandas(x="eV", y="Jy")
    assert conv["x"][0] == pytest.approx(1.4e9 * units.PLANCK_CONST_EV)
    assert sed.rows()[2]["nufnu_err"] is None


def test_plot(tmp_path):
    pytest.importorskip("matplotlib")
    import matplotlib

    matplotlib.use("Agg")
    sed = make_sed()
    ax = sed.plot(tmp_path / "sed.png", x="eV", y="flux_jyhz")
    assert (tmp_path / "sed.png").stat().st_size > 0
    assert "eV" in ax.get_xlabel() and "Jy" in ax.get_ylabel()


# -- units against the website's formulas --------------------------------------------

# Golden values from the website's conversion formulas, per (freq Hz, νFν erg cm⁻² s⁻¹).
_WEBSITE_UNITS = {
    (1400000000.0, 1.1e-14): {
        "freq_ev": 5.789934774400001e-06,
        "erg": 1.1e-14,
        "flux_ev": 6.8662e-15,
        "flux_norm": 204818464.95699468,
        "flux_jyhz": 1100000000.0,
        "flux_wm2": 1.1e-17,
        "nufnu_fnu_jy": 0.7857142857142857,
    },
    (1400000000.0, 3.2e-11): {
        "freq_ev": 5.789934774400001e-06,
        "erg": 3.2e-11,
        "flux_ev": 1.99744e-11,
        "flux_norm": 595835534420.3481,
        "flux_jyhz": 3199999999999.9995,
        "flux_wm2": 3.1999999999999996e-14,
        "nufnu_fnu_jy": 2285.7142857142853,
    },
    (65200000000000.0, 1.1e-14): {
        "freq_ev": 0.26964553377920003,
        "erg": 1.1e-14,
        "flux_ev": 6.8662e-15,
        "flux_norm": 0.09443434813968102,
        "flux_jyhz": 1100000000.0,
        "flux_wm2": 1.1e-17,
        "nufnu_fnu_jy": 1.6871165644171778e-05,
    },
    (65200000000000.0, 3.2e-11): {
        "freq_ev": 0.26964553377920003,
        "erg": 3.2e-11,
        "flux_ev": 1.99744e-11,
        "flux_norm": 274.71810367907204,
        "flux_jyhz": 3199999999999.9995,
        "flux_wm2": 3.1999999999999996e-14,
        "nufnu_fnu_jy": 0.04907975460122699,
    },
    (2.4e+17, 1.1e-14): {
        "freq_ev": 992.56024704,
        "erg": 1.1e-14,
        "flux_ev": 6.8662e-15,
        "flux_norm": 6.969517210342182e-09,
        "flux_jyhz": 1100000000.0,
        "flux_wm2": 1.1e-17,
        "nufnu_fnu_jy": 4.583333333333333e-09,
    },
    (2.4e+17, 3.2e-11): {
        "freq_ev": 992.56024704,
        "erg": 3.2e-11,
        "flux_ev": 1.99744e-11,
        "flux_norm": 2.0274959157359073e-05,
        "flux_jyhz": 3199999999999.9995,
        "flux_wm2": 3.1999999999999996e-14,
        "nufnu_fnu_jy": 1.3333333333333332e-05,
    },
    (2.4e+25, 1.1e-14): {
        "freq_ev": 99256024704.0,
        "erg": 1.1e-14,
        "flux_ev": 6.8662e-15,
        "flux_norm": 6.969517210342182e-25,
        "flux_jyhz": 1100000000.0,
        "flux_wm2": 1.1e-17,
        "nufnu_fnu_jy": 4.583333333333333e-17,
    },
    (2.4e+25, 3.2e-11): {
        "freq_ev": 99256024704.0,
        "erg": 3.2e-11,
        "flux_ev": 1.99744e-11,
        "flux_norm": 2.0274959157359075e-21,
        "flux_jyhz": 3199999999999.9995,
        "flux_wm2": 3.1999999999999996e-14,
        "nufnu_fnu_jy": 1.333333333333333e-13,
    },
}


def test_dnde_is_nufnu_over_e_squared():
    # 1e-10 erg cm-2 s-1 at 1 GeV is 6.24e-17 eV-1 cm-2 s-1.
    (value,) = units.convert_y([1e-10], [1e9 / units.PLANCK_CONST_EV], "dN/dE")
    assert value == pytest.approx(1e-10 * 6.242e11 / 1e9**2, rel=1e-12)


@pytest.mark.parametrize(("freq", "flux"), list(_WEBSITE_UNITS))
def test_units_match_website(freq, flux):
    expect = dict(_WEBSITE_UNITS[(freq, flux)])
    assert units.convert_x([freq], "freq_ev") == [expect.pop("freq_ev")]
    for key, value in expect.items():
        # Bit-identical: the y conversion always takes freq in Hz (the website's fixed order).
        assert units.convert_y([flux], [freq], key) == [value], key


def test_units_aliases_and_missing():
    assert units.y_unit("flux_jyhz") == "Jy Hz" and units.x_unit("hz") == "Hz"
    assert units.convert_y([None, 1.0], [1e10, None], "Jy") == [None, None]
    assert units.convert_y([1.0], [0.0], "Jy") == [None]
    with pytest.raises(ValueError):
        units.convert_y([1.0], [1.0], "furlong")


def test_get_many_default_runs_two_at_a_time(mock_api, client, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor

    seen = {}

    class Pool(ThreadPoolExecutor):
        def __init__(self, max_workers):
            seen["workers"] = max_workers
            super().__init__(max_workers=max_workers)

    monkeypatch.setattr("astro_mmdc.resources.sed.ThreadPoolExecutor", Pool)
    mock_api.post("/api/sed/").mock(return_value=httpx.Response(200, json=envelope("done")))
    client.sed.get_many([(1.0, 1.0)])
    assert seen["workers"] == 2


# -- review fixes ---------------------------------------------------------------


def test_get_many_stops_at_first_failure(mock_api, client, sleeps):
    import time as _time

    def answer(request):
        ra = json.loads(request.content)["ra"]
        if ra == 1.0:
            body = envelope("failed", i="bad", sed=None, error=FAILED_ERR)
            body["error"] = FAILED_ERR
            return httpx.Response(200, json=body)
        return httpx.Response(202, headers=RUNNING,
                              json=envelope("running", f"slow-{ra}", sed=None, events=[]))

    # No job route: a cancelled worker stops at its first progress check.
    posts = mock_api.post("/api/sed/").mock(side_effect=answer)
    started = _time.monotonic()
    with pytest.raises(SEDJobFailed) as exc:
        client.sed.get_many([(1.0, 1.0), (2.0, 2.0), (3.0, 3.0), (4.0, 4.0)])
    assert exc.value.id == "bad" and _time.monotonic() - started < 5
    _time.sleep(0.2)  # let the cancelled worker notice
    ras = sorted(json.loads(c.request.content)["ra"] for c in posts.calls)
    assert 3.0 not in ras and 4.0 not in ras


def test_failed_refresh_returns_previous_sed_stale(mock_api, client, sleeps):
    running = envelope("running", NEW, sed=None, reused=False, events=[])
    running["job"]["refresh_of"] = JID
    mock_api.post("/api/sed/").mock(return_value=httpx.Response(202, headers=RUNNING, json=running))
    err = {"code": "empty_refresh", "message": "The new run found no data; the previous SED is kept.",
           "retry_after_s": 0}
    failed = job("failed", NEW, events=[], error=err)
    failed["refresh_of"] = JID
    mock_api.get(f"/api/sed/jobs/{NEW}/").mock(return_value=httpx.Response(200, json=failed))
    old = envelope("done")
    old["stale"] = True
    old["refresh"] = {"id": NEW, "status": "failed", "error": err, "links": {}}
    mock_api.get(f"/api/sed/{JID}/").mock(return_value=httpx.Response(200, json=old))
    with pytest.warns(Warning, match="empty_refresh"):
        sed = client.sed.get(1.0, 2.0, refresh=True)
    assert sed.id == JID and sed.stale and sed.refresh.error.code == "empty_refresh"
    assert sed.points == 3


def test_failed_refresh_without_previous_sed_raises(mock_api, client, sleeps):
    running = envelope("running", NEW, sed=None, events=[])
    mock_api.post("/api/sed/").mock(return_value=httpx.Response(202, headers=RUNNING, json=running))
    failed = job("failed", NEW, events=[], error={"code": "pipeline", "message": "x",
                                                   "retry_after_s": 0})
    failed["refresh_of"] = JID
    mock_api.get(f"/api/sed/jobs/{NEW}/").mock(return_value=httpx.Response(200, json=failed))
    mock_api.get(f"/api/sed/{JID}/").mock(return_value=httpx.Response(
        200, json=envelope("no_data", sed=EMPTY)))
    with pytest.raises(SEDJobFailed, match="pipeline"):
        client.sed.get(1.0, 2.0, refresh=True)


def test_503_never_blocks_past_timeout(mock_api, client, sleeps):
    body = {"id": NEW, "status": "failed", "links": links(NEW),
            "error": {"code": "enqueue", "message": "x", "retry_after_s": 30}}
    route = mock_api.post("/api/sed/").mock(return_value=httpx.Response(
        503, headers={"Retry-After": "30"}, json=body))
    with pytest.raises(SEDTimeoutError) as exc:
        client.sed.get(1.0, 2.0, timeout=10)
    assert exc.value.id == NEW and route.call_count == 1 and sleeps == []


def test_429_raises_rate_limit_error(mock_api, client, sleeps):
    from astro_mmdc import RateLimitError

    mock_api.get(f"/api/sed/jobs/{JID}/").mock(return_value=httpx.Response(
        429, headers={"Retry-After": "3"}, json={"error": {"code": "throttled", "message": "slow down"}}))
    with pytest.raises(RateLimitError) as exc:
        client.sed.job(JID)
    assert exc.value.retry_after == 3


def test_csv_of_running_job_raises_not_ready(mock_api, client):
    from astro_mmdc import APIError, SEDNotReady

    mock_api.get(f"/api/sed/{NEW}/", params={"format": "csv"}).mock(return_value=httpx.Response(
        409, json={"error": {"code": "not_ready", "message": "The SED is not ready."}}))
    with pytest.raises(SEDNotReady) as exc:
        client.sed.csv(NEW)
    assert exc.value.id == NEW and isinstance(exc.value, APIError)


def test_exceptions_pickle():
    import pickle

    from astro_mmdc import SEDNotReady

    for e in (SEDTimeoutError("late", id="x"), SEDJobFailed("x", "timeout", "m", 30),
              SEDNoData("x", make_sed()), SEDNotReady("x", "busy")):
        back = pickle.loads(pickle.dumps(e))
        assert type(back) is type(e) and str(back) == str(e) and back.id == "x"
    assert pickle.loads(pickle.dumps(SEDJobFailed("x", "timeout", "m", 30))).retry_after_s == 30


class _Angle:
    def __init__(self, deg):
        self.deg = deg


class _Quantity:
    def __init__(self, v):
        self.v = v

    def to_value(self, unit):
        assert unit == "deg"
        return self.v


class _SkyCoord:
    def __init__(self, ra, dec):
        self.ra, self.dec = _Angle(ra), _Angle(dec)


def test_astropy_style_positions(mock_api, client):
    route = mock_api.post("/api/sed/").mock(return_value=httpx.Response(200, json=envelope("done")))
    client.sed.get(_SkyCoord(166.1, 38.2))
    client.sed.get(_Angle(1.5), _Quantity(-2.5), "q")
    client.sed.get_many([_SkyCoord(10.0, 20.0)])
    bodies = [json.loads(c.request.content) for c in route.calls]
    assert bodies[0] == {"ra": 166.1, "dec": 38.2}
    assert bodies[1] == {"ra": 1.5, "dec": -2.5, "name": "q"}
    assert bodies[2] == {"ra": 10.0, "dec": 20.0}


def test_select_empty_list_is_empty_selection():
    sed = make_sed().select([])
    assert sed.points == 0 and sed.filters["catalogs"] == []


def test_source_without_w_peak():
    body = envelope("done")
    body["source"] = {**SOURCE, "w_peak": None, "redshift": None}
    sed = SED.from_api(body)
    assert sed.source.w_peak is None and sed.source.redshift is None
