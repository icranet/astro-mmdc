---
title: "MMDC documentation"
description: "Documentation of the Markarian Multiwavelength Data Center (MMDC, mmdc.am): multiwavelength SEDs of blazars, SSC, EIC and hadronic emission modeling and fitting, on the website and with the astro-mmdc Python SDK."
---

# MMDC documentation

The [Markarian Multiwavelength Data Center (MMDC)](https://mmdc.am) retrieves multiwavelength,
multitemporal data of blazars and any sky position from radio to gamma rays, and models their
broadband emission. It can be used in the browser at **[mmdc.am](https://mmdc.am)** or from
Python with the `astro-mmdc` SDK.

[Open MMDC :material-open-in-new:](https://mmdc.am){ .md-button .md-button--primary }
[Install the SDK](getting-started.md){ .md-button }

## Using the website

- [Getting SED data](web/sed-data.md): build the SED of a source, filter it in time, explore it,
  download it as CSV.
- [Blazar SED modeling](web/modeling.md): the SSC, EIC and hadronic models and every parameter.
- [Fitting your SED](web/fitting.md): fit a model to your own data and read the result.

## Python SDK

```bash
pip install astro-mmdc
```

```python
from astro_mmdc import MMDC

client = MMDC()
sed = client.sed.get(ra=187.2779, dec=2.0524, name="3C 273")
print(sed.source.redshift, sed.points)
```

- [Getting started](getting-started.md): installation, creating a client, quick start.
- [Scripts and AI agents](agents.md): rules and recipes for code that calls MMDC without a person at the browser, including raw HTTP.
- Guides:
    - [SED data](guides/sed.md): the SED of any sky position.
    - [Observations](guides/observations.md): the unified observations catalog (SED + lightcurve).
    - [Swift UVOT/XRT analysis](guides/swift.md): on-demand Swift analysis with the MADAM pipeline.
    - [Blazar emission modeling](guides/modeling.md): SSC, EIC and hadronic model fits.
    - [Results & errors](guides/results-errors.md): working with fit results and handling errors.
    - [Advanced](guides/advanced.md): manual job control, synchronous inference, the `BatchResult` reference.
- [API reference](api.md): every method of the four resource namespaces.

## Links

- **MMDC**: [mmdc.am](https://mmdc.am)
- **Paper**: Sahakyan et al. 2024, AJ, 168, 289, [doi:10.3847/1538-3881/ad8231](https://doi.org/10.3847/1538-3881/ad8231) ([arXiv:2410.01207](https://arxiv.org/abs/2410.01207)). Please cite it when you use MMDC data or models; see [Citing](citing.md).
- **SDK source and issues**: [github.com/icranet/astro-mmdc](https://github.com/icranet/astro-mmdc)
- **Questions and bug reports**: [GitHub issues](https://github.com/icranet/astro-mmdc/issues) or the contact form at [mmdc.am/#contact](https://mmdc.am/#contact)

## License

The SDK is BSD-3-Clause, see [LICENSE](https://github.com/icranet/astro-mmdc/blob/main/LICENSE).
MMDC data are available under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
