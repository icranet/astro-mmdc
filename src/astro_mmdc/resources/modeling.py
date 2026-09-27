from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import IO, Any

from astro_mmdc._base import BaseClient
from astro_mmdc._polling import poll_until
from astro_mmdc.exceptions import BatchJobError
from astro_mmdc.models.modeling import (
    BatchResult,
    BatchSubmission,
    CSVValidation,
    InferenceResult,
)

_TERMINAL_FAILURE_STATUSES = frozenset({"error", "cancelled", "failed"})


def _open_file(file: str | Path | IO[bytes]) -> tuple[Any, bool]:
    """Return (file_obj, should_close)."""
    if isinstance(file, (str, Path)):
        return open(file, "rb"), True
    return file, False


class ModelingResource:
    def __init__(self, client: BaseClient) -> None:
        self._client = client

    def infer(
        self,
        *,
        z: float,
        ebl: bool,
        model_type: str = "SSC",
        parameters: dict[str, float],
    ) -> InferenceResult:
        """Run synchronous model inference.

        Returns the model spectrum immediately (no queuing).
        Supports SSC, EIC, and hadronic model types.

        Parameters
        ----------
        z : float
            Redshift of the source.
        ebl : bool
            Whether to apply EBL absorption correction.
        model_type : str
            Model type: ``"SSC"``, ``"EIC"``, or ``"hadronic"``.
        parameters : dict[str, float]
            Model parameters. Keys depend on model_type:

            * **SSC**: ``log_B``, ``log_electron_luminosity``, ``log_gamma_cut``,
              ``log_gamma_min``, ``log_radius``, ``lorentz_factor``, ``spectral_index``
            * **EIC**: SSC params + ``log_Ld``, ``log_MBH``, ``log_nu_BLR``, ``log_nu_DT``
            * **hadronic**: ``log_B``, ``log_Le``, ``log_gamma_e_min``,
              ``log_gamma_e_cut``, ``log_gamma_p_cut``, ``log_Lp``, ``log_R``,
              ``lorentz_factor``, ``pe``, ``pp``
        """
        payload = {
            "z": z,
            "ebl": ebl,
            "model_type": model_type,
            "parameters": parameters,
        }
        response = self._client.request("POST", "/api/modeling/inference/", json=payload)
        body = response.json()
        return InferenceResult.model_validate(body["data"]["best"])

    def validate_csv(self, file: str | Path | IO[bytes]) -> CSVValidation:
        """Validate a CSV file before submitting for batch inference."""
        fobj, should_close = _open_file(file)
        try:
            response = self._client.request(
                "POST",
                "/api/modeling/validate_csv/",
                files={"file": fobj},
            )
        finally:
            if should_close:
                fobj.close()
        return CSVValidation.model_validate(response.json())

    def submit_batch(
        self,
        file: str | Path | IO[bytes],
        *,
        z: float,
        ebl: bool,
        model_type: str,
        email: str = "fit@mmdc.am",
        fixed_parameters: dict[str, float] | None = None,
        likelihood_type: str | None = None,
        n_icecube: int | None = None,
        dt: float | None = None,
        x1: float | None = None,
        x2: float | None = None,
        y: float | None = None,
    ) -> BatchSubmission:
        """Submit a batch inference job. Returns the batch_result_id."""
        fobj, should_close = _open_file(file)
        try:
            # Buffer the CSV so a retried request resends identical content
            # (a consumed stream would silently upload an empty file).
            name = getattr(fobj, "name", None)
            filename = Path(name).name if isinstance(name, str) else "data.csv"
            content = fobj.read()
            form_data: dict[str, str] = {
                "z": str(z),
                "ebl": "true" if ebl else "false",
                "model_type": model_type,
            }
            form_data["email"] = email
            if fixed_parameters is not None:
                form_data["fixed_parameters"] = json.dumps(fixed_parameters)
            if likelihood_type is not None:
                form_data["likelihood_type"] = likelihood_type
            if n_icecube is not None:
                form_data["n_icecube"] = str(n_icecube)
            if dt is not None:
                form_data["dt"] = str(dt)
            if x1 is not None:
                form_data["x1"] = str(x1)
            if x2 is not None:
                form_data["x2"] = str(x2)
            if y is not None:
                form_data["y"] = str(y)

            # One key per submit call: in-call retries replay the same job
            # server-side instead of creating duplicates.
            response = self._client.request(
                "POST",
                "/api/modeling/batch_inference/",
                data=form_data,
                files={"file": (filename, content)},
                headers={"Idempotency-Key": uuid.uuid4().hex},
            )
        finally:
            if should_close:
                fobj.close()
        return BatchSubmission.model_validate(response.json())

    def get_batch_result(self, batch_result_id: str) -> BatchResult:
        """Get the current result of a batch inference job."""
        response = self._client.request(
            "GET", f"/api/modeling/batch_result/{batch_result_id}/"
        )
        return BatchResult.model_validate(response.json())

    def wait_for_batch(
        self,
        batch_result_id: str,
        poll_interval: float = 5.0,
        max_minutes: float = 8.0,
    ) -> BatchResult:
        """Poll until the batch job completes (pdf_link becomes non-null).

        Raises :class:`BatchJobError` immediately if the server reports a terminal
        failure status (``error``, ``cancelled``, ``failed``) — no need to wait
        for the polling deadline.
        """
        def _check(d: dict) -> bool:
            status = d.get("status")
            if status in _TERMINAL_FAILURE_STATUSES:
                raise BatchJobError(batch_result_id, status)
            return d.get("pdf_link") is not None

        data = poll_until(
            self._client,
            f"/api/modeling/batch_result/{batch_result_id}/",
            check=_check,
            interval=poll_interval,
            max_minutes=max_minutes,
        )
        return BatchResult.model_validate(data)

    def batch_infer(
        self,
        file: str | Path | IO[bytes],
        *,
        z: float,
        ebl: bool,
        model_type: str,
        email: str = "fit@mmdc.am",
        fixed_parameters: dict[str, float] | None = None,
        likelihood_type: str | None = None,
        n_icecube: int | None = None,
        dt: float | None = None,
        x1: float | None = None,
        x2: float | None = None,
        y: float | None = None,
        poll_interval: float = 5.0,
        max_minutes: float = 8.0,
    ) -> BatchResult:
        """Submit a batch inference job and wait for completion."""
        submission = self.submit_batch(
            file,
            z=z,
            ebl=ebl,
            model_type=model_type,
            email=email,
            fixed_parameters=fixed_parameters,
            likelihood_type=likelihood_type,
            n_icecube=n_icecube,
            dt=dt,
            x1=x1,
            x2=x2,
            y=y,
        )
        return self.wait_for_batch(
            submission.batch_result_id,
            poll_interval=poll_interval,
            max_minutes=max_minutes,
        )

    def csv_to_json(self, file: str | Path | IO[bytes]) -> dict:
        """Convert a CSV file to JSON format for modeling."""
        fobj, should_close = _open_file(file)
        try:
            response = self._client.request(
                "POST",
                "/api/modeling/csv_to_json/",
                files={"file": fobj},
            )
        finally:
            if should_close:
                fobj.close()
        return response.json()
