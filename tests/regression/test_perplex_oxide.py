# ThermoChemX — Copyright (C) 2026  Michał Bukała <michal.bukala@csic.es>
# This program is free software: GNU General Public License v3 or later.
# It comes with ABSOLUTELY NO WARRANTY. See LICENSE.txt for details.

"""
Phase 2 gate tests — Perple_X oxide-basis adapter (FeOt + excess O₂).

Test groups:
  1. test_roundtrip_mass_balance — closure holds for ALL fixtures incl. negative-O
  2. test_element_balance        — oxide back-transform reproduces element mol/kg
  3. test_fe_redox_roundtrip     — FeOt+O₂ round-trip recovers Fe³⁺/ΣFe
  4. Negative-O export           — cap fires, corrective warning, snapshot flag, cross-basis check
  5. test_phantom_o_consistency  — sulfidic fixtures, no double-counting
  6. Registry / policy checks
  7. rows() / table_headers()
"""

from __future__ import annotations

import re
import sys
import os
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from thermochemx.core.composition import BulkComposition
from thermochemx.core.importer import parse_file, apply_to_model
from thermochemx.core.recalc.core import build_recalc_result
from thermochemx.core.recalc.representation import (
    to_perplex_oxide,
    cap_at_zero,
    OXIDE_KEY_ORDER,
    O2_PER_OXIDE_COMPONENT,
)
from thermochemx.core.targets.perplex_oxide import PerplexOxideAdapter
from thermochemx.core.targets.perplex_element import PerplexElementAdapter
from thermochemx.core.targets.registry import get_adapter

FIXTURES = Path(__file__).parent / "fixtures"
ROUNDTRIP_TOL  = 1e-9
ELEMENT_TOL    = 1e-9
FE_REDOX_TOL   = 1e-6

ALL_FIXTURES      = sorted(FIXTURES.glob("*.csv"))
SULFIDIC_FIXTURES = ["sulfidic_pyrite", "sulfidic_pyrrhotite", "mixed"]


def build_composition(csv_path: Path) -> BulkComposition:
    comp = BulkComposition()
    apply_to_model(parse_file(str(csv_path)), comp)
    return comp


# ---------------------------------------------------------------------------
# 1. Round-trip mass balance (incl. negative-O fixture)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("csv", ALL_FIXTURES, ids=lambda p: p.stem)
def test_roundtrip_mass_balance(csv, qapp):
    """Σ(oxide_mol × O₂/formula_unit) == total_oxygen × 1000/denom  (±1e-9)."""
    comp   = build_composition(csv)
    result = build_recalc_result(comp, csv.stem)

    oxide_mol_kg, excess_o2, _warnings, _neg = to_perplex_oxide(result)

    # The O₂ column holds the true (possibly negative) excess value.
    total_encoded = sum(
        oxide_mol_kg[k] * O2_PER_OXIDE_COMPONENT[k]
        for k in OXIDE_KEY_ORDER
    )
    expected = result.total_oxygen * 1000.0 / result.denom

    assert abs(total_encoded - expected) < ROUNDTRIP_TOL, (
        f"{csv.stem}: round-trip error = {abs(total_encoded - expected):.2e}  "
        f"(O₂ = {excess_o2:.6f} mol/kg, tol {ROUNDTRIP_TOL:.0e})"
    )


