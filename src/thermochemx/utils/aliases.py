# ThermoChemX — Copyright (C) 2026  Michał Bukała <michal.bukala@csic.es>
# This program is free software: GNU General Public License v3 or later.
# It comes with ABSOLUTELY NO WARRANTY. See LICENSE.txt for details.

"""Alias mapping and normalization for oxide and volatile names."""

import re
import unicodedata
from typing import Tuple

__all__ = [
    "normalize_key",
    "OXIDE_ALIASES",
    "SYSTEM_TIERS",
    "RATIO_KEYS",
    "IN_KEY_MAP",
    "LEGACY_V0_HINTS",
]


def normalize_key(name: str) -> str:
    """
    Normalize any user-supplied oxide/volatile name to a canonical lowercase ASCII key.

    Steps:
    1. Decompose Unicode characters (e.g., subscript digits)
    2. Encode to ASCII, dropping non-ASCII residue
    3. Convert to lowercase and strip whitespace
    4. Remove all spaces, underscores, hyphens

    Examples:
        "Fe₂O₃_total_wt" → "fe2o3totalwt"
        "SiO2_wt"        → "sio2wt"
        "C4plus_Ctotal_ratio" → "c4plusctotalratio"
        "fe3_fetot_ratio" → "fe3fetotratio"
    """
    # Step 1: Decompose Unicode
    decomposed = unicodedata.normalize('NFKD', name)

    # Step 2: Drop non-ASCII
    ascii_only = decomposed.encode('ascii', errors='ignore').decode('ascii')

    # Step 3: Lowercase and strip
    lower = ascii_only.lower().strip()

    # Step 4: Remove spaces, underscores, hyphens
    normalized = re.sub(r'[\s_\-]+', '', lower)

    return normalized


# ---------------------------------------------------------------------------
# Per-system input-tier registry (used by core.importer.apply_to_model).
#
# Each system has a list of tiers in priority order; importer applies the
# FIRST tier that has any present key.  Keys in later tiers produce a
# skip-warning.  Within a tier, each inner list is one DOF — only the first
# alias of that DOF present in the input is applied.
#
# All keys are normalized forms (as returned by normalize_key).
# Every key listed here MUST also be present in OXIDE_ALIASES.
# Ratios live in RATIO_KEYS, never inside tiers; they are applied last and
# always override whatever ratio the tier derived.
# ---------------------------------------------------------------------------

SYSTEM_TIERS: dict[str, list[Tuple[str, list[list[str]]]]] = {
    "iron": [
        # Tier A — total iron (Fe₂O₃_total_wt or FeO_total_wt)
        ("A_total_ratio", [
            ["fe2o3totalwt", "feototalwt"],
        ]),
        # Tier B — real oxide pair (Fe₂O₃_wt + FeO_wt)
        ("B_real_oxides", [
            ["feowt"],
            ["fe2o3wt"],
        ]),
        # Tier C — elemental wt% (Fe²⁺ / Fe³⁺)
        ("C_elem_wt", [
            ["fe2pluswt"],
            ["fe3pluswt"],
        ]),
        # Tier D — elemental µg/g
        ("D_elem_ugg", [
            ["fe2plusugg"],
            ["fe3plusugg"],
        ]),
    ],
    "carbon": [
        # Tier A — total carbon (CO₂_total_wt, C_total_wt, or C_total_ugg)
        ("A_total_ratio", [
            ["co2totalwt", "ctotalwt", "ctotalugg"],
        ]),
        # Tier B — species wt% (C0_wt + C4plus_wt)
        ("B_species_wt", [
            ["c0wt"],
            ["c4pluswt"],
        ]),
        # Tier C — species µg/g
        ("C_species_ugg", [
            ["c0ugg"],
            ["c4plusugg"],
        ]),
    ],
    "sulfur": [
        # Tier A — total sulfur (SO₃_total_wt, S_total_wt, or S_total_ugg)
        ("A_total_ratio", [
            ["so3totalwt", "stotalwt", "stotalugg"],
        ]),
        # Tier B — species wt% (S6plus_wt, S1minus_wt, S2minus_wt)
        ("B_species_wt", [
            ["s6pluswt"],
            ["s1minuswt"],
            ["s2minuswt"],
        ]),
        # Tier C — species µg/g
        ("C_species_ugg", [
            ["s6plusugg"],
            ["s1minusugg"],
            ["s2minusugg"],
        ]),
    ],
}


