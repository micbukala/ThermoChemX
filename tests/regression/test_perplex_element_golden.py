# ThermoChemX — Copyright (C) 2026  Michał Bukała <michal.bukala@csic.es>
# This program is free software: GNU General Public License v3 or later.
# It comes with ABSOLUTELY NO WARRANTY. See LICENSE.txt for details.

"""
Regression lock for the Perple_X element-basis exporter.

Phase C structure — three test groups, parametrised over 6 redox-corner fixtures:

  GROUP 1 — permanent component-list lock (never regenerated):
    test_component_list_permanent_lock  — extracts the thermodynamic component
        list block from fresh output, asserts byte-for-byte identity against
        the frozen golden in golden/{stem}_components.dat.  This is Rule-1:
        the Perple_X copy-paste block may NEVER change.

  GROUP 2 — versioned snapshot lock (regenerated deliberately per phase):
    test_snapshot_v1  — extracts the composition snapshot block from fresh
        output (with fixed UTC and source_file), asserts byte-for-byte identity
        against golden/{stem}_snapshot.dat.  Regenerate with _generate_golden.py
        whenever the format changes on purpose.

  GROUP 3 — numeric quality:
    test_mol_kg_within_tolerance  — each mol/kg value within 1e-9 (absolute).
    test_mass_closure             — model_mass_redox_corrected == 1000.0 g/kg.

Golden files:
    golden/{stem}_components.dat  — permanent component-list block
    golden/{stem}_snapshot.dat    — versioned snapshot block
    golden/{stem}.json            — mol/kg + redox-ratio numerics
"""

from __future__ import annotations

import json
import sys
import os
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from thermochemx.core.composition import BulkComposition
from thermochemx.core.importer import parse_file, apply_to_model
from thermochemx.core.exporter import PerplexExporter

FIXTURES = Path(__file__).parent / "fixtures"
GOLDEN   = Path(__file__).parent / "golden"
ATOL     = 1e-9


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def build_composition(csv_path: Path) -> BulkComposition:
    """Load a fixture CSV through the real importer into a fresh BulkComposition."""
    comp = BulkComposition()
    apply_to_model(parse_file(str(csv_path)), comp)
    return comp


def _extract_block(text: str, begin_marker: str, end_marker: str) -> str:
    """Return the substring from begin_marker through the end of end_marker's line."""
    b = text.find(begin_marker)
    e = text.find(end_marker, b)
    if b == -1 or e == -1:
        raise ValueError(f"Block markers not found: {begin_marker!r} / {end_marker!r}")
    e_end = text.find("\n", e)
    return text[b: len(text) if e_end == -1 else e_end]


def _capture(comp: BulkComposition) -> dict:
    """Snapshot the key calculated quantities for the golden JSON."""
    m = comp.model
    return {
        "all_mol_kg": dict(m.all_mol_kg),
        "o2_mol_kg": m.o2_mol_kg,
        "total_model": comp.total_model,
        "total_model_redox_corrected": comp.total_model_redox_corrected,
        "phantom_o_from_sulfide_wt": comp.phantom_o_from_sulfide_wt,
        "model_mass_redox_corrected": comp.model_mass_redox_corrected,
        "fe3_fetot_ratio": comp.iron.fe3_fetot_ratio,
        "co2_ctot_ratio": comp.carbon.co2_ctot_ratio,
        "so3_stot_ratio": comp.sulfur.so3_stot_ratio,
        "s1_sred_ratio": comp.sulfur.s1_sred_ratio,
    }


# ---------------------------------------------------------------------------
# Parametrisation: one id per fixture CSV (top-level only; volatile/ excluded)
# ---------------------------------------------------------------------------

CASES = sorted(FIXTURES.glob("*.csv"))


# ---------------------------------------------------------------------------
# GROUP 1 — permanent component-list lock
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("csv", CASES, ids=lambda p: p.stem)
def test_component_list_permanent_lock(csv, qapp):
    """
    The thermodynamic component list block must be byte-for-byte identical to
    the frozen golden.  This lock is PERMANENT — regenerating it means a
    physics change and must be treated as a breaking change.
    """
    golden_path = GOLDEN / f"{csv.stem}_components.dat"
    if not golden_path.exists():
        pytest.skip(f"Component-list golden not yet generated: {golden_path.name}")

    comp = build_composition(csv)
    got = _extract_block(
        PerplexExporter(comp).generate_component_block(),
        "begin thermodynamic component list",
        "end thermodynamic component list",
    )
    expected = golden_path.read_text(encoding="utf-8")
    assert got == expected, (
        f"{csv.stem}: component-list block differs from permanent golden.\n"
        "This is a PHYSICS change — investigate before proceeding."
    )


# ---------------------------------------------------------------------------
# GROUP 2 — versioned snapshot lock (format v1)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("csv", CASES, ids=lambda p: p.stem)
def test_snapshot_v1(csv, qapp):
    """
    The composition snapshot block (format v1) must match the versioned golden.
    Regenerate with _generate_golden.py after an intentional format change.
    """
    golden_path = GOLDEN / f"{csv.stem}_snapshot.dat"
    if not golden_path.exists():
        pytest.skip(f"Snapshot golden not yet generated: {golden_path.name}")

    comp = build_composition(csv)
    got = PerplexExporter(comp).generate_snapshot(
        source_file=csv.stem,
    )
    expected = golden_path.read_text(encoding="utf-8")
    assert got == expected, (
        f"{csv.stem}: snapshot block differs from golden.\n"
        "Run _generate_golden.py to regenerate if the format change is intentional."
    )


# ---------------------------------------------------------------------------
# GROUP 3 — numeric quality
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("csv", CASES, ids=lambda p: p.stem)
def test_mol_kg_within_tolerance(csv, qapp):
    """Every mol/kg value must match the golden within 1e-9 (absolute)."""
    golden_path = GOLDEN / f"{csv.stem}.json"
    if not golden_path.exists():
        pytest.skip(f"Golden file not yet generated: {golden_path}")
    got = _capture(build_composition(csv))
    golden = json.loads(golden_path.read_text(encoding="utf-8"))
    for k, expected_v in golden["all_mol_kg"].items():
        got_v = got["all_mol_kg"][k]
        assert abs(got_v - expected_v) <= ATOL, (
            f"{csv.stem}: mol/kg for '{k}' differs by "
            f"{abs(got_v - expected_v):.3e} (tol={ATOL})"
        )
    assert abs(got["model_mass_redox_corrected"] - golden["model_mass_redox_corrected"]) <= 1e-6, (
        f"{csv.stem}: model_mass_redox_corrected drift"
    )


@pytest.mark.parametrize("csv", CASES, ids=lambda p: p.stem)
def test_mass_closure(csv, qapp):
    """Σ(mol_i/kg × M_i) must equal 1000.0 g/kg within 1e-6."""
    comp = build_composition(csv)
    if comp.total_model_redox_corrected <= 0:
        pytest.skip("Degenerate: total_model_redox_corrected <= 0")
    mass = comp.model_mass_redox_corrected
    assert abs(mass - 1000.0) <= 1e-6, (
        f"{csv.stem}: mass closure = {mass:.6f} g/kg (expected 1000.0)"
    )
