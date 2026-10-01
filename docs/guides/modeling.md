# Blazar emission modeling

MMDC supports three blazar broadband emission models:

| Model | Description | Typical fit time |
|---|---|---|
| `SSC` | Synchrotron Self-Compton | 10–15 s |
| `EIC` | External Inverse Compton | about 1 min |
| `HADRONIC` | Hadronic emission model | about 2 min |

Fit times are the run on the server, without any wait in the queue. `batch_infer` and
`wait_for_batch` return about a second after the fit ends.

## Input Data Format

All modeling endpoints need a CSV file with `frequency`, `flux` and `flux_err` columns (case-sensitive, lowercase):

```csv
frequency,flux,flux_err
1.00e+09,2.50e-14,3.00e-15
4.85e+09,3.10e-14,2.80e-15
...
```

Columns may come in any order and other columns are ignored. Upper limits
(`is_ul` true, or `flag` UL) and rows without a positive `flux_err` are dropped.

An SED from `client.sed` can be fitted directly: its CSV (`freq_hz`, `nufnu`,
`nufnu_err`, `is_ul`, …) is accepted as well. Keep one period, or the file is
refused as too variable:

```python
sed = client.sed.get(ra=166.113808, dec=38.208833, name="Mrk 421")
sed.between(59000, 59030).to_csv("mrk421.csv")
result = client.modeling.batch_infer("mrk421.csv", z=0.031, ebl=True, model_type="SSC")
```

## Validate CSV Before Submitting

```python
validation = client.modeling.validate_csv("observations.csv")

print(validation.success)          # True/False
print(validation.data_points)      # Number of valid rows
print(validation.columns)          # ["frequency", "flux", "flux_err"]
print(validation.frequency_range)  # [min, max]
print(validation.flux_range)       # [min, max]
```

## SSC Model Fitting

```python
result = client.modeling.batch_infer(
    "observations.csv",
    z=0.158,            # Redshift (0 < z <= 4.99)
    ebl=True,           # EBL absorption correction
    model_type="SSC",
)

print(result.pdf_link)                   # URL to PDF report
print(result.csv_best_parameters_link)   # URL to best-fit parameters CSV
print(result.csv_best_model_link)        # URL to best-fit model CSV
print(result.best_parameters)            # Dict of parameter name -> {value, error}
```

## Fixed Parameters

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

## EIC Model Fitting

```python
result = client.modeling.batch_infer(
    "observations.csv",
    z=0.5,
    ebl=True,
    model_type="EIC",
    fixed_parameters={"log_nu_BLR": 15.0, "log_nu_DT": 13.5},
)
```

## HADRONIC Model with Neutrino Parameters

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
