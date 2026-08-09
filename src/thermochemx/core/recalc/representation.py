# ThermoChemX — Copyright (C) 2026  Michał Bukała <michal.bukala@csic.es>
# This program is free software: GNU General Public License v3 or later.
# It comes with ABSOLUTELY NO WARRANTY. See LICENSE.txt for details.

"""
Oxide representation transform (Phase 2, revised).

Converts a RecalcResult (element moles, absolute) into a Perple_X oxide-basis
component dict (mol/kg) using the FeOt + excess-O₂ convention.

Component set (output order)::

    SiO2  TiO2  Al2O3  Cr2O3  FeO  MnO  MgO  NiO  CaO  Na2O  K2O
    P2O5  H2O  CO2  S2  O2

Rules:
  - All Fe as FeO (FeOt convention).  Ferric iron adds to the O2 excess term.
  - All C as CO2.  Graphitic C⁰ *subtracts* from the O2 excess.  When graphite
    is abundant and ferric iron / sulfate are low, excess_O2 can be negative —
    this is physically valid for Perple_X databases that define phases with
    negative oxygen stoichiometry.  ``to_perplex_oxide`` never caps this value.
  - All S as S2 (atoms → S₂ molecules, divide by 2).  Sulfate S⁶⁺ adds to the
    O2 excess; sulfide S²⁻/S¹⁻ subtracts (phantom-O already baked in Layer A).
  - O2 = TRUE excess oxygen, possibly negative (NOT capped here).

Excess-O₂ derivation (proven by round-trip, not hardcoded from prose)::

    excess_O2 = 0.25·n(Fe³⁺)  −  n(C⁰)  +  1.5·n(S⁶⁺)  −  0.5·n(S²⁻)  −  0.25·n(S¹⁻)

    Proof: total_oxygen = Σ(oxide_mol × O2_per_formula_unit) + excess_O2
           where the baseline oxide list assigns FeO, CO₂ (all C), and S₂ (no O).

Cap policy:
  The cap (clamp to 0) is an *adapter-level* decision, not a transform decision.
  ``to_perplex_oxide`` never caps.  The standalone helper ``cap_at_zero`` is
  used by ``PerplexOxideAdapter`` (and available for future MAGEMin/THERMOCALC
  adapters) to clamp the exported O₂ to 0 when negative.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .result import RecalcResult

__all__ = ["to_perplex_oxide", "cap_at_zero", "OXIDE_KEY_ORDER", "O2_PER_OXIDE_COMPONENT"]

# Canonical component output order.
OXIDE_KEY_ORDER: list[str] = [
    "SiO2", "TiO2", "Al2O3", "Cr2O3", "FeO", "MnO", "MgO", "NiO",
    "CaO", "Na2O", "K2O", "P2O5", "H2O", "CO2", "S2", "O2",
]

# O₂ molecules per FORMULA UNIT of each component (used by the round-trip test).
# These are formula-unit values — e.g. 1 mol Al₂O₃ = 1.5 mol O₂, because
# oxide_mol_kg is expressed in mol formula-units (= element_mol / n_cations).
O2_PER_OXIDE_COMPONENT: dict[str, float] = {
    "SiO2":  1.0,    # 1 × SiO₂  → 2 O atoms = 1.0  O₂ / formula unit
    "TiO2":  1.0,    # 1 × TiO₂  → 2 O atoms = 1.0  O₂ / formula unit
    "Al2O3": 1.5,    # 1 × Al₂O₃ → 3 O atoms = 1.5  O₂ / formula unit
    "Cr2O3": 1.5,    # 1 × Cr₂O₃ → 3 O atoms = 1.5  O₂ / formula unit
    "FeO":   0.5,    # 1 × FeO   → 1 O atom  = 0.5  O₂ / formula unit
    "MnO":   0.5,
    "MgO":   0.5,
    "NiO":   0.5,
    "CaO":   0.5,
    "Na2O":  0.5,    # 1 × Na₂O  → 1 O atom  = 0.5  O₂ / formula unit
    "K2O":   0.5,    # 1 × K₂O   → 1 O atom  = 0.5  O₂ / formula unit
    "P2O5":  2.5,    # 1 × P₂O₅  → 5 O atoms = 2.5  O₂ / formula unit
    "H2O":   0.5,    # 1 × H₂O   → 1 O atom  = 0.5  O₂ / formula unit
    "CO2":   1.0,    # 1 × CO₂   → 2 O atoms = 1.0  O₂ / formula unit
    "S2":    0.0,    # S₂:   no oxygen in baseline S₂
    "O2":    1.0,    # the excess O₂ term itself
}

_NEGATIVE_O_INFO = (
    "Excess O\u2082 is negative ({:.5f} mol/kg). "
    "This is valid input only if your Perple\u2011X thermodynamic database "
    "and fluid model define phases with negative oxygen stoichiometry "
    "(e.g. graphite). "
    "Verify your database supports this; otherwise Perple\u2011X will reject the input."
)

# Corrective warning — returned by cap_at_zero() when the cap fires.
_CAP_WARNING_CORRECTIVE = (
    "Excess O\u2082 is negative ({:.5g}\u202fmol/kg) for this composition and has been "
    "capped at 0 for the oxide basis, which cannot represent this degree of reduction. "
    "The exported oxide composition no longer closes to the physical bulk. "
    "To preserve the full reduction state, export this sample in the element basis."
)


def cap_at_zero(excess_o2_mol_kg: float) -> tuple[float, bool, str]:
    """
    Apply a zero-floor cap to the excess O₂ term.

    Used by ``PerplexOxideAdapter`` (``o2_cap_policy == "cap_at_zero"``) and
    available for future MAGEMin / THERMOCALC adapters that require non-negative O₂.

    Args:
        excess_o2_mol_kg: The true (possibly negative) excess O₂ in mol/kg.

    Returns:
        ``(capped_value, capped_flag, warning_message)``
        - *capped_value*: 0.0 if input < 0, otherwise the original value.
        - *capped_flag*: True when the cap was applied.
        - *warning_message*: Corrective warning (with original value formatted in)
          when capped, else "".
    """
    if excess_o2_mol_kg < 0.0:
        return 0.0, True, _CAP_WARNING_CORRECTIVE.format(excess_o2_mol_kg)
    return excess_o2_mol_kg, False, ""


def to_perplex_oxide(
    result: "RecalcResult",
) -> tuple[dict[str, float], float, list[str], bool]:
    """
    Convert a RecalcResult to Perple_X oxide-basis mol/kg values.

    The excess O₂ term is returned **as-is** — possibly negative for highly
    reducing (e.g. graphitic) compositions.  No capping is applied here.
    Adapters that require non-negative O₂ should call ``cap_at_zero`` themselves.

    Args:
        result: Frozen RecalcResult from ``build_recalc_result``.
                ``result.denom`` must be > 0.

    Returns:
        ``(oxide_mol_kg, excess_o2_mol_kg, warnings, o2_is_negative)``

        - *oxide_mol_kg*: ``{component_key: mol/kg}`` in OXIDE_KEY_ORDER.
          ``oxide_mol_kg["O2"]`` equals *excess_o2_mol_kg* and may be negative.
        - *excess_o2_mol_kg*: the O₂ excess in mol/kg (same as oxide_mol_kg["O2"],
          returned separately for convenience).
        - *warnings*: list of human-readable strings; non-empty when O₂ < 0
          (informational, not corrective — mass closure still holds).
        - *o2_is_negative*: True when excess_o2_mol_kg < 0.
    """
    if result.denom <= 0.0:
        empty = dict.fromkeys(OXIDE_KEY_ORDER, 0.0)
        return empty, 0.0, ["RecalcResult.denom is zero; cannot compute mol/kg."], False

    em     = result.element_moles
    factor = 1000.0 / result.denom

    # ------------------------------------------------------------------ #
    # Oxide moles per 100 g  (same units as element_moles)               #
    # ------------------------------------------------------------------ #
    oxides_abs: dict[str, float] = {
        "SiO2":  em.get("Si", 0.0),
        "TiO2":  em.get("Ti", 0.0),
        "Al2O3": em.get("Al", 0.0) / 2.0,
        "Cr2O3": em.get("Cr", 0.0) / 2.0,
        "FeO":   em.get("Fe", 0.0),            # all Fe as FeOt
        "MnO":   em.get("Mn", 0.0),
        "MgO":   em.get("Mg", 0.0),
        "NiO":   em.get("Ni", 0.0),
        "CaO":   em.get("Ca", 0.0),
        "Na2O":  em.get("Na", 0.0) / 2.0,
        "K2O":   em.get("K",  0.0) / 2.0,
        "P2O5":  em.get("P",  0.0) / 2.0,
        "H2O":   em.get("H2", 0.0),            # H₂-molecules → H₂O (1:1)
        "CO2":   em.get("C",  0.0),            # all C as CO₂ (regardless of C⁰/C⁴⁺)
        "S2":    em.get("S",  0.0) / 2.0,      # S-atoms → S₂ molecules
    }

    # ------------------------------------------------------------------ #
    # Excess-O₂ derivation                                               #
    #                                                                     #
    # Baseline: all Fe as FeO, all S as S₂ (no O), all C as CO₂.        #
    # excess_O₂ = total_oxygen − encoded_O₂                             #
    # where encoded_O₂ = Σ(oxide_mol × O2_per_formula_unit) for the     #
    # baseline components above (excluding the O₂ term itself).          #
    #                                                                     #
    # Expanded:                                                           #
    #   excess_O₂ = 0.25·n(Fe³⁺) − n(C⁰) + 1.5·n(S⁶⁺)                 #
    #               − 0.5·n(S²⁻) − 0.25·n(S¹⁻)                        #
    # ------------------------------------------------------------------ #
    n_Fe   = em.get("Fe", 0.0)
    n_C    = em.get("C",  0.0)
    n_S    = em.get("S",  0.0)

    n_Fe3    = n_Fe * result.fe3_fetot
    n_C0     = n_C  * (1.0 - result.co2_ctot)
    n_Sred   = n_S  * (1.0 - result.so3_stot)
    n_S6     = n_S  * result.so3_stot
    n_S1     = n_Sred * result.s1_sred
    n_S2     = n_Sred * (1.0 - result.s1_sred)

    excess_o2_abs = (
        0.25 * n_Fe3
        - 1.0 * n_C0
        + 1.5 * n_S6
        - 0.5 * n_S2
        - 0.25 * n_S1
    )

    excess_o2_mol_kg = excess_o2_abs * factor
    o2_is_negative   = excess_o2_abs < 0.0

    warnings: list[str] = []
    if o2_is_negative:
        warnings.append(_NEGATIVE_O_INFO.format(excess_o2_mol_kg))

    oxides_abs["O2"] = excess_o2_abs

    # ------------------------------------------------------------------ #
    # Scale to mol/kg and return in canonical key order                  #
    # ------------------------------------------------------------------ #
    oxide_mol_kg = {k: oxides_abs[k] * factor for k in OXIDE_KEY_ORDER}

    return oxide_mol_kg, excess_o2_mol_kg, warnings, o2_is_negative
