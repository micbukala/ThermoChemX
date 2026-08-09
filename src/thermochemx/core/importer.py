# ThermoChemX — Copyright (C) 2026  Michał Bukała <michal.bukala@csic.es>
# This program is free software: GNU General Public License v3 or later.
# It comes with ABSOLUTELY NO WARRANTY. See LICENSE.txt for details.

"""File import functionality for ThermoChemX composition data."""

from __future__ import annotations

import csv
import math
from dataclasses import dataclass, field
from io import StringIO
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .composition import BulkComposition

from ..utils.aliases import (
    OXIDE_ALIASES,
    SYSTEM_TIERS,
    RATIO_KEYS,
    normalize_key,
    LEGACY_V0_HINTS,
)
from ..utils.constants import ELEMENT_MASSES, OXIDE_MASSES

__all__ = ["parse_file", "apply_to_model", "ImportResult", "SampleData", "parse_file_multi"]

# Header keywords — used by both parse_file() and parse_file_multi()
HEADER_KEYWORDS = {"oxidevolatile", "oxide", "volatile", "name", "label", "samplename", "wt%", "wt.%"}

# User-facing encoding-fallback warning (kept as a module constant so tests
# can match on it exactly without duplicating the phrasing).
ENCODING_FALLBACK_WARNING = (
    "File is not UTF-8 encoded — it was probably saved by Excel as ANSI. "
    "It was imported using Windows-1252 instead. Check that special "
    "characters survived, and re-save the file as 'CSV UTF-8' to avoid "
    "this warning."
)

# Clean per-file error message used when a file cannot be decoded as text
# at all, or decodes but contains none of the canary alias keys.
UNREADABLE_FILE_MESSAGE = (
    "File could not be read as text. Please export your data as CSV UTF-8 "
    "and re-import."
)

# Canary substrings used as a sanity check after the cp1252 fallback:
# cp1252 accepts nearly all byte values, so a corrupt binary may decode
# without an exception. Requiring at least one of these guarantees the
# result is plausibly a ThermoChemX composition file.
_ALIAS_CANARIES = ("sio2", "al2o3", "fe2o3", "feo", "cao", "mgo", "k2o", "na2o", "loi")


@dataclass
class SampleData:
    """A single sample's composition data parsed from import file."""
    name: str                    # sample identifier (from sample_name row or filename)
    data: dict[str, float]       # {original_oxide_name: float_value}


@dataclass
class ImportResult:
    """Result of importing composition data into the model."""

    applied: list[str] = field(default_factory=list)  # field names successfully set
    skipped: list[str] = field(default_factory=list)  # unrecognized names
    warnings: list[str] = field(default_factory=list)  # recognized but overridden by priority


# ---------------------------------------------------------------------------
# Low-level file readers & helpers
# ---------------------------------------------------------------------------

def _try_float(val) -> float | None:
    """Convert *val* to float; return None for empty / non-numeric / NaN."""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        f = float(val)
        return None if math.isnan(f) else f
    s = str(val).strip()
    if not s or s.lower() == "nan":
        return None
    try:
        f = float(s)
        return None if math.isnan(f) else f
    except ValueError:
        return None


