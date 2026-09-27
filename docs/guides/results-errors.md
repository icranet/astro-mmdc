# Results & errors

## Working with Results

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

## Error Handling

```python
from astro_mmdc import (
    MMDC,
    MMDCError,           # Base exception for all SDK errors
    APIError,            # Non-2xx HTTP response
    NotFoundError,       # 404 response
    RateLimitError,      # 429 response after retries (.retry_after)
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
