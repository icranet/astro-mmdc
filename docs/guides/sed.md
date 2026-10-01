# SED data

## Getting an SED

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
sed.undated                # True for undated catalogue values (mjd_start = mjd_end = 50000)
sed.catalog                # catalogue name of every point
sed.rows()                 # one dict per point
sed.table                  # pandas DataFrame (needs pandas)
```

Filter, convert, save and plot on the client:

```python
recent = sed.between(58000, 58400)            # MJD overlap; undated points dropped unless undated=True
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

**Undated points.** Catalogue values without an observation epoch have
`mjd_start` = `mjd_end` = 50000 (never `None`/NaN) and `undated` True; the
DataFrame from `sed.table` has an `undated` column too. They belong to no time
window: when `mjd_start` or `mjd_end` is given they are dropped, otherwise kept.
Pass `undated=True` to keep them with a window, or `undated=False` to drop them
without one; `between()`, `get()`, `fetch()` and `csv()` all take it.

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

## Older API

!!! note "Legacy"
    The methods below use the older endpoints and keep working unchanged. New code should use [`client.sed.get()`](#getting-an-sed) and the jobs described above.

### Preparation

SED preparation fetches multi-wavelength observational data from external catalogs for a given sky position.

```python
job = client.sed.prepare_and_wait(
    ra=187.2779,            # Right Ascension in degrees
    dec=2.0524,             # Declination in degrees
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
job = client.sed.prepare_and_wait(ra=187.2779, dec=2.0524, database_name="3C273", force=True)
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