def _decode_file(path: str) -> tuple[str, list[str]]:
    """Read *path* as text with a UTF-8 → cp1252 fallback.

    Returns ``(text, warnings)``. ``warnings`` is a list of file-level
    warning strings (empty when the file decoded cleanly as UTF-8).

    - First tries ``utf-8-sig`` (also strips a UTF-8 BOM if present).
    - On :class:`UnicodeDecodeError`, retries with ``cp1252`` (Windows-1252)
      because Excel's default "CSV" export on Windows writes ANSI. When the
      fallback succeeds and the decoded text contains at least one canary
      oxide-alias substring, appends :data:`ENCODING_FALLBACK_WARNING`.
    - If neither codec works, or cp1252 decodes but the result lacks any
      recognisable alias key (probably binary garbage), raises
      :class:`ValueError` with :data:`UNREADABLE_FILE_MESSAGE`.
    """
    raw = Path(path).read_bytes()
    try:
        return raw.decode("utf-8-sig"), []
    except UnicodeDecodeError:
        pass
    try:
        text = raw.decode("cp1252")
    except UnicodeDecodeError:
        raise ValueError(UNREADABLE_FILE_MESSAGE)
    lowered = text.lower()
    if not any(canary in lowered for canary in _ALIAS_CANARIES):
        # cp1252 accepted the bytes but the content isn't a composition file.
        raise ValueError(UNREADABLE_FILE_MESSAGE)
    return text, [ENCODING_FALLBACK_WARNING]


def _detect_delimiter(sample: str) -> str:
    """Detect the CSV delimiter from a text sample.

    Deterministic rule: for each candidate delimiter (comma, semicolon,
    tab, pipe) csv-parse the first up-to-20 non-empty lines, note the
    *modal* column count each candidate produces, and score by
    ``modal_count × rows_that_match_modal``. The candidate with the
    highest score wins. Ties are broken by preferred order
    (``, ; \\t |``). If no candidate yields more than one column for any
    row, defaults to ``,``.

    Chosen over :class:`csv.Sniffer` because Sniffer's heuristic is
    quote-aware but delimiter-agnostic: it happily picks a stray
    in-field comma over a real tab delimiter when the sample is short.
    The deterministic rule is more predictable and easier to reason
    about.
    """
    lines = [ln for ln in sample.splitlines()[:20] if ln.strip()]
    if not lines:
        return ","
    scores: dict[str, int] = {}
    for delim in (",", ";", "\t", "|"):
        counts: list[int] = []
        for ln in lines:
            row = next(csv.reader(StringIO(ln), delimiter=delim), None)
            if row is not None:
                counts.append(len(row))
        if not counts:
            scores[delim] = 0
            continue
        modal = max(set(counts), key=counts.count)
        if modal <= 1:
            scores[delim] = 0  # never split → useless
            continue
        hits = counts.count(modal)
        scores[delim] = modal * hits
    best = max(scores.values())
    if best == 0:
        return ","
    # Preference order on tie: comma, semicolon, tab, pipe.
    for delim in (",", ";", "\t", "|"):
        if scores[delim] == best:
            return delim
    return ","


def _read_csv_rows(path: str) -> tuple[list[list], list[str]]:
    """Read a CSV/TSV file into ``(rows, file_warnings)``.

    ``file_warnings`` carries any file-scope warnings raised by the decode
    step (currently: cp1252 fallback). Uses :func:`_decode_file` for
    encoding handling and :func:`_detect_delimiter` for delimiter
    resolution; no pandas, no strict UTF-8.
    """
    text, warnings = _decode_file(path)
    delimiter = _detect_delimiter(text)
    rows = list(csv.reader(StringIO(text), delimiter=delimiter))
    return rows, warnings


def _read_xlsx_rows(path: str) -> list[list]:
    """Read an XLSX file into a list-of-lists using openpyxl (read-only, fast)."""
    import openpyxl
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        ws = wb.active
        return [list(row) for row in ws.iter_rows(values_only=True)]
    finally:
        wb.close()


