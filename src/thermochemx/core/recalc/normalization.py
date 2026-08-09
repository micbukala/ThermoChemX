# ThermoChemX — Copyright (C) 2026  Michał Bukała <michal.bukala@csic.es>
# This program is free software: GNU General Public License v3 or later.
# It comes with ABSOLUTELY NO WARRANTY. See LICENSE.txt for details.

"""
Normalisation strategies for mol/kg calculation (Layer B).

Each strategy exposes a single method:
    denom(comp) -> float

which returns the denominator used in MolarModel._mol_kg.  A non-positive
return value causes _mol_kg to return 0.0 (same guard as the original code).

Phase 0 ships MolKg1000g — the Perple_X element-basis behaviour.
Future phases may add oxide-mol / oxide-wt strategies here.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..composition import BulkComposition

__all__ = ["NormalizationStrategy", "MolKg1000g"]


class NormalizationStrategy(ABC):
    """Abstract base: return the denominator for MolarModel._mol_kg."""

    @abstractmethod
    def denom(self, comp: "BulkComposition") -> float: ...


class MolKg1000g(NormalizationStrategy):
    """
    Existing Perple_X element-basis strategy.

    Divides by total_model_redox_corrected so that
        Σ(mol_i/kg × M_i) = 1000 g/kg
    for any composition including sulfide-bearing rocks.

    This is the REGRESSION ANCHOR: every existing .dat golden file was
    generated with this strategy.  Do not alter its return value.
    """

    def denom(self, comp: "BulkComposition") -> float:
        return comp.total_model_redox_corrected