# RATIO keys — applied last (Pass 2).  Two live spellings per ratio:
#   • new v1.0 CSV key  (e.g. "Fe3plus_Fetotal_ratio")
#   • canonical SSoT name used by snapshot re-import  (e.g. "fe3_fetot_ratio")
RATIO_KEYS = {
    # Fe³⁺/ΣFe
    "fe3plusfetotalratio", "fe3fetotratio",
    # C⁴⁺/ΣC
    "c4plusctotalratio", "co2ctotratio",
    # S⁶⁺/ΣS
    "s6plusstotalratio", "so3stotratio",
    # S¹⁻/Sred
    "s1minusssulfidesratio", "s1sredratio",
}


# ---------------------------------------------------------------------------
# Full alias dictionary: normalized_key → (system, property_name)
#
# v1.0 vocabulary only.  Two live spellings per ratio input (new CSV key +
# canonical SSoT name).  All removed v0 aliases are listed in LEGACY_V0_HINTS.
# ---------------------------------------------------------------------------

OXIDE_ALIASES: dict[str, Tuple[str, str]] = {

    # --- Simple oxides (v1.0: _wt suffix required) ---
    "sio2wt":   ("simple", "SiO2"),
    "tio2wt":   ("simple", "TiO2"),
    "al2o3wt":  ("simple", "Al2O3"),
    "cr2o3wt":  ("simple", "Cr2O3"),
    "mnowt":    ("simple", "MnO"),
    "mgowt":    ("simple", "MgO"),
    "caowt":    ("simple", "CaO"),
    "niowt":    ("simple", "NiO"),
    "na2owt":   ("simple", "Na2O"),
    "k2owt":    ("simple", "K2O"),
    "p2o5wt":   ("simple", "P2O5"),
    "h2owt":    ("simple", "H2O"),

    # --- LOI (v1.0: LOI_wt) ---
    "loiwt":    ("root", "loi_measured"),

    # --- Iron — Tier A: total Fe ---
    "fe2o3totalwt":        ("iron", "fe2o3_tot_wt"),   # Fe2O3_total_wt  (SSoT)
    "feototalwt":          ("iron", "feo_tot_wt"),      # FeO_total_wt    (derived setter)

    # --- Iron — Tier B: real oxide pair ---
    "fe2o3wt":             ("iron", "fe3_oxide_wt"),    # Fe2O3_wt  (ferric)
    "feowt":               ("iron", "fe2_oxide_wt"),    # FeO_wt    (ferrous)

    # --- Iron — Tier C: elemental wt% ---
    "fe2pluswt":           ("iron", "fe2_wt"),          # Fe2plus_wt  (Fe²⁺)
    "fe3pluswt":           ("iron", "fe3_wt"),          # Fe3plus_wt  (Fe³⁺)

    # --- Iron — Tier D: elemental µg/g ---
    "fe2plusugg":          ("iron", "fe2_ugg"),         # Fe2plus_ugg
    "fe3plusugg":          ("iron", "fe3_ugg"),         # Fe3plus_ugg

    # --- Iron — ratios (Pass 2): new CSV key + canonical SSoT name ---
    "fe3plusfetotalratio": ("iron", "fe3_fetot_ratio"), # Fe3plus_Fetotal_ratio
    "fe3fetotratio":       ("iron", "fe3_fetot_ratio"), # fe3_fetot_ratio  (canonical)

    # --- Carbon — Tier A: total C ---
    "ctotalwt":            ("carbon", "c_wt"),          # C_total_wt    (SSoT)
    "co2totalwt":          ("carbon", "co2_wt"),        # CO2_total_wt  (derived setter)
    "ctotalugg":           ("carbon", "total_c_ugg"),   # C_total_ugg

    # --- Carbon — Tier B: species wt% ---
    "c0wt":                ("carbon", "c0_wt"),         # C0_wt    (graphitic C⁰)
    "c4pluswt":            ("carbon", "c4_wt"),         # C4plus_wt (carbonate C⁴⁺)

    # --- Carbon — Tier C: species µg/g ---
    "c0ugg":               ("carbon", "c0_ugg"),        # C0_ugg
    "c4plusugg":           ("carbon", "c4_ugg"),        # C4plus_ugg

    # --- Carbon — ratios (Pass 2): new CSV key + canonical SSoT name ---
    "c4plusctotalratio":   ("carbon", "co2_ctot_ratio"), # C4plus_Ctotal_ratio
    "co2ctotratio":        ("carbon", "co2_ctot_ratio"), # co2_ctot_ratio  (canonical)

    # --- Sulfur — Tier A: total S ---
    "stotalwt":            ("sulfur", "s_wt"),          # S_total_wt    (SSoT)
    "so3totalwt":          ("sulfur", "so3_wt"),        # SO3_total_wt  (derived setter)
    "stotalugg":           ("sulfur", "total_s_ugg"),   # S_total_ugg

    # --- Sulfur — Tier B: species wt% ---
    "s6pluswt":            ("sulfur", "s6_wt"),         # S6plus_wt   (sulfate S⁶⁺)
    "s1minuswt":           ("sulfur", "s1_wt"),         # S1minus_wt  (disulfide S¹⁻)
    "s2minuswt":           ("sulfur", "s2_wt"),         # S2minus_wt  (monosulfide S²⁻)

    # --- Sulfur — Tier C: species µg/g ---
    "s6plusugg":           ("sulfur", "s6_ugg"),        # S6plus_ugg
    "s1minusugg":          ("sulfur", "s1_ugg"),        # S1minus_ugg
    "s2minusugg":          ("sulfur", "s2_ugg"),        # S2minus_ugg

    # --- Sulfur — ratios (Pass 2): new CSV key + canonical SSoT name ---
    "s6plusstotalratio":      ("sulfur", "so3_stot_ratio"), # S6plus_Stotal_ratio
    "so3stotratio":           ("sulfur", "so3_stot_ratio"), # so3_stot_ratio  (canonical)
    "s1minusssulfidesratio":  ("sulfur", "s1_sred_ratio"),  # S1minus_Ssulfides_ratio
    "s1sredratio":            ("sulfur", "s1_sred_ratio"),  # s1_sred_ratio   (canonical)
}