def _detect_orientation(rows: list[list]) -> str:
    """Return ``"standard"`` or ``"transposed"`` for *rows*.

    Standard layout  : column 0 = oxide labels, columns 1..N = sample values.
    Transposed layout: row 0 (or 1) = oxide labels, rows 1..N = sample values.
    """
    alias_keys = set(OXIDE_ALIASES.keys())

    if not rows:
        return "standard"

    # Matches in column 0  →  standard layout
    col0_matches = sum(
        1 for row in rows if row and normalize_key(str(row[0])) in alias_keys
    )

    # Matches in row 0 (skip cell [0][0])  →  transposed layout
    row0 = rows[0]
    row0_matches = sum(
        1 for val in (row0[1:] if len(row0) > 1 else [])
        if normalize_key(str(val)) in alias_keys
    )

    # Row 0 empty? Try row 1 (may be a pure header, e.g. "sample_name")
    if row0_matches == 0 and len(rows) > 1:
        row1 = rows[1]
        row0_matches = sum(
            1 for val in (row1[1:] if len(row1) > 1 else [])
            if normalize_key(str(val)) in alias_keys
        )

    if row0_matches >= 3 and row0_matches > col0_matches:
        return "transposed"
    return "standard"


def _detect_key_column(rows: list[list]) -> int:
    """Return the column index (0 or 1) that holds recognized alias keys.

    Counts OXIDE_ALIASES matches in columns 0 and 1 and returns the column
    with strictly more matches.  Defaults to 0 on tie or when both score zero
    (backward-compat with the legacy two-column form).

    Callers should only invoke this when ``ncols >= 3``; for two-column files
    the key column is always 0.
    """
    alias_keys = set(OXIDE_ALIASES.keys())
    col0 = 0
    col1 = 0
    for row in rows:
        if row:
            if len(row) > 0 and normalize_key(str(row[0])) in alias_keys:
                col0 += 1
            if len(row) > 1 and normalize_key(str(row[1])) in alias_keys:
                col1 += 1
    return 1 if col1 > col0 else 0


def _transpose_rows(rows: list[list]) -> list[list]:
    """Transpose a (possibly ragged) list-of-lists, padding shorter rows with ``""``."""
    if not rows:
        return rows
    ncols = max(len(r) for r in rows)
    padded = [r + [""] * (ncols - len(r)) for r in rows]
    return [list(col) for col in zip(*padded)]


def parse_file(path: str) -> dict[str, float]:
    """Parse composition data from a two-column .xlsx or .csv file.

    Returns a raw ``{original_name: float_value}`` dict.

    File-level warnings (e.g. cp1252 encoding fallback) are discarded here;
    callers that need them should use :func:`parse_file_multi`.

    Raises:
        ValueError: Unsupported file extension.
        Exception:  File read or parse failure.
    """
    path_obj = Path(path)
    ext = path_obj.suffix.lower()

    if ext not in {".xlsx", ".csv"}:
        raise ValueError(
            f"Unsupported file type: {ext}. Only .xlsx and .csv are supported."
        )

    try:
        if ext == ".xlsx":
            rows = _read_xlsx_rows(path)
        else:
            rows, _ = _read_csv_rows(path)
    except Exception as exc:
        raise Exception(f"Failed to read file: {exc}") from exc

    result: dict[str, float] = {}
    for row in rows:
        if len(row) < 2:
            continue
        name = str(row[0]).strip()
        if not name or normalize_key(name) in HEADER_KEYWORDS:
            continue
        val = _try_float(row[1])
        if val is None:
            continue
        result[name] = val

    return result


