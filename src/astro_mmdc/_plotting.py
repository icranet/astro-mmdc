"""SED plotting for batch inference results and observed SEDs.

``plot_sed`` reproduces the nuFnu-vs-nu spectral energy distribution that the MMDC web UI
draws client-side from a batch result: gray posterior model curves, the red
best-fit model, and (optionally) the observed data points overlaid as markers.

Plotting deps are optional — install with ``pip install astro-mmdc[plot]``.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import IO, TYPE_CHECKING, Any

if TYPE_CHECKING:
    from astro_mmdc.models.modeling import BatchResult
    from astro_mmdc.models.sed import SED


def _require(module: str) -> Any:
    try:
        return importlib.import_module(module)
    except ImportError as exc:  # pragma: no cover - exercised via install extras
        raise ImportError(
            f"Plotting requires '{module}'. Install the plotting extra with "
            "`pip install astro-mmdc[plot]`."
        ) from exc


def _read_observations(csv: str | Path | IO[Any]) -> tuple[Any, Any, Any]:
    """Return (x, y, yerr) from an observed-data CSV.

    Accepts either ``frequency/flux/flux_err`` or ``x/y/dy`` column naming,
    matching the formats accepted by the modeling API.
    """
    pd = _require("pandas")
    obs = pd.read_csv(csv)
    if "frequency" in obs.columns:
        xc, yc, ec = "frequency", "flux", "flux_err"
    elif "x" in obs.columns:
        xc, yc, ec = "x", "y", "dy"
    else:
        raise ValueError(
            f"Unrecognised observation columns: {list(obs.columns)}. "
            "Expected frequency/flux/flux_err or x/y/dy."
        )
    yerr = obs[ec] if ec in obs.columns else None
    return obs[xc], obs[yc], yerr


def _observations_from_result(result: "BatchResult") -> tuple[Any, Any, Any] | None:
    """Return (x, y, yerr) from the data points the result echoes back.

    The ``batch_result`` endpoint re-reads the submitted CSV and returns it as
    ``uploaded_file = {"frequency": [...], "flux": [...], "flux_err": [...]}``,
    so the same points you fitted are already on the result — no CSV needed.
    """
    uploaded = result.uploaded_file
    if not isinstance(uploaded, dict):
        return None
    freq, flux = uploaded.get("frequency"), uploaded.get("flux")
    if not freq or not flux:
        return None
    return freq, flux, uploaded.get("flux_err")


def plot_sed(
    result: "BatchResult",
    path: str | Path,
    *,
    observed_csv: str | Path | IO[Any] | bool | None = None,
    title: str | None = None,
    best_color: str = "red",
    posterior_color: str = "lightgray",
    posterior_alpha: float = 0.3,
    data_color: str = "dodgerblue",
    figsize: tuple[float, float] = (10, 6),
    dpi: int = 150,
    xlim: tuple[float, float] | None = None,
    ylim: tuple[float, float] | None = None,
) -> str:
    """Render the SED for ``result`` and save it to ``path``.

    Draws every posterior model curve in ``result.data`` (any key other than
    ``"best"``) in gray, the ``"best"`` curve in ``best_color``, and the observed
    flux points with error bars.

    The observed points come from ``result.uploaded_file`` by default — these are
    the same data you submitted to ``batch_infer``, echoed back by the API, so you
    don't pass the CSV again. Provide ``observed_csv`` only to override them with a
    different file (or pass ``observed_csv=False`` to omit observations entirely).

    Returns the string path the figure was written to.
    """
    if not result.data:
        raise ValueError(
            "result.data is empty — the batch job has no model spectrum to plot "
            "(is it still running?)."
        )

    plt = _require("matplotlib.pyplot")

    fig, ax = plt.subplots(figsize=figsize)

    # Posterior model curves: every entry in data except the best fit.
    for key, curve in result.data.items():
        if key == "best" or not isinstance(curve, dict):
            continue
        nu, nufnu = curve.get("nu"), curve.get("nuFnu")
        if nu and nufnu:
            ax.plot(nu, nufnu, color=posterior_color, alpha=posterior_alpha,
                    lw=0.8, zorder=1)

    # Best-fit model.
    best = result.data.get("best")
    if isinstance(best, dict) and best.get("nu") and best.get("nuFnu"):
        ax.plot(best["nu"], best["nuFnu"], color=best_color, lw=2,
                zorder=4, label="Best model")
        # Hadronic neutrino spectrum, if present.
        if best.get("neutrino_energy") and best.get("eFe_nu_tot"):
            ax.plot(best["neutrino_energy"], best["eFe_nu_tot"], color=best_color,
                    lw=2, ls="--", zorder=4, label="Best model (neutrino)")

    # Observed data points: from the CSV if one is given, otherwise the points
    # the result already carries. observed_csv=False opts out entirely.
    obs: tuple[Any, Any, Any] | None
    if observed_csv is False:
        obs = None
    elif observed_csv is not None:
        obs = _read_observations(observed_csv)
    else:
        obs = _observations_from_result(result)
    if obs is not None:
        x, y, yerr = obs
        ax.errorbar(x, y, yerr=yerr, fmt="o", markersize=6, color=data_color,
                    capsize=3, zorder=5, label="Observations")

    ax.set_xscale("log")
    ax.set_yscale("log")
    if xlim:
        ax.set_xlim(*xlim)
    if ylim:
        ax.set_ylim(*ylim)
    ax.set_xlabel(r"$\nu$ [Hz]", fontsize=14)
    ax.set_ylabel(r"$\nu F(\nu)$ [erg cm$^{-2}$ s$^{-1}$]", fontsize=14)
    if title:
        ax.set_title(title)
    ax.legend()

    path = str(path)
    fig.savefig(path, dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    return path


def plot_points(
    sed: "SED",
    path: str | Path | None = None,
    *,
    x: str = "Hz",
    y: str = "erg cm-2 s-1",
    ax: Any = None,
    title: str | None = None,
    legend: bool = True,
    figsize: tuple[float, float] = (10, 6),
    dpi: int = 150,
) -> Any:
    """Draw an observed SED per catalogue, as the website does; return the Axes."""
    from astro_mmdc import units

    plt = _require("matplotlib.pyplot")
    xu, yu = units.x_unit(x), units.y_unit(y)
    conv = sed.converted(x=xu, y=yu)
    if ax is None:
        _, ax = plt.subplots(figsize=figsize)

    for ci, cat in enumerate(sed.catalogs):
        pts = [
            i for i in range(sed.points)
            if sed.catalog_idx[i] == ci and conv["x"][i] is not None
            and conv["y"][i] is not None and conv["y"][i] > 0 and conv["x"][i] > 0
        ]
        det = [i for i in pts if not sed.is_ul[i]]
        ul = [i for i in pts if sed.is_ul[i]]
        color = cat.color or None
        if det:
            yerr = [conv["y_err"][i] or 0.0 for i in det]
            ax.errorbar([conv["x"][i] for i in det], [conv["y"][i] for i in det],
                        yerr=yerr, fmt="o", markersize=4, color=color, capsize=2,
                        label=cat.name)
        if ul:
            ax.plot([conv["x"][i] for i in ul], [conv["y"][i] for i in ul], "v",
                    markersize=5, color=color, label=None if det else f"{cat.name} (UL)")

    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel(units.X_UNITS[xu][1], fontsize=14)
    ax.set_ylabel(units.Y_UNITS[yu][1], fontsize=14)
    ax.set_title(title if title is not None else sed.source.name)
    if legend and sed.catalogs:
        ax.legend(fontsize="x-small", ncol=2, loc="center left", bbox_to_anchor=(1.01, 0.5))
    if path is not None:
        ax.figure.savefig(str(path), dpi=dpi, bbox_inches="tight")
    return ax