# ---------------------------------------------------------------------------
# Snapshot (in.*) key → (system, setter_name)
#
# Used by dat_importer.apply_snapshot_to_model to dispatch in.* keys from
# a .dat snapshot to BulkComposition setters via a shared registry.
# Special-cased keys (in.volatile_mode, in.sample_name) are NOT here;
# dat_importer handles them directly.
# ---------------------------------------------------------------------------

IN_KEY_MAP: dict[str, Tuple[str, str]] = {
    # 12 simple oxides — dispatched via comp.set_oxide_wt(prop, value)
    "in.SiO2":               ("simple", "SiO2"),
    "in.TiO2":               ("simple", "TiO2"),
    "in.Al2O3":              ("simple", "Al2O3"),
    "in.Cr2O3":              ("simple", "Cr2O3"),
    "in.MnO":                ("simple", "MnO"),
    "in.MgO":                ("simple", "MgO"),
    "in.CaO":                ("simple", "CaO"),
    "in.NiO":                ("simple", "NiO"),
    "in.Na2O":               ("simple", "Na2O"),
    "in.K2O":                ("simple", "K2O"),
    "in.P2O5":               ("simple", "P2O5"),
    "in.H2O":                ("simple", "H2O"),
    # LOI — dispatched via comp.loi_measured = max(0, value)
    "in.LOI":                ("root",   "loi_measured"),
    # Iron SSoT
    "in.fe_tot_as_fe2o3_wt": ("iron",   "fe2o3_tot_wt"),
    "in.fe3_fetot_ratio":    ("iron",   "fe3_fetot_ratio"),
    # Carbon SSoT
    "in.c_tot_wt":           ("carbon", "c_wt"),
    "in.co2_ctot_ratio":     ("carbon", "co2_ctot_ratio"),
    # Sulfur SSoT
    "in.s_tot_wt":           ("sulfur", "s_wt"),
    "in.so3_stot_ratio":     ("sulfur", "so3_stot_ratio"),
    "in.s1_sred_ratio":      ("sulfur", "s1_sred_ratio"),
}


# ---------------------------------------------------------------------------
# Legacy v0 alias hints
#
# Maps normalized v0 key → suggested v1.0 key string, used to produce
# friendlier "did you mean?" warnings when a removed alias is encountered.
# ---------------------------------------------------------------------------