def parse_file_multi(path: str) -> tuple[list[SampleData], list[str]]:
    """Parse single or multiple samples from .xlsx or .csv.

    Auto-detects layout orientation (standard / transposed) and number of
    samples (2 columns → single sample; >2 columns → multi-sample).

    Returns ``(samples, file_warnings)`` where ``file_warnings`` are
    file-scope warnings surfaced by the read step (currently: cp1252
    encoding fallback). ``file_warnings`` is always an empty list for
    .xlsx.

    Raises:
        ValueError: Unsupported file extension, too few columns, or the
            file cannot be decoded as text at all.
        Exception:  Other file read or parse failure.
    """
    path_obj = Path(path)
    ext = path_obj.suffix.lower()

    if ext not in {".xlsx", ".csv"}:
        raise ValueError(
            f"Unsupported file type: {ext}. Only .xlsx and .csv are supported."
        )

    file_warnings: list[str] = []
    try:
        if ext == ".xlsx":
            rows = _read_xlsx_rows(path)
        else:
            rows, file_warnings = _read_csv_rows(path)
    except ValueError:
        # Clean, user-facing ValueError from _decode_file — propagate as-is.
        raise
    except Exception as exc:
        raise Exception(f"Failed to read file: {exc}") from exc

    if not rows:
        return [], file_warnings

    # --- Orientation detection & optional transpose ---
    ncols = max((len(r) for r in rows), default=0)
    if len(rows) >= 2 and ncols >= 2 and _detect_orientation(rows) == "transposed":
        rows = _transpose_rows(rows)
        ncols = max((len(r) for r in rows), default=0)

    if ncols < 2:
        raise ValueError(f"File must have at least 2 columns, got {ncols}")

    # --- Comment-column detection (three-column layout) ---
    # key_col=0: legacy two-column form (key in col 0)
    # key_col=1: comment form (free-text description in col 0, key in col 1)
    key_col = _detect_key_column(rows) if ncols >= 3 else 0

    # --- Single-sample shortcut (key col + exactly one value col) ---
    if ncols - key_col == 2:
        result: dict[str, float] = {}
        for row in rows:
            if len(row) < key_col + 2:
                continue
            name = str(row[key_col]).strip()
            if not name or normalize_key(name) in HEADER_KEYWORDS:
                continue
            val = _try_float(row[key_col + 1])
            if val is None:
                continue
            result[name] = val
        return [SampleData(name=path_obj.stem, data=result)], file_warnings

    # --- Multi-sample: key_col = labels, key_col+1..N = samples ---
    # Locate the sample_name row to extract column headers
    sample_names: list[str] = []
    sample_name_row_idx: int | None = None

    for idx, row in enumerate(rows):
        if row and len(row) > key_col and normalize_key(str(row[key_col])) == "samplename":
            sample_name_row_idx = idx
            for col_idx in range(key_col + 1, ncols):
                raw = row[col_idx] if col_idx < len(row) else ""
                name = str(raw).strip() if raw is not None else ""
                if not name or name.lower() == "nan":
                    name = f"sample_{col_idx - key_col}"
                else:
                    # Normalise float-looking integers (e.g. "8.0" → "8")
                    try:
                        f = float(name)
                        if f == int(f):
                            name = str(int(f))
                    except (ValueError, TypeError):
                        pass
                sample_names.append(name)
            break

    if not sample_names:
        sample_names = [f"sample_{i}" for i in range(1, ncols - key_col)]

    # Deduplicate sample names
    seen: dict[str, int] = {}
    for i, name in enumerate(sample_names):
        if name in seen:
            seen[name] += 1
            sample_names[i] = f"{name}_{seen[name]}"
        else:
            seen[name] = 1

    # Build one SampleData per data column
    samples: list[SampleData] = []
    for col_idx in range(key_col + 1, ncols):
        sample_data: dict[str, float] = {}
        for row_idx, row in enumerate(rows):
            if sample_name_row_idx is not None and row_idx == sample_name_row_idx:
                continue
            if not row:
                continue
            label = str(row[key_col]).strip() if len(row) > key_col else ""
            if not label or label.lower() == "nan":
                continue
            if normalize_key(label) in HEADER_KEYWORDS:
                continue
            val = _try_float(row[col_idx] if col_idx < len(row) else None)
            if val is None:
                continue
            sample_data[label] = val

        data_col = col_idx - key_col - 1
        col_name = (
            sample_names[data_col]
            if data_col < len(sample_names)
            else f"sample_{col_idx}"
        )
        samples.append(SampleData(name=col_name, data=sample_data))

    return samples, file_warnings


