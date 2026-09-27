# astro-mmdc

Python SDK for the [MMDC astrophysics platform](https://mmdc.am) — programmatic access to multi-wavelength SED data, on-demand Swift UVOT/XRT analysis and blazar broadband emission modeling.

MMDC provides APIs for querying astrophysical databases, preparing Spectral Energy Distribution (SED) data from multiple catalogs, running Swift photometry on demand, and running physics simulations for blazar emission modeling using SSC, EIC, and hadronic models.

## Installation

```bash
pip install astro-mmdc
```

Or with [uv](https://docs.astral.sh/uv/):

```bash
uv pip install astro-mmdc
```

Requires Python 3.10+.

---

## Quick Start

Get the SED of a source in 3 lines:

```python
from astro_mmdc import MMDC

client = MMDC()
sed = client.sed.get(ra=187.28, dec=2.05, name="3C 273")
print(sed.source.redshift, sed.points)
```

Run a quick SSC model inference:

```python
result = client.modeling.infer(
    z=0.158, ebl=True, model_type="SSC",
    parameters={"log_B": -1.5, "log_electron_luminosity": 44.0,
                "log_gamma_cut": 5.0, "log_gamma_min": 2.0,
                "log_radius": 16.0, "lorentz_factor": 20.0,
                "spectral_index": 2.2},
)
print(result.nu)     # Frequencies
print(result.nuFnu)  # Fluxes
```

Run Swift UVOT photometry for a source and time window:

```python
job = client.madam.analyze(ra=166.11, dec=38.21, mjd_start=58849, mjd_end=59031)
for row in job.results:
    if not row.is_lightcurve:
        print(row.obsid, row.filter_band, row.frequency, row.flux)
```

Or fit a model to data (async batch job):

```python
result = client.modeling.batch_infer(
    "observations.csv",
    z=0.158,
    ebl=True,
    model_type="SSC",
)
print(result.pdf_link)
print(result.best_parameters)
```

End-to-end pipeline — from sky coordinates to model fit:

```python
from astro_mmdc import MMDC

client = MMDC()

# Fetch SED data
job = client.sed.prepare_and_wait(
    ra=166.11, dec=38.21, database_name="Mkn421", source_name="Mkn 421"
)
info = client.sed.get_info(job.uuid)
client.sed.download_csv(job.uuid, "mkn421_sed.csv")

# Fit SSC model
result = client.modeling.batch_infer(
    "mkn421_sed.csv",
    z=info.redshift,
    ebl=True,
    model_type="SSC",
)

for name, param in result.best_parameters.items():
    print(f"{name}: {param.value:.4f} +/- {param.error:.4f}")
```

---

## Guide

### Creating a Client

```python
from astro_mmdc import MMDC

client = MMDC()

# Custom request timeout (seconds)
client = MMDC(timeout=60.0)

# As a context manager (auto-closes HTTP connection)
with MMDC() as client:
    ...
```

#### Identifying your application and users

```python
client = MMDC(
    app="my-project",           # sent as X-MMDC-Client
    api_key="mmdc_...",         # sent as X-API-Key; higher modeling tiers
    end_user="u42",             # sent as X-MMDC-End-User
)
```

If your service calls MMDC on behalf of many users, create one client and derive a per-user view for each request. Views share the connection pool and the parent's settings, and closing a view leaves the parent open:

```python
client = MMDC(app="my-project", api_key="mmdc_...")

def handle(request):
    mmdc = client.for_user(request.user.id)
    return mmdc.observations.cone_search(ra=187.28, dec=2.05)
```

`end_user` is an opaque id of your choice: 1–64 characters from letters, digits and `. _ : -`, never an email. Anything else raises `ValueError` at construction. MMDC records it only when a valid `api_key` is sent, and uses it for per-user usage statistics.

The client provides four resource namespaces:
- `client.sed` — multi-wavelength SED of any sky position
- `client.modeling` — blazar emission modeling (SSC, EIC, hadronic)
- `client.observations` — unified observations catalog (SED + lightcurve)
- `client.madam` — on-demand Swift UVOT/XRT analysis (MADAM pipeline)

---

### SED Data

`client.sed.get()` returns the SED at a sky position: the source (name,
coordinates, redshift, synchrotron peak), the job that built it and every point.
Most positions are cached and come back in one request; a new position runs the
pipeline over ~60 catalogues, which takes up to a few minutes. Any job within 2″
is reused.

```python
sed = client.sed.get(ra=166.113808, dec=38.208833, name="Mrk 421")

sed.source.redshift        # 0.0308 (None when unknown)
sed.source.w_peak          # None when unknown; else .log_nu (log10 Hz), .limit, .text ("> 17.5")
sed.catalogs               # [SEDCatalog(name="NVSS", band="radio_waves", reference=..., color=...), ...]
sed.missed_catalogs        # catalogues that could not be queried in this run, e.g. ["ZTF"]

# Points as columns (plain lists, None where missing)
sed.freq_hz, sed.nufnu, sed.nufnu_err, sed.is_ul, sed.mjd_start, sed.mjd_end
sed.catalog                # catalogue name of every point
sed.rows()                 # one dict per point
sed.table                  # pandas DataFrame (needs pandas)
```

Filter, convert, save and plot on the client:

```python
recent = sed.between(58000, 58400)            # MJD overlap; undated points kept unless undated=False
radio = sed.select(["NVSS", "FIRST"])         # or sed.select(exclude=["ZTF"])
sed.to_csv("mrk421.csv")                      # same columns as the server's CSV; returns the text
sed.converted(x="eV", y="Jy")                 # {"x": [...], "y": [...], "y_err": [...]}
recent.plot("mrk421.png", y="Jy Hz")          # needs astro-mmdc[plot]; returns the matplotlib Axes
```

Units are the website's: `x` is `Hz` or `eV`; `y` is `erg cm-2 s-1` (default),
`TeV cm-2 s-1`, `norm` (the website's dN/dE axis), `Jy Hz`, `W m-2` or `Jy` (F(ν)).
The website's axis keys (`freq_ev`, `flux_jyhz`, `nufnu_fnu_jy`, ...) work too.
The MJD and catalogue filters can also be applied by the server:
`client.sed.get(..., mjd_start=58000, mjd_end=58400, catalogs=["NVSS"])`.

**Progress.** `progress` is called with the job after every answer from the
server; `progress=True` prints the job's log to stderr:

```python
sed = client.sed.get(194.046527, -5.789312, "3C 279",
                     progress=lambda job: print(job.status, job.progress, len(job.new_events)))
```

**Refresh.** `refresh=True` runs the pipeline again. The old SED stays in place
until the new run succeeds. If the new run fails (including `empty_refresh`,
when it found no data where the old SED had points), `get()` returns the old SED
with `sed.stale == True` and the failed run in `sed.refresh`, and emits a
`SEDStaleWarning` naming the error code. It raises `SEDJobFailed` only when
there is no previous SED.

Positions are degrees as floats; astropy `Angle`s and a `SkyCoord`
(`client.sed.get(coord)`) work too.

**Source only.** The redshift and synchrotron peak without the points:

```python
src = client.sed.source(ra=166.113808, dec=38.208833)
print(src.redshift, src.w_peak)
```

**Many sources.** `get_many` runs up to `max_concurrency` at a time and keeps
the input order. Sources are `(ra, dec)` / `(ra, dec, name)` tuples, dicts or
objects with `ra`, `dec` and `name`:

```python
seds = client.sed.get_many(
    [(166.113808, 38.208833, "Mrk 421"), (253.467569, 39.760169, "Mrk 501")],
    return_exceptions=True,   # a failed source gives its exception instead of raising
)
```

Without `return_exceptions`, the first failure is raised at once and the
remaining sources are not started.

**Jobs.** `submit` returns at once with an `SEDJob` handle:

```python
job = client.sed.submit(ra, dec, name="PKS 2155-304")
job.id, job.status          # queued | running | done | no_data | failed
job.progress                # SEDProgress(stage="phase2", done=17, total=59, elapsed_s=8.9)
job.refresh()               # one request: new status and only the new events
job.events                  # every event so far; event.render() gives the log line
sed = job.result(timeout=300)

# Later, from the id alone
client.sed.job(job.id)      # status and all events
client.sed.fetch(job.id)    # the SED, waiting if the job still runs
client.sed.csv(job.id, "out.csv")   # the server's CSV
```

**Errors.** `get`, `fetch` and `result` raise `SEDNoData` when the pipeline
found nothing (the empty SED, with its source, is on `.sed`), `SEDJobFailed`
with a stable `.code` (`pipeline`, `timeout`, `abandoned`, `enqueue`,
`internal`, `empty_refresh`) and `.retry_after_s`, and `SEDTimeoutError` with
the job `.id` when `timeout` (default 900 s) runs out (retries of a busy
server never run past it); the job keeps running
and `client.sed.fetch(id)` collects it later.

### SED Data Preparation (older API)

The methods below use the older endpoints and keep working unchanged.

SED preparation fetches multi-wavelength observational data from external catalogs for a given sky position.

```python
job = client.sed.prepare_and_wait(
    ra=187.28,              # Right Ascension in degrees
    dec=2.05,               # Declination in degrees
    database_name="3C273",  # Database identifier
    source_name="3C 273",   # Optional display name
)
print(job.status)  # "done", "no_data", or "error"
print(job.uuid)    # Use this UUID for all subsequent data retrieval
```

An `error` status is returned, not raised; pass `raise_on_error=True` to get
`SEDJobFailed` instead. A timeout raises `PollingTimeoutError` with the job's `uuid`.

If data already exists for a sky position, MMDC returns the cached result. Use `force=True` to re-fetch:

```python
job = client.sed.prepare_and_wait(ra=187.28, dec=2.05, database_name="3C273", force=True)
```

### Retrieving SED Data

Once a job is complete, retrieve the frequency/flux data:

```python
data = client.sed.get_data(job.uuid)

# data.uuid, data.ra, data.dec, data.source_name
# data.data — nested dict of frequency ranges, catalogs, and flux measurements
```

Filter by time range, catalogs, or convert units:

```python
data = client.sed.get_data(
    job.uuid,
    mjd_start=50000.0,                      # Filter by MJD time range
    mjd_end=60000.0,
    exclude_catalogs=["WISE", "2MASS"],      # Exclude specific catalogs
    exclude_freq_ranges=["radio"],           # Exclude frequency ranges
    x_axis="freq_ev",                        # Convert frequency to eV
    y_axis="flux_ev",                        # Convert flux to eV/cm²/s
)
```

**Available axis conversions:**

| `x_axis` | Description |
|---|---|
| `"freq_ev"` | Hz to eV |

| `y_axis` | Description |
|---|---|
| `"flux_ev"` | erg/cm²/s to eV/cm²/s |
| `"flux_norm"` | Normalized eV/cm²/s |
| `"flux_jyhz"` | Jy·Hz |
| `"flux_wm2"` | W/m² |
| `"nufnu_fnu_jy"` | Fν in Jy |

### Source Metadata

```python
info = client.sed.get_info(job.uuid)
print(info.source_name)   # "3C 273"
print(info.ra, info.dec)  # Coordinates
print(info.redshift)      # Redshift (float or None)
print(info.gal_lat)       # Galactic latitude
print(info.gal_long)      # Galactic longitude
print(info.W_peak)        # Peak frequency indicator
```

### Download as CSV

```python
client.sed.download_csv(job.uuid, "sed_data.csv")

# With filters (same options as get_data)
client.sed.download_csv(
    job.uuid, "filtered.csv",
    mjd_start=55000.0,
    exclude_catalogs=["WISE"],
)
```

CSV columns: `frequency`, `flux`, `flux_err`, `MJD_start`, `MJD_end`, `flag`, `catalog`, `reference`

---

### Observations

Direct access to the unified observations catalog — 12.4M rows of multi-wavelength data spanning both per-frequency SED measurements and time-series lightcurves, distinguished by an `is_lightcurve` flag.

**Catalogs:** `MMDCGR` (Fermi γ-ray), `MMDCOUV` (Swift UVOT), `MMDCXRT` (Swift XRT), `MMDCNuX` (NuSTAR), `ASAS-SN`, `ZTF`, `PanSTARRS-LC`, `SMARTS`.

#### Filtered Query

```python
# SED rows only, X-ray catalog, latest 100 by mjd_mid
rows = client.observations.query(
    catalog="MMDCXRT",
    is_lightcurve=False,
    limit=100,
)
for r in rows:
    print(f"{r.catalog} obsid={r.obsid} freq={r.frequency:.2e} flux={r.flux:.2e}")

# ZTF R-band lightcurve within an MJD window
lc = client.observations.query(
    catalog="ZTF",
    is_lightcurve=True,
    filter_band="R",
    mjd_min=60000,
    mjd_max=60100,
    ordering="-mjd_mid",
)
```

#### Cone Search

HEALPix-indexed spatial search (5 arcsec default, server caps prefilter at 4096 pixels):

```python
# All observations within 10″ of 3C 273
near = client.observations.cone_search(
    ra=187.27791667,
    dec=2.05238889,
    radius_arcsec=10,
)

# Combine cone search with other filters
recent_lc = client.observations.cone_search(
    ra=187.27791667, dec=2.05238889, radius_arcsec=30,
    is_lightcurve=True,
    mjd_min=60000,
)
```

#### Available Filters (on both `query()` and `cone_search()`)

| Param | Type | Description |
|---|---|---|
| `catalog` | str | Catalog code (see list above) |
| `filter_band` | str | Photometric band (`R`, `V`, `G`, `W1`, …) |
| `is_lightcurve` | bool | `True`=LC only, `False`=SED only, omit=both |
| `is_upper_limit` | bool | Filter by upper-limit flag |
| `obsid` | str | Exact telescope observation ID |
| `mjd_min`, `mjd_max` | float | MJD range bounds |
| `ordering` | str | Sort key, `-` prefix for descending |
| `limit` | int | Cap returned rows |

#### Reading Results

Each `Observation` carries its own `is_lightcurve` flag so a mixed result can be split client-side:

```python
rows = client.observations.query(catalog="MMDCGR", limit=200)
lc  = [r for r in rows if r.is_lightcurve]
sed = [r for r in rows if not r.is_lightcurve]
```

SED rows carry `frequency`/`mjd_start`/`mjd_end`, LC rows carry `mjd_mid`/`filter_band`. The MMDC* catalogs auto-attach the Sahakyan et al. 2024 reference:

```python
row = client.observations.query(catalog="MMDCXRT", limit=1)[0]
if row.reference:
    print(row.reference.bibcode)  # "2024AJ....168..289S"
    print(row.reference.citation) # "Sahakyan N., et al., 2024, ..."
```

---

### Swift UVOT/XRT Analysis

`client.madam` runs the MADAM pipeline on Swift data for a sky position, on demand. Results are ingested into the observations catalog (`MMDCOUV` for UVOT, `MMDCXRT` / `MMDCXRT_ORBIT` for XRT), so anything already analysed at that position is answered from cache without a new run.

Ask for a time window (MJD) or a list of Swift obsids, never both:

```python
# Time-range mode
job = client.madam.analyze(
    ra=166.1138, dec=38.2088,
    mjd_start=58849.0, mjd_end=59031.0,
    source_name="Mkn 421",
)

# ObsID mode (also the way to reach pre-2008 Swift data)
job = client.madam.analyze(ra=133.703645, dec=20.108511, obsids=["00030901030"])

print(job.status)   # "done" or "no_data" — both are complete answers
print(job.count)    # rows matching the request
```

`job.results` is a list of `Observation` objects, the same shape as `client.observations` returns. Each measurement appears twice: as a lightcurve row (`is_lightcurve=True`, `mjd_mid`, `filter_band`) and as an SED row (`is_lightcurve=False`, `frequency`, `mjd_start`/`mjd_end`).

```python
sed = [r for r in job.results if not r.is_lightcurve]
lc  = [r for r in job.results if r.is_lightcurve]
```

#### Instruments

| `instrument` | Runs | Catalogs |
|---|---|---|
| `"uvot"` (default) | UVOT photometry in `U`, `B`, `V`, `W1`, `M2`, `W2` | `MMDCOUV` |
| `"xrt"` | XRT spectroscopy, per observation and optionally per orbit | `MMDCXRT`, `MMDCXRT_ORBIT` |
| `"swift"` | both | all three |

```python
job = client.madam.analyze(
    ra=166.1138, dec=38.2088, obsids=["00030352001", "00030352002"],
    instrument="xrt",
    orbit=False,     # skip the per-orbit products; False is only accepted with instrument="xrt"
)
for obs in job.xrt_observations:   # one per obsid: both spectral fits plus its points
    pl, lp = obs.fits.powerlaw, obs.fits.logparabola
    print(obs.obsid, obs.preferred_model, obs.delta_stat, pl.index, lp.alpha, lp.beta)
    print(len(obs.points))         # the MMDCXRT / MMDCXRT_ORBIT rows of this obsid
```

`xrt_observations` is filled for `"xrt"` and `"swift"` requests. Both fits are always returned, each with its fit statistic (`stat`, `dof`, `null_prob`) so you can apply your own model choice. `delta_stat` is `powerlaw.stat - logparabola.stat`, and `preferred_model` is `"logparabola"` when it is at least 9 (the server default), otherwise `"powerlaw"` (or `None` if the two cannot be compared). A model that was not fitted is `None`, and so is `fits` for an obsid analysed before fits were recorded. `limit=` caps `results` but not `xrt_observations`. The flux errors come from a Monte Carlo and vary by about 30% between runs, so don't compare runs on them. The flat fit table is still available as `job.xrt_fits`.

X-ray runs are capped server-side at 60 obsids or a 365-day window per request, because XRT costs minutes per observation.

#### Coverage cache

The server remembers every completed request. A new request that lies inside an earlier one at the same position (5″) and with a covering instrument is answered immediately with `cached=True`, including the case where the earlier run found nothing. A `"swift"` run covers later `"uvot"` and `"xrt"` requests; the reverse is not true. Pass `force=True` to re-run regardless.

On a cache hit `analyze()` returns a job with `cached=True` whose request fields (`instrument`, `mjd_start`/`mjd_end`, `obsids`) and `results` are yours, while the run metadata (`created_at`, `rows_ingested`, `xrt_fits`, ...) comes from the covering run. Pass `limit=` to cap the rows either way.

Windows that reach up to today are handled sensibly: the last ~7 days are treated as not yet in the Swift archive, so a cached window still counts as covering them.

#### Timing

A run downloads Swift data and runs HEASoft, so it takes minutes to hours. `analyze()` polls once a minute, backing off to every two minutes, and gives up after four hours by default:

```python
job = client.madam.analyze(
    ra=166.1138, dec=38.2088, mjd_start=58849.0, mjd_end=59031.0,
    poll_interval=60.0,   # seconds between checks (keep >= 60)
    max_minutes=240.0,
)
```

If the pipeline fails, `analyze()` and `wait_for_completion()` raise `AnalysisJobError` carrying the tail of the container log in `.logs`. If the wait budget runs out, `PollingTimeoutError.uuid` identifies the job, which keeps running on the server and can be collected later with `client.madam.get(uuid)`.

---

### Blazar Emission Modeling

MMDC supports three blazar broadband emission models:

| Model | Description |
|---|---|
| `SSC` | Synchrotron Self-Compton |
| `EIC` | External Inverse Compton |
| `HADRONIC` | Hadronic emission model |

#### Input Data Format

All modeling endpoints expect a CSV file with three columns (case-sensitive, lowercase):

```csv
frequency,flux,flux_err
1.00e+09,2.50e-14,3.00e-15
4.85e+09,3.10e-14,2.80e-15
...
```

#### Validate CSV Before Submitting

```python
validation = client.modeling.validate_csv("observations.csv")

print(validation.success)          # True/False
print(validation.data_points)      # Number of valid rows
print(validation.columns)          # ["frequency", "flux", "flux_err"]
print(validation.frequency_range)  # [min, max]
print(validation.flux_range)       # [min, max]
```

#### SSC Model Fitting

```python
result = client.modeling.batch_infer(
    "observations.csv",
    z=0.158,            # Redshift (0 < z <= 10)
    ebl=True,           # EBL absorption correction
    model_type="SSC",
)

print(result.pdf_link)                   # URL to PDF report
print(result.csv_best_parameters_link)   # URL to best-fit parameters CSV
print(result.csv_best_model_link)        # URL to best-fit model CSV
print(result.best_parameters)            # Dict of parameter name -> {value, error}
```

#### Fixed Parameters

Fix specific model parameters instead of fitting them:

```python
result = client.modeling.batch_infer(
    "observations.csv",
    z=0.158,
    ebl=True,
    model_type="SSC",
    fixed_parameters={
        "log_B": -1.5,
        "lorentz_factor": 20.0,
    },
)
```

**SSC parameters:** `log_B`, `log_electron_luminosity`, `log_gamma_cut`, `log_gamma_min`, `log_radius`, `lorentz_factor`, `spectral_index`

**EIC parameters:** `log_B`, `log_Ld`, `log_MBH`, `log_electron_luminosity`, `log_gamma_cut`, `log_gamma_min`, `log_radius`, `lorentz_factor`, `spectral_index`, `log_nu_BLR`, `log_nu_DT`

**HADRONIC parameters:** `log_B`, `log_Le`, `log_gamma_e_cut`, `log_gamma_e_min`, `log_gamma_p_cut`, `log_Lp`, `log_R`, `lorentz_factor`, `pe`, `pp`

#### EIC Model Fitting

```python
result = client.modeling.batch_infer(
    "observations.csv",
    z=0.5,
    ebl=True,
    model_type="EIC",
    fixed_parameters={"log_nu_BLR": 15.0, "log_nu_DT": 13.5},
)
```

#### HADRONIC Model with Neutrino Parameters

Hadronic models require additional neutrino likelihood parameters. Choose either Poisson or chi-square likelihood:

**Poisson likelihood:**

```python
result = client.modeling.batch_infer(
    "observations.csv",
    z=1.0,
    ebl=True,
    model_type="HADRONIC",
    likelihood_type="poisson",
    n_icecube=3,       # Number of IceCube neutrino events
    dt=12.0,           # Observation period in months
)
```

**Chi-square likelihood:**

```python
result = client.modeling.batch_infer(
    "observations.csv",
    z=1.0,
    ebl=True,
    model_type="HADRONIC",
    likelihood_type="chi2",
    x1=100.0,          # First neutrino energy (TeV)
    x2=200.0,          # Second neutrino energy (TeV)
    y=-12.0,           # Neutrino flux log value
)
```

### Working with Results

```python
result = client.modeling.batch_infer(...)

# Best-fit parameters
for name, param in result.best_parameters.items():
    print(f"{name}: {param.value} +/- {param.error}")

# Fixed parameters
if result.fixed_parameters:
    for name, param in result.fixed_parameters.items():
        print(f"{name} (fixed): {param.value}")

# Download links
print(result.pdf_link)                   # PDF report with plots
print(result.csv_best_parameters_link)   # Best-fit parameters as CSV
print(result.csv_best_model_link)        # Best-fit model curve as CSV
```

Download result files:

```python
import httpx

if result.pdf_link:
    pdf = httpx.get(result.pdf_link)
    with open("report.pdf", "wb") as f:
        f.write(pdf.content)
```

### Error Handling

```python
from astro_mmdc import (
    MMDC,
    MMDCError,           # Base exception for all SDK errors
    APIError,            # Non-2xx HTTP response
    NotFoundError,       # 404 response
    ValidationError,     # 422 response (CSV/parameter validation)
    PollingTimeoutError, # Polling exceeded max wait time
    BatchJobError,       # Batch modeling job failed on the server
    AnalysisJobError,    # Swift/MADAM analysis job failed on the server
    SEDNoData,           # client.sed.get(): no points at this position
    SEDJobFailed,        # client.sed.get(): the SED job failed (.code, .retry_after_s)
    SEDTimeoutError,     # client.sed.get(): still running at the timeout (.id)
    SEDNotReady,         # client.sed.csv(): the job is still running (HTTP 409)
)

client = MMDC()

try:
    result = client.modeling.batch_infer("data.csv", z=0.5, ebl=True, model_type="SSC")
except ValidationError as e:
    print(f"CSV validation failed: {e} (type: {e.validation_type})")
except PollingTimeoutError:
    print("Job did not complete in time")
except NotFoundError:
    print("Resource not found")
except APIError as e:
    print(f"HTTP {e.status_code}: {e.detail}")
```

The SDK automatically retries on transient errors (429, 502, 503, 504) with exponential backoff (up to 3 attempts).

---

## Advanced

### Manual Job Control

SED preparation, batch modeling and Swift analysis are asynchronous — you submit a job, then poll for results. The convenience methods (`prepare_and_wait`, `batch_infer`, `analyze`) handle polling automatically, but you can manage each step yourself for more control.

This is useful when you want to submit multiple jobs at once and poll them independently, or do other work between submission and result retrieval.

#### SED: Manual Submit and Poll

```python
# Submit — returns immediately
job = client.sed.prepare(ra=187.28, dec=2.05, database_name="3C273")
print(job.uuid)

# Check status manually
status = client.sed.get_status(job.uuid)
print(status.status)  # "processing", "done", "no_data", or "error"

# Or block until complete with custom polling settings
completed = client.sed.wait_for_completion(
    job.uuid,
    poll_interval=5.0,   # Seconds between checks
    max_minutes=15.0,    # Give up after this
)
```

#### Modeling: Manual Submit and Poll

```python
# Submit — returns immediately with a batch_result_id
submission = client.modeling.submit_batch(
    "observations.csv",
    z=0.158,
    ebl=True,
    model_type="SSC",
)
print(submission.batch_result_id)

# Check result manually
result = client.modeling.get_batch_result(submission.batch_result_id)
if result.pdf_link:
    print("Job complete!")
else:
    print("Still processing...")

# Or block until complete with custom polling settings
result = client.modeling.wait_for_batch(
    submission.batch_result_id,
    poll_interval=10.0,
    max_minutes=15.0,
)
```

#### Swift Analysis: Manual Submit and Poll

```python
# Submit — returns immediately
submission = client.madam.submit(ra=166.1138, dec=38.2088, mjd_start=58849.0, mjd_end=59031.0)
if submission.cached:
    rows = submission.results        # already analysed, no run queued
else:
    print(submission.uuid, submission.status)   # "processing"

# Poll cheaply without the rows
status = client.madam.get(submission.uuid, include_results=False)
print(status.status)  # "processing", "done", "no_data", or "error"

# Or block until complete
job = client.madam.wait_for_completion(submission.uuid, poll_interval=60.0, max_minutes=240.0)

# Fetch rows later, optionally capped
job = client.madam.get(submission.uuid, limit=100)
```

Submitting the same request twice while it is still running returns the running job rather than queuing a second one.

#### Batch Processing Multiple Sources

```python
import time

sources = [
    {"ra": 187.28, "dec": 2.05, "name": "3C273"},
    {"ra": 166.11, "dec": 38.21, "name": "Mkn421"},
    {"ra": 253.47, "dec": 39.76, "name": "Mkn501"},
]

# Submit all jobs first
jobs = []
for src in sources:
    job = client.sed.prepare(ra=src["ra"], dec=src["dec"], database_name=src["name"])
    jobs.append(job)
    print(f"Submitted {src['name']}: {job.uuid}")

# Then wait for all of them
for job in jobs:
    completed = client.sed.wait_for_completion(job.uuid)
    print(f"{completed.source_name}: {completed.status}")
```

### Synchronous Inference

For quick model calculations without queuing — pass parameters directly and get the spectrum back instantly:

```python
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

# Access the model spectrum directly
print(result.nu)       # Frequency values
print(result.nuFnu)    # Flux values (nu * F_nu)
```

Works with all model types — SSC, EIC, and hadronic:

```python
# EIC inference
result = client.modeling.infer(
    z=0.5,
    ebl=True,
    model_type="EIC",
    parameters={
        "log_B": -1.0,
        "log_electron_luminosity": 44.0,
        "log_gamma_cut": 4.5,
        "log_gamma_min": 2.0,
        "log_radius": 16.5,
        "lorentz_factor": 15.0,
        "spectral_index": 2.0,
        "log_Ld": 45.0,
        "log_MBH": 8.5,
        "log_nu_BLR": 15.0,
        "log_nu_DT": 13.5,
    },
)
```

### BatchResult Object Reference

All fields available on a `BatchResult`:

```python
result.data                       # Model curve data points (dict)
result.best_parameters            # Best-fit parameters (dict of name -> {value, error})
result.fixed_parameters           # Fixed parameters (dict of name -> {value, error})
result.model_type                 # "SSC", "EIC", or "HADRONIC"
result.z                          # Redshift
result.pdf_link                   # URL to PDF report
result.csv_best_parameters_link   # URL to best-fit parameters CSV
result.csv_best_model_link        # URL to best-fit model curve CSV
result.uploaded_file              # Original input data (dict)
result.multinest_stats            # MultiNest sampling statistics (dict)
result.equal_weighted_posterior   # Posterior samples (dict)
```

---

## API Reference

### `client.sed`

| Method | Description |
|---|---|
| `get(ra, dec, name=None, ...)` | The SED at a position (waits for a new job) |
| `submit(ra, dec, name=None, ...)` | Create or reuse the job; returns an `SEDJob` |
| `get_many(sources, max_concurrency=2, ...)` | `get` for many positions |
| `source(ra, dec, ...)` | Source info only (redshift, synchrotron peak) |
| `job(id)` / `fetch(id, ...)` / `csv(id, dest=None, ...)` | A job, its SED, its CSV by id |
| `prepare(ra, dec, database_name, ...)` | Submit SED preparation job (older API) |
| `get_status(uuid)` | Check job status |
| `wait_for_completion(uuid, ...)` | Poll until job finishes |
| `prepare_and_wait(ra, dec, database_name, ...)` | Submit and wait |
| `get_data(uuid, ...)` | Get frequency/flux data |
| `get_info(uuid)` | Get source metadata |
| `download_csv(uuid, dest, ...)` | Download data as CSV file |

### `client.modeling`

| Method | Description |
|---|---|
| `validate_csv(file)` | Validate CSV before submission |
| `submit_batch(file, z, ebl, model_type, ...)` | Submit batch inference job |
| `get_batch_result(batch_result_id)` | Get current job result |
| `wait_for_batch(batch_result_id, ...)` | Poll until job completes |
| `batch_infer(file, z, ebl, model_type, ...)` | Submit and wait |
| `infer(z, ebl, model_type, parameters)` | Synchronous model inference |
| `csv_to_json(file)` | Convert CSV to JSON format |

### `client.observations`

| Method | Description |
|---|---|
| `query(catalog, filter_band, is_lightcurve, ...)` | Filtered query of the observations table |
| `cone_search(ra, dec, radius_arcsec, ...)` | HEALPix-indexed spatial search with optional filters |

### `client.madam`

| Method | Description |
|---|---|
| `submit(ra, dec, mjd_start=, mjd_end=, obsids=, instrument=, ...)` | Request a Swift analysis; cached answers come back with rows |
| `get(uuid, include_results=True, limit=None)` | Fetch a job, optionally without its rows |
| `wait_for_completion(uuid, poll_interval=60, max_minutes=240, limit=None)` | Poll until done / no_data; raises `AnalysisJobError` on error |
| `analyze(ra, dec, ..., limit=None, poll_interval=60, max_minutes=240)` | Submit and wait |

---

## Citing

If you use MMDC data, models or this SDK in your research, please cite the MMDC paper
(Sahakyan et al. 2024, AJ, 168, 289; [doi:10.3847/1538-3881/ad8231](https://doi.org/10.3847/1538-3881/ad8231)):

```bibtex
@article{Sahakyan_2024,
  title     = {Markarian Multiwavelength Data Center (MMDC): A Tool for Retrieving and Modeling Multitemporal, Multiwavelength, and Multimessenger Data from Blazar Observations},
  author    = {Sahakyan, N. and Vardanyan, V. and Giommi, P. and B{\'e}gu{\'e}, D. and Israyelyan, D. and Harutyunyan, G. and Manvelyan, M. and Khachatryan, M. and Dereli-B{\'e}gu{\'e}, H. and Gasparyan, S.},
  journal   = {The Astronomical Journal},
  publisher = {American Astronomical Society},
  volume    = {168},
  number    = {6},
  pages     = {289},
  year      = {2024},
  month     = nov,
  doi       = {10.3847/1538-3881/ad8231},
  eprint    = {2410.01207},
  archivePrefix = {arXiv}
}
```

Data retrieved through MMDC is licensed under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)
and requires attribution. Citation metadata for the SDK itself is in [`CITATION.cff`](https://github.com/icranet/astro-mmdc/blob/main/CITATION.cff).

---

## Links

- **MMDC Platform**: [mmdc.am](https://mmdc.am)
- **Data access guide (PDF)**: [mmdc.am/api/serve-pdf/data_access/](https://mmdc.am/api/serve-pdf/data_access/)
- **Paper**: Sahakyan et al. 2024, AJ, 168, 289, [doi:10.3847/1538-3881/ad8231](https://doi.org/10.3847/1538-3881/ad8231) ([arXiv:2410.01207](https://arxiv.org/abs/2410.01207)). Please cite it when you use MMDC data or models.
- **Source and issues**: [github.com/icranet/astro-mmdc](https://github.com/icranet/astro-mmdc)
- **Questions and bug reports**: [GitHub issues](https://github.com/icranet/astro-mmdc/issues) or the contact form at [mmdc.am/#contact](https://mmdc.am/#contact)

---

## License

BSD-3-Clause, see [LICENSE](https://github.com/icranet/astro-mmdc/blob/main/LICENSE).