# ---------------------------------------------------------------------------
# 2. Element balance
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("csv", ALL_FIXTURES, ids=lambda p: p.stem)
def test_element_balance(csv, qapp):
    """Oxide back-transform reproduces element mol/kg within 1e-9."""
    comp   = build_composition(csv)
    result = build_recalc_result(comp, csv.stem)
    factor = 1000.0 / result.denom

    ox, _excess, _w, _neg = to_perplex_oxide(result)
    em = result.element_moles

    checks = {
        "Si":  (ox["SiO2"],        em["Si"]  * factor),
        "Ti":  (ox["TiO2"],        em["Ti"]  * factor),
        "Al":  (ox["Al2O3"] * 2.0, em["Al"]  * factor),
        "Cr":  (ox["Cr2O3"] * 2.0, em["Cr"]  * factor),
        "Fe":  (ox["FeO"],         em["Fe"]  * factor),
        "Mn":  (ox["MnO"],         em["Mn"]  * factor),
        "Mg":  (ox["MgO"],         em["Mg"]  * factor),
        "Ni":  (ox["NiO"],         em["Ni"]  * factor),
        "Ca":  (ox["CaO"],         em["Ca"]  * factor),
        "Na":  (ox["Na2O"] * 2.0,  em["Na"]  * factor),
        "K":   (ox["K2O"]  * 2.0,  em["K"]   * factor),
        "P":   (ox["P2O5"] * 2.0,  em["P"]   * factor),
        "H2":  (ox["H2O"],         em["H2"]  * factor),
        "C":   (ox["CO2"],         em["C"]   * factor),
        "S2":  (ox["S2"] * 2.0,    em["S"]   * factor),
    }
    for elem, (got, expected) in checks.items():
        assert abs(got - expected) < ELEMENT_TOL, (
            f"{csv.stem}: {elem} error {abs(got - expected):.2e}"
        )


# ---------------------------------------------------------------------------
# 3. Fe-redox round-trip
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("fe3_ratio", [0.0, 0.25, 0.5, 0.75, 1.0])
def test_fe_redox_roundtrip(fe3_ratio, qapp):
    """Encode → decode Fe³⁺/ΣFe via FeOt+O₂ (±1e-6)."""
    csv  = FIXTURES / "oxidised.csv"
    comp = build_composition(csv)
    comp.iron.fe3_fetot_ratio = fe3_ratio
    result = build_recalc_result(comp, "roundtrip_fe")
    factor = 1000.0 / result.denom

    ox, excess_o2, _w, _neg = to_perplex_oxide(result)

    n_Fe  = result.element_moles["Fe"] * factor
    n_C   = result.element_moles["C"]  * factor
    n_S   = result.element_moles["S"]  * factor
    n_C0  = n_C * (1.0 - result.co2_ctot)
    n_S6  = n_S * result.so3_stot
    n_Sred = n_S * (1.0 - result.so3_stot)
    n_S1  = n_Sred * result.s1_sred
    n_S2  = n_Sred * (1.0 - result.s1_sred)

    o2_fe = excess_o2 - (-n_C0 + 1.5 * n_S6 - 0.5 * n_S2 - 0.25 * n_S1)
    decoded = o2_fe / (0.25 * n_Fe) if n_Fe > 0 else 0.0
    assert abs(decoded - fe3_ratio) < FE_REDOX_TOL, (
        f"fe3_ratio encoded={fe3_ratio}, decoded={decoded:.8f}"
    )


# ---------------------------------------------------------------------------
# 4a. Negative-O export: reduced_graphitic triggers cap, corrective warning, snapshot flag
# ---------------------------------------------------------------------------

def test_negative_o_export_value(qapp):
    """reduced_graphitic: to_perplex_oxide returns true negative O₂ (transform never caps)."""
    comp   = build_composition(FIXTURES / "reduced_graphitic.csv")
    result = build_recalc_result(comp, "reduced_graphitic")

    ox, excess_o2, warnings, o2_is_negative = to_perplex_oxide(result)

    assert o2_is_negative
    assert excess_o2 < 0.0
    assert ox["O2"] < 0.0
    assert ox["O2"] == excess_o2
    assert len(warnings) == 1
    # Informational, not corrective
    assert "negative" in warnings[0].lower() or "database" in warnings[0].lower()
    assert "capped" not in warnings[0].lower()


