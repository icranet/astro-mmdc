---
title: "Blazar SED modeling on mmdc.am (SSC, EIC, hadronic)"
description: "Compute the broadband SED of a blazar on mmdc.am with the synchrotron self-Compton (SSC), external inverse Compton (EIC) or lepto-hadronic model; every parameter, its range and meaning."
---

# Blazar SED modeling

The **Theoretical Modeling** section of [mmdc.am](https://mmdc.am/#theoreticalModeling)
computes the broadband SED of a blazar for the parameters you give, within seconds, and
fits the models to your own data ([Fitting your SED](fitting.md)).

[Open Theoretical Modeling on mmdc.am :material-open-in-new:](https://mmdc.am/#theoreticalModeling){ .md-button .md-button--primary }

[![The modeling section with an SSC model](img/tm-ssc.webp#only-light)](img/tm-ssc.webp)
[![The modeling section with an SSC model](img/tm-ssc-dark.webp#only-dark)](img/tm-ssc-dark.webp)

*An SSC model. The panel on the right holds the Data card, the model tabs and the parameters.*

## In short

1. Set the **Redshift z** in the Data card, and tick **EBL absorption** if you want it.
2. Choose **SSC**, **EIC** or **Hadronic**.
3. Enter the parameters, or use **Run model ▾ → Load example** for a tested set
   (**Load example (Mrk 421)** for SSC).
4. Press **Run model**. The SED appears on the plot.

A value outside its range is shown in red with the allowed range; the range of every field is
also shown inside it.

## The models

The SSC and EIC models are convolutional neural networks (CNNs) trained on the physical models of
[Bégué, Sahakyan, Dereli Bégué, et al. 2024, ApJ, 963, 71](https://ui.adsabs.harvard.edu/abs/2024ApJ...963...71B/abstract)
(SSC) and
[Sahakyan, Bégué, Casotto, et al. 2024, ApJ, 971, 70](https://ui.adsabs.harvard.edu/abs/2024ApJ...971...70S/abstract)
(EIC). They are trained on a leptonic framework that includes synchrotron and inverse Compton
emission (from internal and external photon fields), with self-consistent electron cooling
and pair creation–annihilation. The physical models and their parameters are described in
detail in those two papers. The hadronic model is likewise a neural-network surrogate of its
physical model. The trained networks are used with
[MultiNest](https://arxiv.org/abs/0809.3437) (Feroz et al. 2009) to fit your data.

| Model | What it describes |
|---|---|
| **SSC**, synchrotron self-Compton | Electrons in one spherical blob emit synchrotron photons and up-scatter them by inverse Compton. |
| **EIC**, external inverse Compton | As SSC, and the electrons also up-scatter photons from the broad-line region (BLR) and the dusty torus (DT). The SED also includes the thermal emission of the disk, the BLR and the torus. |
| **Hadronic**, lepto-hadronic | Protons in the blob add the emission of their interactions, and neutrinos, to the electrons' synchrotron and SSC emission. |

The hadronic model also predicts the neutrino flux, drawn as a dashed curve.

## Redshift, distance and EBL

- **Redshift z** (0 < z ≤ 4.99) is required for every run and fit. It is converted to a distance
  with a flat cosmology, H₀ = 71 km s⁻¹ Mpc⁻¹ and Ω<sub>m</sub> = 0.27 (Ned Wright's Cosmology
  Calculator).
- **EBL absorption**, when ticked, attenuates the γ-ray emission by the extragalactic background
  light with model C of
  [Finke, Razzaque & Dermer 2010, ApJ, 712, 238](https://ui.adsabs.harvard.edu/abs/2010ApJ...712..238F/abstract).
  The optical depths are tabulated every 0.01 in z up to z = 4.99, which is why z is limited
  to 4.99; z is rounded to the nearest table.

## Parameters

All logarithms are base 10. The ranges are those the form accepts for a run; a fit samples
slightly different ranges (see [Fitting your SED](fitting.md#the-priors)).

### SSC

| Parameter | Meaning | Range |
|---|---|---|
| δ | Doppler factor of the emitting region | 3 – 50 |
| log R | comoving radius of the blob [cm] | 15 – 18 |
| log B | comoving magnetic field [G] | −3 – 2 |
| p | power-law index of the electrons | 1.8 – 5 |
| log γ<sub>min</sub> | minimum Lorentz factor of the electrons | 1.5 – 5 |
| log γ<sub>max</sub> | cut-off Lorentz factor of the electrons | 2 – 8 |
| log L<sub>e</sub> | electron luminosity [erg s⁻¹] | 42 – 48 |

### EIC

The SSC parameters (with slightly different ranges), plus the external photon fields.

[![EIC parameters](img/tm-eic.webp#only-light)](img/tm-eic.webp)
[![EIC parameters](img/tm-eic-dark.webp#only-dark)](img/tm-eic-dark.webp)

| Parameter | Meaning | Range |
|---|---|---|
| δ | Doppler factor | 3 – 50 |
| log R | comoving blob radius [cm] | 15 – 18 |
| log B | comoving magnetic field [G] | −3 – 2.5 |
| p | power-law index of the electrons | 1.8 – 5 |
| log γ<sub>min</sub> | minimum Lorentz factor | 1.5 – 5 |
| log γ<sub>max</sub> | cut-off Lorentz factor | 2 – 6 |
| log L<sub>e</sub> | electron luminosity [erg s⁻¹] | 42 – 48 |
| log L<sub>d</sub> | accretion disk luminosity [erg s⁻¹] | 43.5 – 47 |
| log M<sub>BH</sub> | mass of the central black hole [M<sub>⊙</sub>] | 7 – 10 |
| log ν<sub>BLR</sub> | frequency of the BLR photons [Hz] | fixed at 15.393 (ν = 2.47 × 10¹⁵ Hz) |
| log ν<sub>DT</sub> | frequency of the dusty torus photons [Hz] | fixed at 13.477 (ν = 3.0 × 10¹³ Hz) |

ν<sub>BLR</sub> and ν<sub>DT</sub> are fixed in the model: the values in their fields are not
used, in a run or in a fit (the fields must still hold a value in their range, 14.5–16 and
12.5–14).

### Hadronic

[![Hadronic parameters](img/tm-hadronic.webp#only-light)](img/tm-hadronic.webp)
[![Hadronic parameters](img/tm-hadronic-dark.webp#only-dark)](img/tm-hadronic-dark.webp)

| Parameter | Meaning | Range |
|---|---|---|
| δ | Doppler factor | 3.5 – 80 |
| log R | comoving blob radius [cm] | 14.5 – 18 |
| log B | comoving magnetic field [G] | −3 – 3.5 |
| p<sub>e</sub> | power-law index of the electrons | 1.75 – 5 |
| log γ<sub>min</sub> | minimum Lorentz factor of the electrons | 1.5 – 2 |
| log γ<sub>e,max</sub> | cut-off Lorentz factor of the electrons | 2 – 8 |
| log L<sub>e</sub> | electron luminosity [erg s⁻¹] | 42.5 – 48.5 |
| p<sub>p</sub> | power-law index of the protons | 1.65 – 3.45 |
| log γ<sub>p,max</sub> | cut-off Lorentz factor of the protons | 3 – 11 |
| log L<sub>p</sub> | proton luminosity [erg s⁻¹] | 42 – 52 |

## Compare with data

Upload an SED in the Data card (**Upload SED (CSV)**) to draw it with the model. The file
format is described in [Fitting your SED](fitting.md#the-data-file). The upload is optional for
a run; it is needed for a fit.

[![An SSC model drawn with uploaded data](img/tm-data.webp#only-light)](img/tm-data.webp)
[![An SSC model drawn with uploaded data](img/tm-data-dark.webp#only-dark)](img/tm-data-dark.webp)

## Citing the models

If you use the modeling tools in a publication, please cite (also under **⋯ → Cite**):

- Bégué, Sahakyan, Dereli Bégué, et al. 2024, ApJ, 963, 71
- Sahakyan, Bégué, Casotto, et al. 2024, ApJ, 971, 70
- Sahakyan, Vardanyan, Giommi, et al. 2024, AJ, 168, 289 (MMDC)

## From Python

The same models are available from Python with the `astro-mmdc` SDK:
see [Blazar emission modeling](../guides/modeling.md).
