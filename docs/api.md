# API reference

Every public method of the four resource namespaces on an `MMDC` client. The [guides](guides/sed.md) show them in use, and [Advanced](guides/advanced.md#batchresult-object-reference) lists the fields of a `BatchResult`.

## `client.sed`

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

## `client.modeling`

| Method | Description |
|---|---|
| `validate_csv(file)` | Validate CSV before submission |
| `submit_batch(file, z, ebl, model_type, ...)` | Submit batch inference job |
| `get_batch_result(batch_result_id)` | Get current job result |
| `wait_for_batch(batch_result_id, ...)` | Poll until job completes |
| `batch_infer(file, z, ebl, model_type, ...)` | Submit and wait |
| `infer(z, ebl, model_type, parameters)` | Synchronous model inference |
| `csv_to_json(file)` | Convert CSV to JSON format |

## `client.observations`

| Method | Description |
|---|---|
| `query(catalog, filter_band, is_lightcurve, ...)` | Filtered query of the observations table |
| `cone_search(ra, dec, radius_arcsec, ...)` | HEALPix-indexed spatial search with optional filters |

## `client.madam`

| Method | Description |
|---|---|
| `submit(ra, dec, mjd_start=, mjd_end=, obsids=, instrument=, ...)` | Request a Swift analysis; cached answers come back with rows |
| `get(uuid, include_results=True, limit=None)` | Fetch a job, optionally without its rows |
| `wait_for_completion(uuid, poll_interval=60, max_minutes=240, limit=None)` | Poll until done / no_data; raises `AnalysisJobError` on error |
| `analyze(ra, dec, ..., limit=None, poll_interval=60, max_minutes=240)` | Submit and wait |