def apply_to_model(data: dict[str, float], model: BulkComposition) -> ImportResult:
    """
    Apply parsed data to the model using tier-based priority resolution.

    Algorithm:
      Pass 0 — Apply simple oxides and LOI (independent of redox systems).
      Pass 1 — For each redox system (iron, carbon, sulfur), walk its tiers
               from SYSTEM_TIERS in declared order. The FIRST tier with any
               present input key wins; every present key in that tier is
               applied (per-DOF, first-alias-wins). Keys in later tiers
               produce a skip-warning.
      Carbon seeding — If carbon Tier A won and no explicit co2ratio key
               was supplied, seed co2_ctot_ratio=1.0 (preserves the
               fixed-speciation default: "CO₂ column = all C is carbonate").
               Lower tiers don't seed
               because the species pair already encodes the ratio.
      Pass 2 — Apply ratio keys last. Explicit ratio always overrides
               whatever ratio the tier produced.
      Volatile-mode — Same logic as before, based on LOI/H2O presence.
    """
    result = ImportResult()
    h2o_set = False
    loi_set = False

    # Normalize input → first-occurrence wins on collision.
    normalized_input: dict[str, tuple[str, float]] = {}
    for original, value in data.items():
        nk = normalize_key(original)
        if nk not in normalized_input:
            normalized_input[nk] = (original, value)

    # Anything not in OXIDE_ALIASES is unrecognised — except reserved
    # snapshot-provenance prefixes (der.*, tchx.*) which are silently
    # tolerated for round-trip parity with the .dat importer.
    # Known v0 aliases produce a "did you mean?" hint in result.warnings.
    for nk, (original, _) in normalized_input.items():
        if nk in OXIDE_ALIASES:
            continue
        if nk.startswith("der.") or nk.startswith("tchx."):
            continue
        result.skipped.append(original)
        if nk in LEGACY_V0_HINTS:
            hint = LEGACY_V0_HINTS[nk]
            result.warnings.append(
                f"Unrecognized key '{original}' — did you mean '{hint}'? "
                f"(v0 alias removed in v1.0)"
            )

    # --- Consistency override: prefer species tier over Tier A when sums match.
    # Rationale: species-level input encodes both total and ratios, whereas
    # Tier A + no ratio drops the redox split.  Only fires when a lower tier
    # is complete (all DOFs present) AND its species sum equals the Tier A
    # total within tolerance.  Matched Tier A keys are silently removed so
    # Pass 1 naturally picks the species tier.
    for system_name, tiers in SYSTEM_TIERS.items():
        override_idx = _consistency_override(system_name, tiers, normalized_input)
        if override_idx is None:
            continue
        for k in _tier_keys(tiers[0]):
            normalized_input.pop(k, None)

    # --- Pass 0: simple oxides + LOI ---
    for nk, (original, value) in normalized_input.items():
        if nk not in OXIDE_ALIASES:
            continue
        system, prop = OXIDE_ALIASES[nk]
        if system == "simple":
            _apply_single(model, system, prop, value, original, result)
            if prop == "H2O":
                h2o_set = True
        elif system == "root":
            _apply_single(model, system, prop, value, original, result)
            if prop == "loi_measured":
                loi_set = True

    # --- Pass 1: per-system tier walk (first-tier-wins) ---
    tier_wins: dict[str, str | None] = {"iron": None, "carbon": None, "sulfur": None}

    for system_name, tiers in SYSTEM_TIERS.items():
        won_idx: int | None = None
        for tier_idx, (tier_name, dof_lists) in enumerate(tiers):
            tier_has_any = any(k in normalized_input for dof in dof_lists for k in dof)
            if not tier_has_any:
                continue
            # Apply this tier: each DOF picks the first alias present.
            for dof in dof_lists:
                for k in dof:
                    if k in normalized_input:
                        original, value = normalized_input[k]
                        sys, prop = OXIDE_ALIASES[k]
                        _apply_single(model, sys, prop, value, original, result)
                        break
            tier_wins[system_name] = tier_name
            won_idx = tier_idx
            break

        # Skip-warnings for any later-tier keys.
        if won_idx is not None:
            for _, dof_lists in tiers[won_idx + 1:]:
                for dof in dof_lists:
                    for k in dof:
                        if k in normalized_input:
                            original = normalized_input[k][0]
                            result.warnings.append(
                                f"'{original}' skipped — higher-priority input data "
                                f"is already loaded for the {system_name} system. "
                                f"Everything is fine."
                            )

    # --- Carbon seeding: preserve fixed-speciation "CO₂ → all carbonate" default ---
    carbon_ratio_aliases = {"c4plusctotalratio", "co2ctotratio"}
    explicit_carbon_ratio = bool(normalized_input.keys() & carbon_ratio_aliases)
    if tier_wins["carbon"] == "A_total_ratio" and not explicit_carbon_ratio:
        model.carbon.co2_ctot_ratio = 1.0

    # --- Pass 2: ratios override last ---
    for nk, (original, value) in normalized_input.items():
        if nk not in RATIO_KEYS or nk not in OXIDE_ALIASES:
            continue
        system, prop = OXIDE_ALIASES[nk]
        _apply_single(model, system, prop, value, original, result)

    # --- Volatile-mode (unchanged) ---
    if loi_set and not h2o_set:
        model._volatile_mode = "h2o_derived"
    elif loi_set and h2o_set:
        model._volatile_mode = "direct"
    else:
        # H2O only, or neither → LOI = H2O + CO2 + SO3
        model._volatile_mode = "loi_derived"

    return result


