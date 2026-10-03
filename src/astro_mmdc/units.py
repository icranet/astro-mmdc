"""Unit conversions for SED axes, the same ones the website offers.

The API sends frequency in Hz and νFν in erg cm⁻² s⁻¹; everything else is
converted here, with the same formulas and constants the website uses, so
the numbers match the website's.
Missing values (``None``) stay ``None``.
"""

from __future__ import annotations

from typing import Callable, Iterable

ERG_TO_EV = 6.242e11
PLANCK_CONST_EV = 4.135667696e-15


def _hz_to_ev(freq_hz: float) -> float:
    return freq_hz * PLANCK_CONST_EV


def _erg_to_tev(flux: float, freq_hz: float) -> float:
    return flux * ERG_TO_EV * 1e-12


def _erg_to_norm(flux: float, freq_hz: float) -> float:
    # dN/dE = νFν / E², in eV⁻¹ cm⁻² s⁻¹.
    return flux * ERG_TO_EV / _hz_to_ev(freq_hz) ** 2


def _erg_to_wm2(flux: float, freq_hz: float) -> float:
    return flux * (1e-7 / 1.0) * (1.0 / 1e-4)


def _erg_to_jyhz(flux: float, freq_hz: float) -> float:
    return _erg_to_wm2(flux, freq_hz) / 1e-26


def _erg_to_fnu_jy(flux: float, freq_hz: float) -> float:
    return flux * (1e-7 / 1.0) * (1.0 / 1e-4) / freq_hz / 1e-26


# name -> (converter, axis label); the website's axis keys are aliases.
X_UNITS: dict[str, tuple[Callable[[float], float], str]] = {
    "Hz": (lambda f: f, r"$\nu$ [Hz]"),
    "eV": (_hz_to_ev, r"$E$ [eV]"),
}
Y_UNITS: dict[str, tuple[Callable[[float, float], float], str]] = {
    "erg cm-2 s-1": (lambda v, f: v, r"$\nu F(\nu)$ [erg cm$^{-2}$ s$^{-1}$]"),
    "TeV cm-2 s-1": (_erg_to_tev, r"$\nu F(\nu)$ [TeV cm$^{-2}$ s$^{-1}$]"),
    # dN/dE = νFν [eV cm⁻² s⁻¹] / E² [eV²].
    "norm": (_erg_to_norm, r"dN/dE [eV$^{-1}$ cm$^{-2}$ s$^{-1}$]"),
    "Jy Hz": (_erg_to_jyhz, r"$\nu F(\nu)$ [Jy $\times$ Hz]"),
    "W m-2": (_erg_to_wm2, r"$\nu F(\nu)$ [W m$^{-2}$]"),
    "Jy": (_erg_to_fnu_jy, r"$F(\nu)$ [Jy]"),
}
_ALIASES = {
    "hz": "Hz",
    "freq_ev": "eV",
    "ev": "eV",
    "erg": "erg cm-2 s-1",
    "nufnu": "erg cm-2 s-1",
    "flux_ev": "TeV cm-2 s-1",
    "flux_norm": "norm",
    "dN/dE": "norm",
    "flux_jyhz": "Jy Hz",
    "flux_wm2": "W m-2",
    "nufnu_fnu_jy": "Jy",
    "fnu_jy": "Jy",
}


def x_unit(name: str) -> str:
    """The canonical x-axis unit name for ``name`` (a unit or a website axis key)."""
    return _canonical(name, X_UNITS)


def y_unit(name: str) -> str:
    """The canonical y-axis unit name for ``name`` (a unit or a website axis key)."""
    return _canonical(name, Y_UNITS)


def _canonical(name: str, table: dict) -> str:
    unit = name if name in table else _ALIASES.get(name, _ALIASES.get(name.lower(), name))
    if unit not in table:
        raise ValueError(f"Unknown unit {name!r}; choose one of {sorted(table)}")
    return unit


def convert_x(freq_hz: Iterable[float | None], unit: str = "Hz") -> list[float | None]:
    """Frequencies in Hz converted to ``unit`` (``"Hz"`` or ``"eV"``)."""
    fn = X_UNITS[x_unit(unit)][0]
    return [None if f is None else fn(f) for f in freq_hz]


def convert_y(
    nufnu: Iterable[float | None],
    freq_hz: Iterable[float | None],
    unit: str = "erg cm-2 s-1",
) -> list[float | None]:
    """νFν in erg cm⁻² s⁻¹ converted to ``unit``; ``freq_hz`` must be in Hz.

    Units: ``erg cm-2 s-1``, ``TeV cm-2 s-1``, ``norm`` (dN/dE in
    eV⁻¹ cm⁻² s⁻¹), ``Jy Hz``, ``W m-2`` and ``Jy`` (F(ν)). Errors convert the
    same way, since every conversion is linear in νFν.
    """
    fn = Y_UNITS[y_unit(unit)][0]
    return [_safe(fn, v, f) for v, f in zip(nufnu, freq_hz)]


def _safe(fn: Callable[[float, float], float], v: float | None, f: float | None) -> float | None:
    if v is None or f is None:
        return None
    try:
        return fn(v, f)
    except ZeroDivisionError:
        return None
