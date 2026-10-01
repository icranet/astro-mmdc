---
title: "Getting SED data on mmdc.am"
description: "How to build the multiwavelength spectral energy distribution (SED) of a blazar or any sky position on mmdc.am, filter it in time, explore it and download it as CSV."
---

# Getting SED data

The **Data access** section of [mmdc.am](https://mmdc.am/#services) builds the multiwavelength
spectral energy distribution (SED) of any sky position from radio to gamma rays, with the
epoch of every point, and lets you explore it, filter it in time and download it.

[Open Data access on mmdc.am :material-open-in-new:](https://mmdc.am/#services){ .md-button .md-button--primary }

[![The Data access section with the SED of 3C 279](img/sed-overview.webp#only-light)](img/sed-overview.webp)
[![The Data access section with the SED of 3C 279](img/sed-overview-dark.webp#only-dark)](img/sed-overview-dark.webp)

*The SED of 3C 279. Left: the SED and its tabs. Right: the source card and the SED plot options.*

## In short

1. Type a source name and pick it from the list, or type RA Dec in degrees.
2. Press **Plot**.
3. Explore the plot; narrow it with **Time filtering** and **Energy band**.
4. Download the points with the **CSV** button in the source card.

## 1. Choose a source

The source field accepts:

| You type | Example | What happens |
|---|---|---|
| A name | `Mrk 421`, `CTA102` | After three characters a list of matching sources appears; pick one. Case and spaces do not matter. |
| RA Dec in degrees | `338.1517 11.73081` or `338.1517, 11.73081` | Plot is enabled at once, no pick needed. RA from 0 to 360 (360 excluded), Dec from −90 to 90. |

A typed name alone is not enough: pick it from the list (or press ++enter++ to take the first
match), otherwise **Plot** stays disabled.

Names are matched in a catalogue originally developed for the Open Universe platform. A name
not found there is resolved with NED, then SIMBAD. Catalogue coordinates can differ slightly
from NED's; if a search returns nothing, try the NED coordinates instead.

### Browse the blazar lists

**Browse** opens two ready-made lists:

- **Known blazars**: about 6,700 blazars from the 5BZCAT, 3HSP and Fermi-LAT catalogues.
- **γ-ray bright**: about 3,400 γ-ray bright blazars, for which MMDC also has SEDs computed
  over many periods.

Filter a list by name, then click a row: it fills the source field. Press **Plot** to build the SED.

[![The Browse lists](img/sed-browse.webp#only-light)](img/sed-browse.webp)
[![The Browse lists](img/sed-browse-dark.webp#only-dark)](img/sed-browse-dark.webp)

## 2. Plot

Press **Plot**. Two cases:

- **The position was searched before** (by anyone, within 2″): the stored SED is shown at once.
- **A new position**: MMDC searches about 75 catalogues and archives (most from copies kept at
  MMDC, the rest queried live). A progress bar shows
  each stage (searching X-ray and radio catalogues, the other catalogues, light curves,
  combining the data). This can take a few minutes.

To follow a run in detail, open **⋯ → Show logs**. The log lists every catalogue queried and
the number of points it returned.

[![The pipeline log](img/sed-logs.webp#only-light)](img/sed-logs.webp)
[![The pipeline log](img/sed-logs-dark.webp#only-dark)](img/sed-logs-dark.webp)

### Force run

**Plot ▾ → Force run** fetches every catalogue again instead of using the stored SED. Use it
when the last run's logs show that some catalogues were unreachable. When catalogues could not
be queried, a notice above the plot names them and offers **View logs** and **Re-run (force)**.
While a re-run is going on, the previous SED stays on screen.

[![The Plot menu with Force run](img/sed-plot-menu.webp#only-light)](img/sed-plot-menu.webp)
[![The Plot menu with Force run](img/sed-plot-menu-dark.webp#only-dark)](img/sed-plot-menu-dark.webp)

## 3. Explore the SED

The plot is interactive: hover a point for its values, drag to zoom, double-click to reset.
Upper limits are drawn as arrows. The camera icon in the plot's toolbar saves a PNG.

### The source card

The card beside the plot shows:

| Field | Meaning |
|---|---|
| RA, Dec | J2000, in degrees and sexagesimal |
| Galactic | Galactic longitude *l* and latitude *b* |
| Redshift | From NED, SIMBAD or other catalogues, when one is known |
| log ν<sub>peak</sub> [Hz] | Peak frequency of the synchrotron emission, estimated from the source's WISE/NEOWISE infrared data when they are not dominated by emission unrelated to the jet. "> 17.5" is a lower limit; "—" means no estimate. |

### SED plot options

The panel under the card has three sections; one is open at a time.

<div class="grid" markdown>

[![Time filtering](img/sed-time.webp#only-light)](img/sed-time.webp)
[![Time filtering](img/sed-time-dark.webp#only-dark)](img/sed-time-dark.webp)

[![Plot options](img/sed-options.webp#only-light)](img/sed-options.webp)
[![Plot options](img/sed-options-dark.webp#only-dark)](img/sed-options-dark.webp)

[![Energy band](img/sed-bands.webp#only-light)](img/sed-bands.webp)
[![Energy band](img/sed-bands-dark.webp#only-dark)](img/sed-bands-dark.webp)

</div>

**Time filtering** keeps only the points observed in a time window: **All time**, **One day**
or a **Range**. Points without an observation epoch (catalogue averages) are hidden while a
window is set, unless **Show undated catalogue values** is ticked.

**Plot options** change the units:

- X axis: frequency in Hz, or energy in eV.
- Y axis: νF(ν) in erg cm⁻² s⁻¹, TeV cm⁻² s⁻¹, Jy × Hz or W/m², dN/dE in eV⁻¹ cm⁻² s⁻¹,
  or F(ν) in Jy.

**Energy band** lists the bands (radio to gamma rays) and, inside each, the catalogues that
returned data. Untick a band or a catalogue to hide its points.

The options apply to the SED tab.

## 4. Download the data

The **CSV (Hz, erg cm⁻² s⁻¹)** button in the source card downloads the points shown: it
follows the time window and the ticked catalogues. Units are always Hz and erg cm⁻² s⁻¹,
whatever the axes on screen.

| Column | Content |
|---|---|
| `freq_hz` | Frequency [Hz] |
| `nufnu` | νF(ν) [erg cm⁻² s⁻¹] |
| `nufnu_err` | Error on νF(ν) [erg cm⁻² s⁻¹] |
| `is_ul` | `true` if the point is an upper limit |
| `mjd_start` | Start of the observation [MJD]; 50000 for a point without an epoch (catalogue average) |
| `mjd_end` | End of the observation [MJD]; 50000 for a point without an epoch (catalogue average) |
| `catalog` | Catalogue the point comes from |
| `band` | Energy band |
| `reference` | Bibliographic reference of the catalogue |

Every row carries its reference, so the data can be cited properly. MMDC data are available
under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/); see [Citing](../citing.md).

## 5. More about the source

The tabs above the plot open once a source is plotted.

### SED/LC animation

A video of how the SED changes over time, built from quasi-simultaneous data, next to the
light curve. It is pre-computed for a set of sources; for the others the tab says the
animation is not available.

[![The SED/LC animation of 3C 279](img/sed-animation.webp#only-light)](img/sed-animation.webp)
[![The SED/LC animation of 3C 279](img/sed-animation-dark.webp#only-dark)](img/sed-animation-dark.webp)

### Aladin

The sky around the source in the [Aladin Lite](https://aladin.cds.unistra.fr/AladinLite/)
atlas, with the source marked. Switch between optical, infrared, radio, X-ray and gamma-ray
surveys, and turn on a coordinate grid. It needs a browser with WebGL2.

[![The Aladin sky view](img/sed-aladin.webp#only-light)](img/sed-aladin.webp)
[![The Aladin sky view](img/sed-aladin-dark.webp#only-dark)](img/sed-aladin-dark.webp)

### Related articles

Papers about the source from the [SAO/NASA Astrophysics Data System](https://ui.adsabs.harvard.edu)
(ADS). Sort by **Newest**, **Most cited** or **Relevance**, keep only refereed papers, open an
abstract, and follow the ADS, arXiv, DOI and PDF links.

[![Related articles for 3C 279](img/sed-articles.webp#only-light)](img/sed-articles.webp)
[![Related articles for 3C 279](img/sed-articles-dark.webp#only-dark)](img/sed-articles-dark.webp)

## From Python

Everything on this page is also available from Python with the `astro-mmdc` SDK:
see [SED data](../guides/sed.md).

[Open Data access on mmdc.am :material-open-in-new:](https://mmdc.am/#services){ .md-button }
