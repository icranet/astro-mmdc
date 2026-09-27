from __future__ import annotations

from pathlib import Path
from typing import IO, Any

from pydantic import BaseModel


class ParameterValue(BaseModel):
    value: float
    error: float


class BatchSubmission(BaseModel):
    batch_result_id: str


class BatchResult(BaseModel):
    model_config = {"protected_namespaces": ()}

    status: str | None = None
    data: dict | None = None
    equal_weighted_posterior: list[list[float]] | None = None
    best_parameters: dict[str, ParameterValue] | None = None
    fixed_parameters: dict[str, ParameterValue] | None = None
    model_type: str
    z: float | None = None
    multinest_stats: dict | None = None
    pdf_link: str | None = None
    csv_best_parameters_link: str | None = None
    csv_best_model_link: str | None = None
    uploaded_file: dict | None = None

    def plot(
        self,
        path: str | Path,
        *,
        observed_csv: str | Path | IO[Any] | bool | None = None,
        **kwargs: Any,
    ) -> str:
        """Render the SED (nuFnu vs nu) for this result and save it to ``path``.

        Draws the posterior model curves and best-fit model from :attr:`data`,
        the same way the MMDC web UI does, with your fitted data points overlaid.
        Those points come from :attr:`uploaded_file` automatically — the API
        echoes back the CSV you submitted to ``batch_infer``, so you don't pass
        it again. Use ``observed_csv`` only to override with a different file, or
        ``observed_csv=False`` to omit the points. Extra keyword arguments are
        forwarded to :func:`astro_mmdc._plotting.plot_sed` for styling (colors,
        ``figsize``, ``dpi``, ``xlim``, ``ylim``, ``title``).

        Requires the plotting extra: ``pip install astro-mmdc[plot]``.

        Returns the path the figure was written to.
        """
        from astro_mmdc._plotting import plot_sed

        return plot_sed(self, path, observed_csv=observed_csv, **kwargs)


class InferenceResult(BaseModel):
    """Result from synchronous model inference — the model spectrum."""

    nu: list[float]
    nuFnu: list[float]
    neutrino_energy: list[float] | None = None
    eFe_nu_tot: list[float] | None = None


class CSVValidation(BaseModel):
    success: bool
    message: str
    data_points: int
    columns: list[str]
    frequency_range: list[float]
    flux_range: list[float]
    preview: list[dict]
