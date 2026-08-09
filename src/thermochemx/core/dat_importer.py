# ThermoChemX — Copyright (C) 2026  Michał Bukała <michal.bukala@csic.es>
# This program is free software: GNU General Public License v3 or later.
# It comes with ABSOLUTELY NO WARRANTY. See LICENSE.txt for details.

"""Round-trip importer for ThermoChemX .dat snapshot files: reconstructs a BulkComposition from a previously exported Perple_X output."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .composition import BulkComposition

from ..utils.aliases import IN_KEY_MAP

__all__ = [
    "DatParseResult", "DatImportError",
    "parse_dat_snapshots", "parse_dat_snapshot",
    "apply_snapshot_to_model",
]

# Keys whose values are strings, not floats.
_STRING_KEYS = frozenset({"in.volatile_mode", "in.sample_name"})

# Explicit restore order (correctness-critical — do NOT reorder).
# volatile_mode and sample_name are special-cased; everything else
# is dispatched via IN_KEY_MAP.
_RESTORE_ORDER: tuple[str, ...] = (
    "in.SiO2", "in.TiO2", "in.Al2O3", "in.Cr2O3", "in.MnO", "in.MgO",
    "in.CaO",  "in.NiO",  "in.Na2O",  "in.K2O",   "in.P2O5", "in.H2O",
    "in.LOI",
    "in.fe_tot_as_fe2o3_wt", "in.fe3_fetot_ratio",
    "in.c_tot_wt",           "in.co2_ctot_ratio",
    "in.s_tot_wt",           "in.so3_stot_ratio",   "in.s1_sred_ratio",
)


class DatImportError(ValueError):
    """Raised for malformed or unsupported .dat snapshot blocks."""


@dataclass
class DatParseResult:
    """Parsed data from one composition snapshot block."""
    format_version: int
    data: dict[str, object]   # in.* keys -> str or float values


def parse_dat_snapshots(text: str) -> list[DatParseResult]:
    """
    Parse all composition snapshot blocks from .dat text.

    Supports single-sample .dat files, multi-block sidecars, and full .dat
    files that also contain a thermodynamic component list block.

    Unknown ``der.*`` / ``tchx.*`` keys are silently tolerated (forward-compat).
    """
    results: list[DatParseResult] = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        if lines[i].strip() == "begin composition snapshot":
            block: list[str] = []
            i += 1
            while i < len(lines) and lines[i].strip() != "end composition snapshot":
                block.append(lines[i])
                i += 1
            if i < len(lines):
                i += 1  # skip "end composition snapshot"
            results.append(_parse_block(block))
        else:
            i += 1
    return results


def parse_dat_snapshot(text: str) -> DatParseResult:
    """
    Parse exactly one composition snapshot block from .dat text.

    Raises DatImportError if zero or more than one block is found.
    For multi-block files use parse_dat_snapshots() instead.
    """
    results = parse_dat_snapshots(text)
    if len(results) == 0:
        raise DatImportError(
            "No 'begin composition snapshot' block found in text."
        )
    if len(results) > 1:
        raise DatImportError(
            f"Expected 1 snapshot block, found {len(results)}.  "
            "Use parse_dat_snapshots() for multi-block files."
        )
    return results[0]


def _parse_block(lines: list[str]) -> DatParseResult:
    """Parse key-value pairs from one snapshot block's interior lines."""
    raw: dict[str, str] = {}
    for raw_line in lines:
        # Strip inline comments
        comment_idx = raw_line.find("#")
        if comment_idx != -1:
            raw_line = raw_line[:comment_idx]
        raw_line = raw_line.strip()
        if not raw_line:
            continue
        parts = raw_line.split(None, 1)
        if len(parts) == 2:
            raw[parts[0]] = parts[1].strip()
        elif len(parts) == 1:
            raw[parts[0]] = ""  # bare key with no value (e.g. empty sample_name)

    # Determine format version
    try:
        fmt = int(raw.get("tchx.format_version", "1"))
    except ValueError:
        fmt = 1

    if fmt != 1:
        raise DatImportError(
            f"Unsupported tchx.format_version={fmt!r}; only version 1 is supported."
        )

    # Extract and type-convert in.* keys only (all others silently ignored)
    data: dict[str, object] = {}
    for key, value_str in raw.items():
        if not key.startswith("in."):
            continue
        if key in _STRING_KEYS:
            data[key] = value_str
        else:
            try:
                data[key] = float(value_str) if value_str else 0.0
            except ValueError:
                pass  # malformed numeric value -- skip silently

    # Require at least in.volatile_mode (its absence signals a malformed block)
    if not data:
        raise DatImportError(
            "No in.* keys found in snapshot block -- block may be malformed."
        )
    if "in.volatile_mode" not in data:
        raise DatImportError(
            "Required key 'in.volatile_mode' is missing from snapshot block."
        )

    return DatParseResult(format_version=fmt, data=data)


def apply_snapshot_to_model(
    result: DatParseResult,
    comp: "BulkComposition",
) -> None:
    """
    Restore a BulkComposition SSoT from a parsed v1 snapshot.

    Restore order (correctness-critical -- do NOT reorder):
      1. _volatile_mode first (governs H2O/LOI reconstruction on all reads)
      2. 12 raw oxides via set_oxide_wt (H2O stored raw, safe regardless of mode)
      3. loi_measured (raw stored value, never loi_display)
      4. Iron SSoT: fe2o3_tot_wt, fe3_fetot_ratio
      5. Carbon SSoT: c_wt, co2_ctot_ratio
      6. Sulfur SSoT: s_wt, so3_stot_ratio, s1_sred_ratio
      7. sample_name

    Dispatches steps 2-6 via IN_KEY_MAP and _RESTORE_ORDER so that the
    in.* → setter mapping is shared with the CSV alias registry.
    Do NOT use species setters (fe2_oxide_wt, s1_wt, etc.) -- they recompute
    ratios and would overwrite the authoritative ratio values read in steps 4-6.
    """
    d = result.data

    # 1. Volatile mode -- must be first
    comp._volatile_mode = str(d.get("in.volatile_mode", "loi_derived"))

    # 2-6. Walk restore order, dispatch via IN_KEY_MAP
    for in_key in _RESTORE_ORDER:
        if in_key not in d:
            continue
        system, prop = IN_KEY_MAP[in_key]
        value = float(d[in_key])
        if system == "simple":
            comp.set_oxide_wt(prop, value)
        elif system == "root":
            if prop == "loi_measured":
                comp.loi_measured = max(0.0, value)
            else:
                setattr(comp, prop, value)
        else:  # "iron", "carbon", "sulfur"
            subsystem = getattr(comp, system)
            setattr(subsystem, prop, value)

    # 7. Sample name
    if "in.sample_name" in d:
        comp.sample_name = str(d["in.sample_name"])