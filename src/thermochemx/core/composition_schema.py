# ThermoChemX — Copyright (C) 2026  Michał Bukała <michal.bukala@csic.es>
# This program is free software: GNU General Public License v3 or later.
# It comes with ABSOLUTELY NO WARRANTY. See LICENSE.txt for details.

"""Snapshot field schema: the ordered table of input and derived fields written 
to the v1.0.0 composition snapshot section of .dat file."""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable, Literal, Optional
if TYPE_CHECKING:
    from .composition import BulkComposition
__all__ = ["SnapshotField", "SNAPSHOT_SCHEMA"]


@dataclass(frozen=True)
class SnapshotField:
    file_key: str
    section: Literal["meta", "in", "der"]
    unit: str
    get: Callable[["BulkComposition"], object]
    set: Optional[Callable[["BulkComposition", object], None]] = field(default=None)


# KEY_W = 22  (key column width used by generate_snapshot)
# Longest in.* key: in.fe_tot_as_fe2o3_wt (21 chars) -> padded to 22 -> 1 space before value.

SNAPSHOT_SCHEMA: list[SnapshotField] = [

    # === in.* fields (volatile_mode first, then oxides, then SSoT scalars) ===
    # NOTE: H2O uses _simple_oxides["H2O"] (raw stored), not get_oxide_wt (computed in h2o_derived).
    # NOTE: LOI uses loi_measured (raw stored), not loi_display (computed in loi_derived).
    SnapshotField("in.volatile_mode",      "in", "",      lambda c: c._volatile_mode),
    SnapshotField("in.SiO2",               "in", "wt%",   lambda c: c.get_oxide_wt("SiO2")),
    SnapshotField("in.TiO2",               "in", "wt%",   lambda c: c.get_oxide_wt("TiO2")),
    SnapshotField("in.Al2O3",              "in", "wt%",   lambda c: c.get_oxide_wt("Al2O3")),
    SnapshotField("in.Cr2O3",              "in", "wt%",   lambda c: c.get_oxide_wt("Cr2O3")),
    SnapshotField("in.MnO",                "in", "wt%",   lambda c: c.get_oxide_wt("MnO")),
    SnapshotField("in.MgO",                "in", "wt%",   lambda c: c.get_oxide_wt("MgO")),
    SnapshotField("in.CaO",                "in", "wt%",   lambda c: c.get_oxide_wt("CaO")),
    SnapshotField("in.NiO",                "in", "wt%",   lambda c: c.get_oxide_wt("NiO")),
    SnapshotField("in.Na2O",               "in", "wt%",   lambda c: c.get_oxide_wt("Na2O")),
    SnapshotField("in.K2O",                "in", "wt%",   lambda c: c.get_oxide_wt("K2O")),
    SnapshotField("in.P2O5",               "in", "wt%",   lambda c: c.get_oxide_wt("P2O5")),
    SnapshotField("in.H2O",                "in", "wt%",   lambda c: c._simple_oxides["H2O"]),
    SnapshotField("in.LOI",                "in", "wt%",   lambda c: c.loi_measured),
    SnapshotField("in.fe_tot_as_fe2o3_wt", "in", "wt%",   lambda c: c.iron.fe2o3_tot_wt),
    SnapshotField("in.fe3_fetot_ratio",    "in", "ratio", lambda c: c.iron.fe3_fetot_ratio),
    SnapshotField("in.c_tot_wt",           "in", "wt%",   lambda c: c.carbon.c_wt),
    SnapshotField("in.co2_ctot_ratio",     "in", "ratio", lambda c: c.carbon.co2_ctot_ratio),
    SnapshotField("in.s_tot_wt",           "in", "wt%",   lambda c: c.sulfur.s_wt),
    SnapshotField("in.so3_stot_ratio",     "in", "ratio", lambda c: c.sulfur.so3_stot_ratio),
    SnapshotField("in.s1_sred_ratio",      "in", "ratio", lambda c: c.sulfur.s1_sred_ratio),
    SnapshotField("in.sample_name",        "in", "",      lambda c: c.sample_name),

    # === der.* fields (informational; ignored on import) ===
    SnapshotField("der.feo_tot_wt",        "der", "wt%",   lambda c: c.iron.feo_tot_wt),
    SnapshotField("der.fe2_oxide_wt",      "der", "wt%",   lambda c: c.iron.fe2_oxide_wt),
    SnapshotField("der.fe3_oxide_wt",      "der", "wt%",   lambda c: c.iron.fe3_oxide_wt),
    SnapshotField("der.fe2_wt",            "der", "wt%",   lambda c: c.iron.fe2_wt),
    SnapshotField("der.fe3_wt",            "der", "wt%",   lambda c: c.iron.fe3_wt),
    SnapshotField("der.fe2_ugg",           "der", "ugg",   lambda c: c.iron.fe2_ugg),
    SnapshotField("der.fe3_ugg",           "der", "ugg",   lambda c: c.iron.fe3_ugg),
    SnapshotField("der.co2_wt",            "der", "wt%",   lambda c: c.carbon.co2_wt),
    SnapshotField("der.c0_wt",             "der", "wt%",   lambda c: c.carbon.c0_wt),
    SnapshotField("der.c4_wt",             "der", "wt%",   lambda c: c.carbon.c4_wt),
    SnapshotField("der.c0_ugg",            "der", "ugg",   lambda c: c.carbon.c0_ugg),
    SnapshotField("der.c4_ugg",            "der", "ugg",   lambda c: c.carbon.c4_ugg),
    SnapshotField("der.c_ugg",             "der", "ugg",   lambda c: c.carbon.total_c_ugg),
    SnapshotField("der.so3_wt",            "der", "wt%",   lambda c: c.sulfur.so3_wt),
    SnapshotField("der.s6_wt",             "der", "wt%",   lambda c: c.sulfur.s6_wt),
    SnapshotField("der.s1_wt",             "der", "wt%",   lambda c: c.sulfur.s1_wt),
    SnapshotField("der.s2_wt",             "der", "wt%",   lambda c: c.sulfur.s2_wt),
    SnapshotField("der.s6_ugg",            "der", "ugg",   lambda c: c.sulfur.s6_ugg),
    SnapshotField("der.s1_ugg",            "der", "ugg",   lambda c: c.sulfur.s1_ugg),
    SnapshotField("der.s2_ugg",            "der", "ugg",   lambda c: c.sulfur.s2_ugg),
    SnapshotField("der.s_ugg",             "der", "ugg",   lambda c: c.sulfur.total_s_ugg),
    SnapshotField("der.fe2_norm_wt",       "der", "wt%",   lambda c: c.fe2_norm_wt),
    SnapshotField("der.fe3_norm_wt",       "der", "wt%",   lambda c: c.fe3_norm_wt),
    SnapshotField("der.c0_norm_wt",        "der", "wt%",   lambda c: c.c0_norm_wt),
    SnapshotField("der.c4_norm_wt",        "der", "wt%",   lambda c: c.c4_norm_wt),
    SnapshotField("der.s6_norm_wt",        "der", "wt%",   lambda c: c.s6_norm_wt),
    SnapshotField("der.s1_norm_wt",        "der", "wt%",   lambda c: c.s1_norm_wt),
    SnapshotField("der.s2_norm_wt",        "der", "wt%",   lambda c: c.s2_norm_wt),
    SnapshotField("der.total_calculated",  "der", "wt%",   lambda c: c.total_calculated),
    SnapshotField("der.total_model",       "der", "wt%",   lambda c: c.total_model),
    SnapshotField("der.phantom_o_wt",      "der", "wt%",   lambda c: c.phantom_o_from_sulfide_wt),
    SnapshotField("der.total_model_o_corr","der", "wt%",   lambda c: c.total_model_redox_corrected),
    SnapshotField("der.model_mass_o_corr", "der", "g/kg",  lambda c: c.model_mass_redox_corrected),
]