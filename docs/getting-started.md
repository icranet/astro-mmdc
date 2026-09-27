# Getting started

## Installation

```bash
pip install astro-mmdc
```

Or with [uv](https://docs.astral.sh/uv/):

```bash
uv pip install astro-mmdc
```

Requires Python 3.10+.

Plotting (`SED.plot()`, `BatchResult.plot()`) and `SED.table` need the `plot` extra, which adds matplotlib and pandas:

```bash
pip install "astro-mmdc[plot]"
```

## Creating a client

```python
from astro_mmdc import MMDC

client = MMDC()

# Custom request timeout (seconds)
client = MMDC(timeout=60.0)

# As a context manager (auto-closes HTTP connection)
with MMDC() as client:
    ...
```

### Identifying your application and users

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

- `client.sed`: multi-wavelength SED of any sky position ([guide](guides/sed.md))
- `client.modeling`: blazar emission modeling, SSC, EIC and hadronic ([guide](guides/modeling.md))
- `client.observations`: unified observations catalog, SED + lightcurve ([guide](guides/observations.md))
- `client.madam`: on-demand Swift UVOT/XRT analysis, MADAM pipeline ([guide](guides/swift.md))

## Quick start

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

End-to-end pipeline, from sky coordinates to model fit:

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
