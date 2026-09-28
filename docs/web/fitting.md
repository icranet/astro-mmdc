---
title: "Fitting a blazar SED on mmdc.am"
description: "Fit the SSC, EIC or lepto-hadronic model to your own blazar SED on mmdc.am with MultiNest; the data file format, the fit options, the emailed results and the corner plot."
---

# Fitting your SED

On [mmdc.am](https://mmdc.am/#theoreticalModeling) you can fit the SSC, EIC or hadronic model
([Blazar SED modeling](modeling.md)) to your own SED. The fit runs in the background with
[MultiNest](https://arxiv.org/abs/0809.3437) (Feroz et al. 2009), which gives the posterior
distribution of every parameter; the result is sent to you by email.

[Open Theoretical Modeling on mmdc.am :material-open-in-new:](https://mmdc.am/#theoreticalModeling){ .md-button .md-button--primary }

## In short

1. **Upload SED (CSV)** in the Data card and set the **Redshift z** (and **EBL absorption**).
2. Choose the model: **SSC**, **EIC** or **Hadronic**.
3. Press **Fit (email)…**, check the summary, fix any parameter you know, enter your email.
4. Press **Submit fit**. A fit takes 0.5–2 hours; the email links to the result.

## The data file

A comma-separated file with a header row and three columns:

| Column | Content | Unit |
|---|---|---|
| `frequency` | frequency | Hz |
| `flux` | νF(ν) | erg cm⁻² s⁻¹ |
| `flux_err` | error on νF(ν) | erg cm⁻² s⁻¹ |

```csv
frequency,flux,flux_err
1.4000e+09,2.5100e-14,3.0000e-15
4.5300e+14,1.1200e-11,5.6000e-13
2.4200e+17,3.8000e-12,4.1000e-13
2.4200e+23,2.0400e-11,3.9000e-12
```

The column names must be exactly these, in lowercase; the file name must end in `.csv`. Once
uploaded, the data appear on the plot and the Data card shows the number of points and the
frequency range.

Before a fit starts, the file is checked:

- Rows with an empty or zero `flux_err` are dropped.
- **Only the data above 10¹¹ Hz are fitted**: fitting lower frequencies makes the model
  converge very slowly. The points below are still drawn.
- The SED should be from one period (quasi-simultaneous data). A file whose fluxes at similar
  frequencies differ by more than a factor of 3 in several places is refused as too variable;
  remove the outliers, or use averaged or binned data.

## Start a fit

With data uploaded, the redshift set and a model chosen, press **Fit (email)…**.

[![The fit dialog for the SSC model](img/tm-fit.webp#only-light)](img/tm-fit.webp)
[![The fit dialog for the SSC model](img/tm-fit-dark.webp#only-dark)](img/tm-fit-dark.webp)

The dialog sums up what will be fitted (the file, the number of points and their frequency
range, z, EBL and the model) and asks for:

- **Source** (optional): names the result. Pick a source from the list to also record its
  coordinates.
- **Parameters**: the fit explores every free parameter over its whole range, so the values
  in the Model panel are not used. Tick **Fix** for a parameter you know to hold it at a value.
  The parameters that can be fixed are log γ<sub>min</sub> (all models) and, for EIC, log
  L<sub>d</sub> and log M<sub>BH</sub>.
- **Email**: where the result is sent.

### Hadronic fits: the neutrino likelihood

For the hadronic model the fit can also use neutrino information. Choose one:

| Option | You give | What the fit compares |
|---|---|---|
| **Spectral information (χ²)** | E₁ and E₂ [TeV], the band's edges; log flux, the neutrino flux [erg cm⁻² s⁻¹] | The model's neutrino flux at E₁ and E₂ with the given flux (10 % error assumed) |
| **Number of neutrinos (Poisson)** | N, the number of neutrinos; Δt, the observation time [months] | N with the number the model predicts over Δt |

[![The fit dialog for the hadronic model](img/tm-fit-hadronic.webp#only-light)](img/tm-fit-hadronic.webp)
[![The fit dialog for the hadronic model](img/tm-fit-hadronic-dark.webp#only-dark)](img/tm-fit-hadronic-dark.webp)

## The result

You receive an email when the fit starts and another when it is ready. The second one has a
**View Results** link that opens the fit on mmdc.am, with:

- the plot of your data, the **best fit** and the posterior samples;
- the **best-fit parameters**, each with its 1σ error (or "fixed"), also loaded into the Model
  panel so you can run the model from them;
- three downloads: **Corner plot** (the posterior distributions, PDF), **Parameters** (the
  best-fit parameters, CSV) and **Model** (the best-fit SED, CSV).

If you already have several fits queued or running, a new one is refused until one of them
finishes.

## Your data

Uploaded data are used only to perform the fit you asked for. The data and the results are
kept for at least one week so you can open and download the results, then deleted
automatically (within 15 days).

## Need more?

To fit many SEDs, set constraints such as linked parameters, or get more advanced data
products, write to us:

- Damien Bégué: begueda@biu.ac.il
- Narek Sahakyan: narek.sahakyan@icranet.org
- MMDC: mailtommdc@gmail.com

To fit from Python, including many SEDs at once, see the SDK guide
[Blazar emission modeling](../guides/modeling.md).
