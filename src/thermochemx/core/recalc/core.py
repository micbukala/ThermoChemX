# ThermoChemX — Copyright (C) 2026  Michał Bukała <michal.bukala@csic.es>
# This program is free software: GNU General Public License v3 or later.
# It comes with ABSOLUTELY NO WARRANTY. See LICENSE.txt for details.

"""
build_recalc_result — thin wrapper that extracts unnormalised quantities
from an existing BulkComposition and packages them into RecalcResult.

No new physics.  All values are derived directly from BulkComposition / MolarModel properties.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..composition import BulkComposition
from ...utils.constants import ELEMENT_MASSES, OXIDE_MASSES
from .result import RecalcResult

__all__ = ["build_recalc_result"]


def build_recalc_result(
    comp: BulkComposition,
    sample_name: str = "",
) -> RecalcResult:
    """
    Build a RecalcResult from a fully-populated BulkComposition.

    total_oxygen strategy (Option A):
        total_oxygen = o2_mol_kg × total_model_redox_corrected / 1000

    This exactly reverses the normalisation applied inside MolarModel._mol_kg
    and is guaranteed to be consistent with the redox coefficients already
    tested by the Phase-0 lock.
    """
    m = comp.model

    # ------------------------------------------------------------------ #
    # Absolute element moles (no normalisation)                           #
    # ------------------------------------------------------------------ #
    element_moles: dict[str, float] = {
        "Si": m._abs_mol(comp.get_oxide_wt("SiO2"),  OXIDE_MASSES["sio2"],  1),
        "Ti": m._abs_mol(comp.get_oxide_wt("TiO2"),  OXIDE_MASSES["tio2"],  1),
        "Al": m._abs_mol(comp.get_oxide_wt("Al2O3"), OXIDE_MASSES["al2o3"], 2),
        "Cr": m._abs_mol(comp.get_oxide_wt("Cr2O3"), OXIDE_MASSES["cr2o3"], 2),
        "Mn": m._abs_mol(comp.get_oxide_wt("MnO"),   OXIDE_MASSES["mno"],   1),
        "Mg": m._abs_mol(comp.get_oxide_wt("MgO"),   OXIDE_MASSES["mgo"],   1),
        "Ca": m._abs_mol(comp.get_oxide_wt("CaO"),   OXIDE_MASSES["cao"],   1),
        "Ni": m._abs_mol(comp.get_oxide_wt("NiO"),   OXIDE_MASSES["nio"],   1),
        "Na": m._abs_mol(comp.get_oxide_wt("Na2O"),  OXIDE_MASSES["na2o"],  2),
        "K":  m._abs_mol(comp.get_oxide_wt("K2O"),   OXIDE_MASSES["k2o"],   2),
        "P":  m._abs_mol(comp.get_oxide_wt("P2O5"),  OXIDE_MASSES["p2o5"],  2),
        # H₂ molecules (1 per H₂O).
        "H2": m._abs_mol(comp.get_oxide_wt("H2O"),   OXIDE_MASSES["h2o"],   1),
        # Fe: total iron expressed as FeO (same convention as MolarModel.fe_mol_kg)
        "Fe": m._abs_mol(comp.iron.feo_tot_wt,        OXIDE_MASSES["feo"],   1),
        # C: total elemental carbon (graphite + carbonate combined; not just graphite)
        "C":  m._abs_mol(comp.carbon.c_wt,             ELEMENT_MASSES["c"],   1),
        # S: total sulfur as S-atoms (sulfate + sulfide; not S₂ molecules)
        "S":  m._abs_mol(comp.sulfur.s_wt,             ELEMENT_MASSES["s"],   1),
    }

    # ------------------------------------------------------------------ #
    # Unnormalised total oxygen (Option A — exact reverse of normalisation) #
    # ------------------------------------------------------------------ #
    denom = comp.total_model_redox_corrected
    total_oxygen = m.o2_mol_kg * denom / 1000.0 if denom > 0.0 else 0.0

    # ------------------------------------------------------------------ #
    # Present components (non-zero imported elements = normalisation base) #
    # ------------------------------------------------------------------ #
    present_components: frozenset[str] = frozenset(
        k for k, v in element_moles.items() if v > 0.0
    )

    return RecalcResult(
        element_moles=element_moles,
        total_oxygen=total_oxygen,
        fe3_fetot=comp.iron.fe3_fetot_ratio,
        co2_ctot=comp.carbon.co2_ctot_ratio,
        so3_stot=comp.sulfur.so3_stot_ratio,
        s1_sred=comp.sulfur.s1_sred_ratio,
        phantom_o_wt=comp.phantom_o_from_sulfide_wt,
        c4=comp.carbon.c4_wt,
        c0=comp.carbon.c0_wt,
        s6=comp.sulfur.s6_wt,
        s_red=comp.sulfur.s_red_wt,
        present_components=present_components,
        sample_name=sample_name,
        input_snapshot=comp.snapshot_dict,
        denom=denom,
        warnings=(),
    )