def test_negative_o_closure_holds(qapp):
    """Closure holds even when excess_O₂ < 0."""
    comp   = build_composition(FIXTURES / "reduced_graphitic.csv")
    result = build_recalc_result(comp, "reduced_graphitic")

    ox, excess_o2, _w, o2_is_negative = to_perplex_oxide(result)
    assert o2_is_negative

    total_encoded = sum(ox[k] * O2_PER_OXIDE_COMPONENT[k] for k in OXIDE_KEY_ORDER)
    expected = result.total_oxygen * 1000.0 / result.denom
    assert abs(total_encoded - expected) < ROUNDTRIP_TOL, (
        f"Closure error with negative O₂: {abs(total_encoded - expected):.2e}"
    )


def test_negative_o_snapshot_keys(qapp):
    """Provenance keys oxide_o2_capped / oxide_o2_value_molkg in snapshot; no stale negative flag."""
    comp   = build_composition(FIXTURES / "reduced_graphitic.csv")
    result = build_recalc_result(comp, "reduced_graphitic")
    rendered, warnings = PerplexOxideAdapter().render(result)

    assert len(warnings) == 1
    assert "oxide_o2_capped" in rendered
    assert "oxide_o2_value_molkg" in rendered
    assert "oxide_o2_negative" not in rendered
    assert "oxide_o2_precap" not in rendered


def test_negative_o_component_line(qapp):
    """After capping, an explicit O2 = 0 component line is present (Perple_X requires it)."""
    comp   = build_composition(FIXTURES / "reduced_graphitic.csv")
    result = build_recalc_result(comp, "reduced_graphitic")
    rendered, _ = PerplexOxideAdapter().render(result)

    o2_lines = [ln for ln in rendered.splitlines() if ln.startswith("O2")]
    assert len(o2_lines) == 1, f"Expected one explicit O2=0 line after cap, got: {o2_lines}"
    val = float(o2_lines[0].split()[2])
    assert val == 0.0, f"Expected O2=0.0 after cap, got {val}"
    assert "-" not in o2_lines[0], "O2 value should not be negative after cap"


def test_negative_o_file_still_written(qapp, tmp_path):
    """export_to_file() writes the file even when the cap fires; warning is in result."""
    comp   = build_composition(FIXTURES / "reduced_graphitic.csv")
    result = build_recalc_result(comp, "reduced_graphitic")
    out_path = tmp_path / "reduced_graphitic_perplex_oxide.dat"

    er = PerplexOxideAdapter().export_to_file(result, str(out_path), "reduced_graphitic")

    assert out_path.exists(), "File was not written when cap fired"
    assert len(er.warnings) == 1, f"Expected one warning, got: {er.warnings}"
    assert "capped" in er.warnings[0].lower() or "element" in er.warnings[0].lower()


# ---------------------------------------------------------------------------
# 4b. Graphite + high Fe³⁺ → excess_O₂ ≥ 0, no warning
# ---------------------------------------------------------------------------

def test_graphitic_positive_o(qapp):
    """graphitic_oxidised.csv: graphite present, Fe³⁺ high → O₂ ≥ 0."""
    comp   = build_composition(FIXTURES / "graphitic_oxidised.csv")
    result = build_recalc_result(comp, "graphitic_oxidised")

    ox, excess_o2, warnings, o2_is_negative = to_perplex_oxide(result)

    assert not o2_is_negative, f"Expected O₂ ≥ 0, got {excess_o2:.6f}"
    assert excess_o2 >= 0.0
    assert len(warnings) == 0


def test_graphitic_positive_o_adapter(qapp):
    """graphitic_oxidised renders without warning via PerplexOxideAdapter."""
    comp   = build_composition(FIXTURES / "graphitic_oxidised.csv")
    result = build_recalc_result(comp, "graphitic_oxidised")
    rendered, warnings = PerplexOxideAdapter().render(result)

    assert not warnings
    assert "oxide_o2_negative" not in rendered


# ---------------------------------------------------------------------------
# 4c. cap_at_zero direct test
# ---------------------------------------------------------------------------

