---
title: "Using MMDC from scripts and AI agents"
description: "How scripts, pipelines and AI agents should call MMDC (mmdc.am): identification, name resolution, SEDs, light curves, model fits, Swift analysis, raw HTTP with Prefer: wait, limits and citation."
---

# Using MMDC from scripts and AI agents

This page is for code that calls MMDC without a person at the browser: scripts, notebooks run in
batch, pipelines and AI agents. It collects the rules such a client should follow and one recipe
per task. The [Python SDK](getting-started.md) follows these rules for you; the
[raw HTTP](#raw-http) section shows them for other languages.

**Rules in short**

1. Positions are ICRS right ascension and declination in **degrees**.
2. Resolve a source name to a position first; the SED API takes positions, not names.
3. Identify your client: the SDK does, and `MMDC(app="your-project")` names your project.
   Raw HTTP must send an `X-MMDC-Client` header, or modeling requests get HTTP 426.
4. An SED request reuses any job within 2″. Do not send `refresh` routinely.
5. Run at most 2 jobs at a time, respect `Retry-After`, and wait with `Prefer: wait=25` instead
   of polling in a tight loop.
6. Undated catalogue values carry MJD 50000; they are not observations from 1995.
7. Cite Sahakyan et al. 2024, AJ, 168, 289 ([doi:10.3847/1538-3881/ad8231](https://doi.org/10.3847/1538-3881/ad8231)).
   MMDC data are licensed under CC BY 4.0.

## Install and identify

```bash
pip install astro-mmdc
```

```python
from astro_mmdc import MMDC

client = MMDC(app="my-pipeline")
```

Every SDK request carries `User-Agent: astro-mmdc/<version>`. `app` adds an `X-MMDC-Client`
header with your project name, which keeps your jobs apart from other SDK users behind the same
IP address. An `api_key` (sent as `X-API-Key`) gives a higher limit on concurrent fits; see
[Identifying your application and users](getting-started.md#identifying-your-application-and-users).

## Resolve a name to a position

MMDC's own name lookup is `POST https://mmdc.am/api/autocomplete/` with `{"query": "<name>"}`.
It answers `{"results": [{"name", "ra", "dec", "refcatalog"}, ...]}`, positions in degrees:

```python
import httpx

r = httpx.post("https://mmdc.am/api/autocomplete/", json={"query": "Mrk 421"},
               headers={"X-MMDC-Client": "my-pipeline"})
hits = r.json()["results"]   # [{"name": "MRK421", "ra": 166.1138, "dec": 38.20883, ...}]
ra, dec = hits[0]["ra"], hits[0]["dec"]
```

A query can match several entries (`3C 273` gives two); pick one, or ask the user. Astropy's
resolver (SIMBAD/NED/VizieR) works as well, and the SDK accepts the `SkyCoord` directly:

```python
from astropy.coordinates import SkyCoord

coord = SkyCoord.from_name("Mrk 421")
sed = client.sed.get(coord, name="Mrk 421")
```

## SED of a source

```python
from astro_mmdc import SEDJobFailed, SEDNoData, SEDTimeoutError

try:
    sed = client.sed.get(ra=166.113808, dec=38.208833, name="Mrk 421")
except SEDNoData:
    raise SystemExit("no points at this position")   # the pipeline ran and found nothing
except SEDJobFailed as exc:
    raise SystemExit(f"failed: {exc.code}, retry after {exc.retry_after_s} s")
except SEDTimeoutError as exc:
    sed = client.sed.fetch(exc.id)   # the job keeps running on the server; pick it up later

print(sed.source.redshift, sed.points)
sed.freq_hz, sed.nufnu, sed.nufnu_err, sed.is_ul   # columns, one entry per point
sed.mjd_start, sed.mjd_end, sed.undated, sed.catalog
```

`freq_hz` is in Hz, `nufnu` and `nufnu_err` in erg cm⁻² s⁻¹; for an upper limit (`is_ul`)
`nufnu` is the limit. Most positions are cached and answer in one request; a new position runs
about 60 catalogues and takes up to a few minutes. `get()` waits up to `timeout` (900 s by
default).

Filter by time on the client or on the server, then save:

```python
recent = sed.between(58000, 58400)          # midpoint in [58000, 58400]; undated points dropped
sed = client.sed.get(ra=166.113808, dec=38.208833, mjd_start=58000, mjd_end=58400)
recent.to_csv("mrk421.csv")                 # freq_hz,nufnu,nufnu_err,is_ul,mjd_start,mjd_end,catalog,band,reference
```

Undated catalogue values have `mjd_start` = `mjd_end` = 50000 and `undated` True. A time window
drops them unless you pass `undated=True`.

For many sources use `client.sed.get_many(...)`, which runs 2 at a time by default:

```python
seds = client.sed.get_many([(166.113808, 38.208833, "Mrk 421"), (187.2779, 2.0524, "3C 273")],
                           return_exceptions=True)
```

More in the [SED data guide](guides/sed.md).

## Light curve

Light-curve rows (Fermi-LAT, Swift UVOT/XRT, NuSTAR, ASAS-SN, ZTF, Pan-STARRS, SMARTS) come
from the observations table by cone search:

```python
rows = client.observations.cone_search(ra=166.113808, dec=38.208833, radius_arcsec=10,
                                       is_lightcurve=True, ordering="mjd_mid")
for row in rows:
    print(row.catalog, row.filter_band, row.mjd_mid, row.flux, row.flux_err)
```

Filter with `catalog=`, `filter_band=`, `mjd_min=`/`mjd_max=` and `limit=`; see the
[Observations guide](guides/observations.md) for the catalogue codes.

## Quick model curve

`infer()` computes one SSC, EIC or hadronic model curve from given parameters, synchronously:

```python
curve = client.modeling.infer(
    z=0.031, ebl=True, model_type="SSC",
    parameters={"log_B": -1.5, "log_electron_luminosity": 44.0, "log_gamma_cut": 5.0,
                "log_gamma_min": 2.0, "log_radius": 16.0, "lorentz_factor": 20.0,
                "spectral_index": 2.2},
)
print(curve.nu, curve.nuFnu)
```

When all inference slots are busy the server answers 429 with `Retry-After: 10`; the SDK does not
retry this POST, so retry it yourself after that delay.

## Fit a model to an SED

A fit is a batch job. Validate the file, submit it, keep the id, then wait:

```python
from astro_mmdc import BatchJobError, PollingTimeoutError

check = client.modeling.validate_csv("mrk421.csv")
print(check.success, check.data_points)

submission = client.modeling.submit_batch("mrk421.csv", z=0.031, ebl=True, model_type="SSC")
fit_id = submission.batch_result_id
try:
    result = client.modeling.wait_for_batch(fit_id, max_minutes=30)
except PollingTimeoutError:
    raise SystemExit(f"still queued or running; call wait_for_batch({fit_id!r}) later")
except BatchJobError as exc:
    raise SystemExit(f"fit failed: {exc.status}")

for name, p in (result.best_parameters or {}).items():
    print(name, p.value, p.error)
print(result.pdf_link)
```

`batch_infer(...)` does submit and wait in one call, but waits only `max_minutes=8` by default.
A fit takes from about 10–20 s (SSC) to a few minutes (EIC, HADRONIC), plus any time in the
queue, so pass a larger `max_minutes` when the queue may be busy. The SED CSV from
`sed.to_csv()` is accepted as is; keep one time period. Results are deleted 15 days after
submission. See [Blazar emission modeling](guides/modeling.md).

## Swift UVOT/XRT analysis

`madam.analyze()` runs the Swift pipeline on a position and a time window (or obsids). A request
already covered by an earlier run answers at once from the cache; a new run downloads Swift data
and can take from minutes to hours:

```python
job = client.madam.analyze(ra=166.1138, dec=38.2088, mjd_start=58849, mjd_end=59031,
                           instrument="uvot")
print(job.status, job.cached, job.count)        # "done" or "no_data"
lc = [r for r in job.results or [] if r.is_lightcurve]
for row in lc:
    print(row.obsid, row.filter_band, row.mjd_mid, row.flux)
```

Each measurement comes twice: as a light-curve row (`is_lightcurve=True`, `mjd_mid`) and as
an SED row (`frequency`, `mjd_start`/`mjd_end`).

`instrument` is `"uvot"`, `"xrt"` or `"swift"` (both). The rows also land in the observations
table, under `MMDCOUV`, `MMDCXRT` and `MMDCXRT_ORBIT`. See the
[Swift guide](guides/swift.md).

## Raw HTTP { #raw-http }

Every SDK call is plain HTTP under `https://mmdc.am/api/`. Without the SDK, send an
`X-MMDC-Client` header on every request.

**SED.** `POST /api/sed/` with `{"ra": <deg>, "dec": <deg>, "name": "<optional>"}`:

```bash
curl -s -X POST https://mmdc.am/api/sed/ \
  -H 'Content-Type: application/json' \
  -H 'X-MMDC-Client: my-pipeline' \
  -H 'Prefer: wait=25' \
  -d '{"ra": 166.113808, "dec": 38.208833, "name": "Mrk 421"}'
```

- The answer has `id`, `status` (`queued`, `running`, `done`, `no_data`, `failed`), `reused`,
  `source` (`name`, `ra`, `dec`, `redshift`, `w_peak`), `job` (timing, `progress`, `events`,
  `error`), `links`, and, once done, `sed`: `units`, `catalogs`, and the columns `freq_hz`,
  `nufnu`, `nufnu_err`, `is_ul`, `mjd_start`, `mjd_end`, `undated` and `catalog_idx` (an index
  into `catalogs`).
- `200` means finished (`done`, `no_data` or `failed`, with `error.code` and
  `error.retry_after_s`). `202` means queued or running: send
  `GET /api/sed/<id>/` (also with `Prefer: wait=25`) until the status is terminal.
- `Prefer: wait=N` (or `?wait=N`) holds the answer until the job ends or `N` seconds pass,
  at most 25. The server holds at most 4 such requests site-wide and 2 per client; above that it
  answers at once with `Retry-After: 2`. `Preference-Applied` tells you it waited. Never assume
  it did: look at `status`.
- Query parameters: `sed=false` (source only), `mjd_start`, `mjd_end` (a point is kept when its
  midpoint lies in the window, ends included), `undated`, `catalogs=NVSS,NEOWISE`.
- `GET /api/sed/<id>/?format=csv` gives the CSV, `GET /api/sed/jobs/<id>/` the job with its
  progress and events.
- Errors: `400` with `error.fields` for a bad position or filter, `404` for an unknown id,
  `503` with `Retry-After: 30` when the job could not be queued.

**Modeling.** `POST /api/modeling/inference/`, `/api/modeling/validate_csv/` and
`/api/modeling/batch_inference/` need an identified client; poll a fit with
`GET /api/modeling/batch_result/<id>/` and `Prefer: wait=25`.

## Identification and HTTP 426 { #identification }

The modeling POSTs (inference, CSV validation, fits) accept a client that sends any of: a valid
`X-API-Key`, a `User-Agent` of `astro-mmdc/0.2.4` or newer, or an `X-MMDC-Client` header. Anything
else gets HTTP 426 and this body (the version is the server's current minimum, also sent as the
`X-MMDC-Min-Version` header):

```json
{
  "error": "upgrade_required",
  "reason": "unidentified",
  "detail": "Unidentified clients can no longer use the MMDC modeling API. Upgrade the Python SDK: pip install -U 'astro-mmdc>=0.2.4' (optionally identify your project with MMDC(app='your-app') or an API key). For an API key or User-Agent allowlisting contact mailtommdc@gmail.com.",
  "min_sdk_version": "0.2.4"
}
```

`reason` is `sdk_outdated` for an older SDK and `invalid_api_key` for a wrong key. Polling an
existing fit (`batch_result`) never answers 426. The SED, observations and Swift endpoints do not
require identification, but sending `X-MMDC-Client` everywhere costs nothing.

## Limits and etiquette

| What | Limit |
|---|---|
| `Prefer: wait` | at most 25 s per request. SED: 4 waiting requests site-wide, 2 per client; fit results (`batch_result`): 3 site-wide, 2 per client |
| Fits queued or running at once | 2 per client without an API key; 5 or 25 with one, by tier. Above it: 429, `Retry-After: 120` |
| Synchronous inference | 4 at once site-wide; above it: 429, `Retry-After: 10` |
| SED reuse | any job within 2″ is reused; a failed run is not retried for 30 min unless `refresh` is sent |
| Fit results | deleted 15 days after submission |

- Keep at most 2 jobs in flight; `get_many()` defaults to `max_concurrency=2`.
- On 429 or 503, wait for `Retry-After` before trying again. The SDK does this for GETs and
  for fit submissions.
- Wait with `Prefer: wait=25` and send the next request right after a `202`; do not poll faster
  than once a second.
- Send `refresh` only when you need data newer than the cached run, not on every request.
- For an API key or a higher limit, use the [contact form](https://mmdc.am/#contact).

## Citing

Cite the MMDC paper when you use MMDC data or models: Sahakyan et al. 2024, AJ, 168, 289,
[doi:10.3847/1538-3881/ad8231](https://doi.org/10.3847/1538-3881/ad8231). MMDC data are licensed
under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) and require attribution. BibTeX and
the SDK's Zenodo DOI are on [Citing](citing.md).