LEGACY_V0_HINTS: dict[str, str] = {
    # Simple oxides — bare form removed (add _wt suffix)
    "sio2":   "SiO2_wt",   "tio2":  "TiO2_wt",  "al2o3": "Al2O3_wt",
    "cr2o3":  "Cr2O3_wt",  "mno":   "MnO_wt",   "mgo":   "MgO_wt",
    "cao":    "CaO_wt",    "nio":   "NiO_wt",   "na2o":  "Na2O_wt",
    "k2o":    "K2O_wt",    "p2o5":  "P2O5_wt",  "h2o":   "H2O_wt",
    "loi":    "LOI_wt",    "loimeasured": "LOI_wt",
    # Iron v0
    "fe2o3t":     "Fe2O3_total_wt", "fe2o3tot":   "Fe2O3_total_wt",
    "fe2o3total": "Fe2O3_total_wt",
    "feot":       "FeO_total_wt",   "feotot":     "FeO_total_wt",
    "feototal":   "FeO_total_wt",
    "fe2o3":      "Fe2O3_wt",       "feo":        "FeO_wt",
    "fe2":        "Fe2plus_wt",     "fe2+":       "Fe2plus_wt",
    "fe2wt":      "Fe2plus_wt",
    "fe3":        "Fe3plus_wt",     "fe3+":       "Fe3plus_wt",
    "fe3wt":      "Fe3plus_wt",
    "fe2ugg":     "Fe2plus_ugg",    "fe3ugg":     "Fe3plus_ugg",
    "fe3ratio":   "Fe3plus_Fetotal_ratio",
    "fe3feratio": "Fe3plus_Fetotal_ratio",
    "fe3fetot":   "Fe3plus_Fetotal_ratio",
    # Carbon v0
    "co2t":       "CO2_total_wt",  "co2tot":  "CO2_total_wt",
    "co2total":   "CO2_total_wt",  "co2":     "CO2_total_wt",
    "c":          "C_total_wt",    "cwt":     "C_total_wt",
    "ctotal":     "C_total_wt",
    "cugg":       "C_total_ugg",   "ctotugg": "C_total_ugg",
    "cgraphite":  "C0_wt",         "cgraph":  "C0_wt",
    "c0":         "C0_wt",
    "ccarbonate": "C4plus_wt",     "ccarb":   "C4plus_wt",
    "c4":         "C4plus_wt",     "c4+":     "C4plus_wt",
    "c4wt":       "C4plus_wt",
    "cgraphiteugg": "C0_ugg",      "cgraphugg": "C0_ugg",
    "ccarbonateugg": "C4plus_ugg", "ccarbonatesugg": "C4plus_ugg",
    "ccarbugg":   "C4plus_ugg",    "c4ugg":   "C4plus_ugg",
    "co2ratio":   "C4plus_Ctotal_ratio",
    "co2ctot":    "C4plus_Ctotal_ratio",
    # Sulfur v0
    "so3t":       "SO3_total_wt",  "so3tot":  "SO3_total_wt",
    "so3total":   "SO3_total_wt",  "so3":     "SO3_total_wt",
    "s":          "S_total_wt",    "swt":     "S_total_wt",
    "stotal":     "S_total_wt",
    "sugg":       "S_total_ugg",   "stotugg": "S_total_ugg",
    "ssulfate":   "S6plus_wt",     "s6":      "S6plus_wt",
    "s6+":        "S6plus_wt",     "s6wt":    "S6plus_wt",
    "ssulfide":   "S1minus_wt or S2minus_wt",
    "sred":       "S1minus_wt or S2minus_wt",
    "s1":         "S1minus_wt",    "s1minus": "S1minus_wt",
    "s1wt":       "S1minus_wt",
    "s2":         "S2minus_wt",    "s2minus": "S2minus_wt",
    "s2wt":       "S2minus_wt",
    "ssulfateugg": "S6plus_ugg",   "s6ugg":   "S6plus_ugg",
    "ssulfideugg": "S1minus_ugg or S2minus_ugg",
    "sredugg":    "S1minus_ugg or S2minus_ugg",
    "s1ugg":      "S1minus_ugg",
    "s2ugg":      "S2minus_ugg",
    "so3ratio":   "S6plus_Stotal_ratio",
    "s1ratio":    "S1minus_Ssulfides_ratio",
}