def _apply_single(
    model: BulkComposition,
    system: str,
    prop: str,
    value: float,
    original_name: str,
    result: ImportResult,
) -> None:
    """
    Apply a single field value to the model.
    
    Args:
        model: The BulkComposition model instance.
        system: One of "simple", "root", "iron", "carbon", "sulfur".
        prop: The property name to set.
        value: The numeric value to assign.
        original_name: Original field name from input (for logging).
        result: ImportResult to record success or error.
    """
    try:
        if system == "simple":
            model.set_oxide_wt(prop, value)
        elif system == "root":
            setattr(model, prop, value)
        else:  # "iron", "carbon", "sulfur"
            subsystem = getattr(model, system)
            setattr(subsystem, prop, value)
        result.applied.append(original_name)
    except Exception as e:
        result.warnings.append(f"Error setting '{original_name}': {e}")


# ---------------------------------------------------------------------------
# Consistency-override helpers (used by apply_to_model Pass 1).
# ---------------------------------------------------------------------------

# Convert any Tier A alias value → elemental wt% of the redox element (Fe/C/S).
# Keys are normalized alias forms; values are (system, multiplier_from_value).
_TIER_A_TO_ELEMENTAL_WT: dict[str, tuple[str, float]] = {
    # Iron: Fe2O3_total_wt → Fe wt%; FeO_total_wt → Fe wt%
    "fe2o3totalwt": ("iron",   2.0 * ELEMENT_MASSES['fe'] / OXIDE_MASSES['fe2o3']),
    "feototalwt":   ("iron",         ELEMENT_MASSES['fe'] / OXIDE_MASSES['feo']),
    # Carbon: C_total_wt → C wt%; CO2_total_wt → C wt%; C_total_ugg → C wt%
    "ctotalwt":     ("carbon",  1.0),
    "co2totalwt":   ("carbon",  ELEMENT_MASSES['c'] / OXIDE_MASSES['co2']),
    "ctotalugg":    ("carbon",  1e-4),
    # Sulfur: S_total_wt → S wt%; SO3_total_wt → S wt%; S_total_ugg → S wt%
    "stotalwt":     ("sulfur",  1.0),
    "so3totalwt":   ("sulfur",  ELEMENT_MASSES['s'] / OXIDE_MASSES['so3']),
    "stotalugg":    ("sulfur",  1e-4),
}

