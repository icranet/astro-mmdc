# Swift UVOT/XRT analysis

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

## Instruments

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

## Coverage cache

The server remembers every completed request. A new request that lies inside an earlier one at the same position (5″) and with a covering instrument is answered immediately with `cached=True`, including the case where the earlier run found nothing. A `"swift"` run covers later `"uvot"` and `"xrt"` requests; the reverse is not true. Pass `force=True` to re-run regardless.

On a cache hit `analyze()` returns a job with `cached=True` whose request fields (`instrument`, `mjd_start`/`mjd_end`, `obsids`) and `results` are yours, while the run metadata (`created_at`, `rows_ingested`, `xrt_fits`, ...) comes from the covering run. Pass `limit=` to cap the rows either way.

Windows that reach up to today are handled sensibly: the last ~7 days are treated as not yet in the Swift archive, so a cached window still counts as covering them.

## Timing

A run downloads Swift data and runs HEASoft, so it takes minutes to hours. `analyze()` polls once a minute, backing off to every two minutes, and gives up after four hours by default:

```python
job = client.madam.analyze(
    ra=166.1138, dec=38.2088, mjd_start=58849.0, mjd_end=59031.0,
    poll_interval=60.0,   # seconds between checks (keep >= 60)
    max_minutes=240.0,
)
```

If the pipeline fails, `analyze()` and `wait_for_completion()` raise `AnalysisJobError` carrying the tail of the container log in `.logs`. If the wait budget runs out, `PollingTimeoutError.uuid` identifies the job, which keeps running on the server and can be collected later with `client.madam.get(uuid)`.
