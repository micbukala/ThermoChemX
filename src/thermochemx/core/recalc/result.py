# ThermoChemX — Copyright (C) 2026  Michał Bukała <michal.bukala@csic.es>
# This program is free software: GNU General Public License v3 or later.
# It comes with ABSOLUTELY NO WARRANTY. See LICENSE.txt for details.

"""
RecalcResult: the frozen intermediate contract between the neutral core (Layer A)
and the normalisation / adapter layers (Layers B and C).

All quantities are UNNORMALISED absolute values.  Normalisation is Layer B's job.
Every field is derivable from the existing BulkComposition / MolarModel objects
— there is no new physics here.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

__all__ = ["RecalcResult"]


@dataclass(frozen=True)
class RecalcResult:
    # ------------------------------------------------------------------ #
    # Absolute, unnormalised element moles.                               #
    # Keys: Si Ti Al Cr Mn Mg Ca Ni Na K P H2 Fe C S                    #
    #   H2 = H₂ molecules (1 per H₂O); adapters wanting H-atoms × 2.    #
    #   Fe = total Fe (FeOt basis); C = total C (graphite + carbonate);  #
    #   S  = total S as S-atoms (sulfate + sulfide).                     #
    # ------------------------------------------------------------------ #
    element_moles: dict[str, float]

    # Unnormalised total oxygen in O₂ units.
    # Phantom-O is already subtracted (inherited from o2_mol_kg).
    # Adapters that want O-atoms multiply by 2.
    total_oxygen: float

    # ------------------------------------------------------------------ #
    # Resolved redox state (for provenance and adapter re-encoding)       #
    # ------------------------------------------------------------------ #
    fe3_fetot: float        # iron.fe3_fetot_ratio
    co2_ctot: float         # carbon.co2_ctot_ratio
    so3_stot: float         # sulfur.so3_stot_ratio
    s1_sred: float          # sulfur.s1_sred_ratio
    phantom_o_wt: float     # composition.phantom_o_from_sulfide_wt

    # ------------------------------------------------------------------ #
    # Species splits for oxide adapters (Phase 2+)                        #
    # ------------------------------------------------------------------ #
    c4: float           # carbon.c4_wt           → CO₂ component
    c0: float           # carbon.c0_wt            → C⁰ component or O-subtraction
    s6: float           # sulfur.s6_wt             → SO₃ component
    s_red: float        # sulfur.s_red_wt          → S₂ component or dropped

    # ------------------------------------------------------------------ #
    # Bookkeeping                                                         #
    # ------------------------------------------------------------------ #
    # Components that were imported (wt > 0).  This is the normalisation
    # base — adapters must NOT add components that are absent here.
    present_components: frozenset[str]

    sample_name: str
    # Read-only view of the full composition state (for snapshots in files).
    input_snapshot: Mapping[str, object]
    # MolKg1000g denominator (total_model_redox_corrected) stored at build time
    # so oxide and element adapters can reconstruct mol/kg without the live comp.
    # Default 0.0 so existing call-sites that don't pass it remain valid.
    denom: float = 0.0
    warnings: tuple[str, ...] = field(default=())