# Convert any lower-tier species alias value → elemental wt% of the redox
# element (Fe/C/S).  Keys are normalized alias forms; values are multipliers.
_SPECIES_TO_ELEMENTAL_WT: dict[str, float] = {
    # Iron Tier B (real oxides) → Fe wt%
    "feowt":       ELEMENT_MASSES['fe'] / OXIDE_MASSES['feo'],
    "fe2o3wt":     2.0 * ELEMENT_MASSES['fe'] / OXIDE_MASSES['fe2o3'],
    # Iron Tier C (elemental wt%) → Fe wt%
    "fe2pluswt":   1.0,
    "fe3pluswt":   1.0,
    # Iron Tier D (elemental ugg) → Fe wt%
    "fe2plusugg":  1e-4,
    "fe3plusugg":  1e-4,
    # Carbon Tier B (species wt%) → C wt%
    "c0wt":        1.0,
    "c4pluswt":    1.0,
    # Carbon Tier C (species ugg) → C wt%
    "c0ugg":       1e-4,
    "c4plusugg":   1e-4,
    # Sulfur Tier B (species wt%) → S wt%
    "s6pluswt":    1.0,
    "s1minuswt":   1.0,
    "s2minuswt":   1.0,
    # Sulfur Tier C (species ugg) → S wt%
    "s6plusugg":   1e-4,
    "s1minusugg":  1e-4,
    "s2minusugg":  1e-4,
}


def _tier_keys(tier: tuple[str, list[list[str]]]) -> list[str]:
    """Flatten a single SYSTEM_TIERS tier into its list of alias keys."""
    return [k for dof in tier[1] for k in dof]


def _tier_a_total_elemental(
    system: str,
    normalized_input: dict[str, tuple[str, float]],
) -> float | None:
    """Return the Tier A total for *system* in elemental wt% (Fe/C/S), or
    ``None`` if no Tier A key is present."""
    tier_a = SYSTEM_TIERS[system][0]
    for k in _tier_keys(tier_a):
        if k in normalized_input:
            sys_name, mult = _TIER_A_TO_ELEMENTAL_WT[k]
            if sys_name != system:
                continue
            _, value = normalized_input[k]
            return value * mult
    return None


def _tier_species_sum_elemental(
    dof_lists: list[list[str]],
    normalized_input: dict[str, tuple[str, float]],
) -> tuple[float, bool]:
    """Return ``(species_sum_wt_element, complete)`` for a lower tier.

    *complete* is True iff every DOF has at least one present alias.
    First-alias-wins within each DOF.  Sum is expressed in elemental wt%
    (Fe/C/S) so it can be compared to :func:`_tier_a_total_elemental`.
    """
    total = 0.0
    complete = True
    for dof in dof_lists:
        picked = False
        for k in dof:
            if k in normalized_input:
                _, value = normalized_input[k]
                total += value * _SPECIES_TO_ELEMENTAL_WT[k]
                picked = True
                break
        if not picked:
            complete = False
    return total, complete


def _consistency_override(
    system: str,
    tiers: list[tuple[str, list[list[str]]]],
    normalized_input: dict[str, tuple[str, float]],
) -> int | None:
    """Return the index of the first complete-and-consistent lower tier, or
    ``None`` if Tier A wins (missing, no complete lower tier, or sums don't
    match within tolerance).

    Tolerance: ``rel_tol=1e-2`` + ``abs_tol=1e-6`` on elemental wt%.
    """
    tier_a_total = _tier_a_total_elemental(system, normalized_input)
    if tier_a_total is None:
        return None
    for idx in range(1, len(tiers)):
        _, dof_lists = tiers[idx]
        species_sum, complete = _tier_species_sum_elemental(dof_lists, normalized_input)
        if not complete:
            continue
        if math.isclose(species_sum, tier_a_total, rel_tol=1e-2, abs_tol=1e-6):
            return idx
    return None
