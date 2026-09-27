# astro-mmdc

Python SDK for the [MMDC astrophysics platform](https://mmdc.am): multi-wavelength SED data, on-demand Swift UVOT/XRT analysis and blazar broadband emission modeling.

[![PyPI](https://img.shields.io/pypi/v/astro-mmdc)](https://pypi.org/project/astro-mmdc/)
[![Python versions](https://img.shields.io/pypi/pyversions/astro-mmdc)](https://pypi.org/project/astro-mmdc/)
[![License](https://img.shields.io/badge/license-BSD--3--Clause-blue)](https://github.com/icranet/astro-mmdc/blob/main/LICENSE)
[![Tests](https://github.com/icranet/astro-mmdc/actions/workflows/tests.yml/badge.svg)](https://github.com/icranet/astro-mmdc/actions/workflows/tests.yml)
[![Docs](https://img.shields.io/badge/docs-docs.mmdc.am-blue)](https://docs.mmdc.am)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.22999175.svg)](https://doi.org/10.5281/zenodo.22999175)

The [Markarian Multiwavelength Data Center (MMDC)](https://mmdc.am) gathers multi-wavelength, multi-epoch observations of blazars and other sources from dozens of catalogues and archives. It also models their broadband emission with SSC, EIC and hadronic models, and this SDK gives Python access to all of it.

## Installation

```bash
pip install astro-mmdc
```

Or with [uv](https://docs.astral.sh/uv/):

```bash
uv pip install astro-mmdc
```

Requires Python 3.10+. Plotting needs the extra: `pip install "astro-mmdc[plot]"`.

## Quick start

```python
from astro_mmdc import MMDC

client = MMDC()

# The SED of 3C 273: source info plus every point
sed = client.sed.get(ra=187.2779, dec=2.0524, name="3C 273")
print(sed.source.redshift, sed.points)
sed.to_csv("3c273.csv")

# A synchronous SSC model spectrum
result = client.modeling.infer(
    z=0.158, ebl=True, model_type="SSC",
    parameters={"log_B": -1.5, "log_electron_luminosity": 44.0,
                "log_gamma_cut": 5.0, "log_gamma_min": 2.0,
                "log_radius": 16.0, "lorentz_factor": 20.0,
                "spectral_index": 2.2},
)
print(result.nu, result.nuFnu)
```

The [Getting started](https://docs.mmdc.am/getting-started/) page has more examples, including a full SED-to-fit pipeline.

## What you can do

- **SED data**: the SED at any sky position, with filters, unit conversion, CSV export and plots. See the [SED data guide](https://docs.mmdc.am/guides/sed/).
- **Observations and light curves**: filtered queries and cone searches over the unified observations catalogue (Fermi, Swift, NuSTAR, ZTF, ASAS-SN, ...). See the [observations guide](https://docs.mmdc.am/guides/observations/).
- **Swift UVOT/XRT analysis**: on-demand photometry and XRT spectral fits through the MADAM pipeline, with a coverage cache. See the [Swift guide](https://docs.mmdc.am/guides/swift/).
- **Blazar emission modeling**: SSC, EIC and hadronic model fits and synchronous inference. See the [modeling guide](https://docs.mmdc.am/guides/modeling/).
- **Async jobs**: submit SED, modeling and Swift jobs, then poll them yourself. See [Advanced](https://docs.mmdc.am/guides/advanced/).

## Links

- Documentation: [docs.mmdc.am](https://docs.mmdc.am)
- MMDC platform: [mmdc.am](https://mmdc.am)
- Paper: Sahakyan et al. 2024, AJ, 168, 289, [doi:10.3847/1538-3881/ad8231](https://doi.org/10.3847/1538-3881/ad8231)
- Software DOI (Zenodo): [doi:10.5281/zenodo.22999175](https://doi.org/10.5281/zenodo.22999175)
- Issues: [github.com/icranet/astro-mmdc/issues](https://github.com/icranet/astro-mmdc/issues)

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
and requires attribution. The SDK itself is archived on Zenodo, [doi:10.5281/zenodo.22999175](https://doi.org/10.5281/zenodo.22999175) (all versions); its citation metadata is in [`CITATION.cff`](https://github.com/icranet/astro-mmdc/blob/main/CITATION.cff).

## License

BSD-3-Clause, see [LICENSE](https://github.com/icranet/astro-mmdc/blob/main/LICENSE).
