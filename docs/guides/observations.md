# Observations

Direct access to the unified observations catalog — 12.4M rows of multi-wavelength data spanning both per-frequency SED measurements and time-series lightcurves, distinguished by an `is_lightcurve` flag.

**Catalogs:** `MMDCGR` (Fermi γ-ray), `MMDCOUV` (Swift UVOT), `MMDCXRT` (Swift XRT), `MMDCXRT_ORBIT` (Swift XRT, per orbit), `MMDCNuX` (NuSTAR), `ASAS-SN`, `ZTF`, `PanSTARRS-LC`, `SMARTS`.

## Filtered Query

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

## Cone Search

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

## Available Filters (on both `query()` and `cone_search()`)

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

## Reading Results

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
