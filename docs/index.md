# astro-mmdc

Python SDK for the [MMDC astrophysics platform](https://mmdc.am): programmatic access to multi-wavelength SED data, on-demand Swift UVOT/XRT analysis and blazar broadband emission modeling.

MMDC provides APIs for querying astrophysical databases, preparing Spectral Energy Distribution (SED) data from multiple catalogs, running Swift photometry on demand, and running physics simulations for blazar emission modeling using SSC, EIC, and hadronic models.

```bash
pip install astro-mmdc
```

```python
from astro_mmdc import MMDC

client = MMDC()
sed = client.sed.get(ra=187.28, dec=2.05, name="3C 273")
print(sed.source.redshift, sed.points)
```

## Where to go next

- [Getting started](getting-started.md): installation, creating a client, quick start.
- Guides:
    - [SED data](guides/sed.md): the SED of any sky position.
    - [Observations](guides/observations.md): the unified observations catalog (SED + lightcurve).
    - [Swift UVOT/XRT analysis](guides/swift.md): on-demand Swift analysis with the MADAM pipeline.
    - [Blazar emission modeling](guides/modeling.md): SSC, EIC and hadronic model fits.
    - [Results & errors](guides/results-errors.md): working with fit results and handling errors.
    - [Advanced](guides/advanced.md): manual job control, synchronous inference, the `BatchResult` reference.
- [API reference](api.md): every method of the four resource namespaces.
- [Citing](citing.md): how to cite MMDC and this SDK.

## Links

- **MMDC Platform**: [mmdc.am](https://mmdc.am)
- **Data access guide (PDF)**: [mmdc.am/api/serve-pdf/data_access/](https://mmdc.am/api/serve-pdf/data_access/)
- **Paper**: Sahakyan et al. 2024, AJ, 168, 289, [doi:10.3847/1538-3881/ad8231](https://doi.org/10.3847/1538-3881/ad8231) ([arXiv:2410.01207](https://arxiv.org/abs/2410.01207)). Please cite it when you use MMDC data or models.
- **Source and issues**: [github.com/icranet/astro-mmdc](https://github.com/icranet/astro-mmdc)
- **Questions and bug reports**: [GitHub issues](https://github.com/icranet/astro-mmdc/issues) or the contact form at [mmdc.am/#contact](https://mmdc.am/#contact)

## License

BSD-3-Clause, see [LICENSE](https://github.com/icranet/astro-mmdc/blob/main/LICENSE).
