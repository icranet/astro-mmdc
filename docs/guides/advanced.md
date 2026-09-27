# Advanced

## Manual Job Control

SED preparation, batch modeling and Swift analysis are asynchronous — you submit a job, then poll for results. The convenience methods (`prepare_and_wait`, `batch_infer`, `analyze`) handle polling automatically, but you can manage each step yourself for more control.

This is useful when you want to submit multiple jobs at once and poll them independently, or do other work between submission and result retrieval.

### SED: Manual Submit and Poll

```python
# Submit — returns immediately
job = client.sed.prepare(ra=187.2779, dec=2.0524, database_name="3C273")
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

### Modeling: Manual Submit and Poll

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

### Swift Analysis: Manual Submit and Poll

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

### Batch Processing Multiple Sources

```python
import time

sources = [
    {"ra": 187.2779, "dec": 2.0524, "name": "3C273"},
    {"ra": 166.1138, "dec": 38.2088, "name": "Mkn421"},
    {"ra": 253.4676, "dec": 39.7602, "name": "Mkn501"},
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

## Synchronous Inference

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

## BatchResult Object Reference

All fields available on a `BatchResult`:

```python
result.status                     # Job status reported by the server (str or None)
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
result.equal_weighted_posterior   # Posterior samples (list of rows)
```

`result.plot("fit.png")` draws the posterior model curves and the best-fit model with your fitted data points overlaid, and returns the path it wrote. It needs the plotting extra (`pip install "astro-mmdc[plot]"`).