def test_cap_at_zero_negative(qapp):
    """cap_at_zero clamps to 0 with the corrective (not informational) warning."""
    val, flag, msg = cap_at_zero(-1.5)
    assert val == 0.0
    assert flag is True
    assert len(msg) > 0
    assert "capped" in msg.lower() or "element" in msg.lower()
    assert "database" not in msg.lower()


def test_cap_at_zero_non_negative(qapp):
    """cap_at_zero leaves non-negative values unchanged."""
    for v in [0.0, 1.23, 0.001]:
        val, flag, msg = cap_at_zero(v)
        assert val == v
        assert flag is False
        assert msg == ""


# ---------------------------------------------------------------------------
# 4d. Element / Theriak adapters unaffected by negative-O fixture
# ---------------------------------------------------------------------------

def test_negative_o_element_unaffected(qapp):
    """reduced_graphitic via perplex_element: O₂ > 0, no warning, no oxide cap keys."""
    comp   = build_composition(FIXTURES / "reduced_graphitic.csv")
    result = build_recalc_result(comp, "reduced_graphitic")
    rendered, warnings = PerplexElementAdapter().render(result)

    assert not warnings
    assert result.total_oxygen * 1000.0 / result.denom > 0.0
    assert "oxide_o2_capped" not in rendered
    assert "oxide_o2_negative" not in rendered



# ---------------------------------------------------------------------------
# 5. Phantom-O consistency
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name", SULFIDIC_FIXTURES)
def test_phantom_o_consistency(name, qapp):
    """Sulfidic fixture: O budget consistent with total_oxygen."""
    comp   = build_composition(FIXTURES / f"{name}.csv")
    result = build_recalc_result(comp, name)

    assert comp.phantom_o_from_sulfide_wt > 0.0

    ox, _e, _w, _n = to_perplex_oxide(result)
    total_encoded = sum(ox[k] * O2_PER_OXIDE_COMPONENT[k] for k in OXIDE_KEY_ORDER)
    expected = result.total_oxygen * 1000.0 / result.denom

    assert abs(total_encoded - expected) < ROUNDTRIP_TOL, (
        f"{name}: error = {abs(total_encoded - expected):.2e}"
    )


# ---------------------------------------------------------------------------
# 6. Registry / policy
# ---------------------------------------------------------------------------

def test_registry_lookup_oxide(qapp):
    assert isinstance(get_adapter("perplex_oxide"), PerplexOxideAdapter)


def test_registry_lookup_element(qapp):
    assert isinstance(get_adapter("perplex_element"), PerplexElementAdapter)


def test_list_targets_includes_oxide(qapp):
    from thermochemx.core.targets.registry import list_targets
    targets = list_targets()
    assert "perplex_oxide" in targets
    assert "perplex_element" in targets
    assert "theriak" not in targets


def test_o2_cap_policy_attributes(qapp):
    assert get_adapter("perplex_element").o2_cap_policy == "allow_negative"
    assert get_adapter("perplex_oxide").o2_cap_policy   == "cap_at_zero"


# ---------------------------------------------------------------------------
# 7. rows() / table_headers()
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("csv", ALL_FIXTURES, ids=lambda p: p.stem)
def test_rows_returns_16_entries(csv, qapp):
    """Every adapter.rows() returns exactly 16 (label, value) pairs."""
    comp   = build_composition(csv)
    result = build_recalc_result(comp, csv.stem)

    for name in ["perplex_element", "perplex_oxide"]:
        adapter = get_adapter(name)
        rows = adapter.rows(result)
        assert len(rows) == 16, f"{name}/{csv.stem}: {len(rows)} rows"
        for label, val in rows:
            assert isinstance(label, str)
            assert isinstance(val, (int, float))


def test_table_headers_return_two_strings(qapp):
    """table_headers() returns a 2-tuple of strings for all adapters."""
    for name in ["perplex_element", "perplex_oxide"]:
        h0, h1 = get_adapter(name).table_headers()
        assert isinstance(h0, str) and isinstance(h1, str)
