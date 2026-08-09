# ThermoChemX — Copyright (C) 2026  Michał Bukała <michal.bukala@csic.es>
# This program is free software: GNU General Public License v3 or later.
# It comes with ABSOLUTELY NO WARRANTY. See LICENSE.txt for details.

"""
Volatile-mode fixture scaffold + Phase D round-trip tests.

Three dedicated fixtures (in tests/regression/fixtures/volatile/) each sit in
exactly one volatile mode so that the Phase D round-trip test exercises all
three reconstruction paths independently.

  vol_loi_derived  —  H2O raw, LOI computed  (H2O + CO2_tot + SO3_tot)
  vol_h2o_derived  —  LOI raw, H2O computed  (LOI - CO2_tot - SO3_tot)
  vol_direct       —  both H2O and LOI raw, deliberately inconsistent

The scaffold section (groups 1-3) verifies mode assignment and raw SSoT values
after CSV import using only the existing importer.

The Phase D section (group 4+) tests the full export→import round-trip:
  import(export(X)).ssot == X.ssot
at the SSoT level for:
  - 9 fixtures (6 original redox-corner + 3 volatile-mode fixtures)
  - covering all three volatile modes (loi_derived, h2o_derived, direct)

Fixture numbers
---------------
  vol_loi_derived:  C=0.40, S=0.30, H2O=2.00
    CO2_wt  ≈ 1.46562  (C × 44.009/12.011)
    SO3_wt  ≈ 0.74906  (S × 80.062/32.065)
    loi_display ≈ 4.21468

  vol_h2o_derived:  C=0.50, S=0.40, LOI=5.00
    CO2_wt  ≈ 1.83203
    SO3_wt  ≈ 0.99875
    H2O_computed ≈ 2.16922

  vol_direct:  C=0.30, S=0.25, H2O=3.00, LOI=8.00 (inconsistent by design)
    CO2_wt  ≈ 1.09922
    SO3_wt  ≈ 0.62422
    loi_derived formula would give LOI ≈ 4.72 ≠ 8.00
    h2o_derived formula would give H2O ≈ 6.28 ≠ 3.00
"""

from __future__ import annotations

import sys
import os
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from thermochemx.core.composition import BulkComposition
from thermochemx.core.importer import parse_file, apply_to_model

VOLATILE_FIXTURES = Path(__file__).parent / "fixtures" / "volatile"


def _load(name: str) -> BulkComposition:
    comp = BulkComposition()
    apply_to_model(parse_file(str(VOLATILE_FIXTURES / f"{name}.csv")), comp)
    return comp


# ---------------------------------------------------------------------------
# Mode assignment
# ---------------------------------------------------------------------------

def test_loi_derived_mode():
    """H2O present, no LOI → loi_derived."""
    assert _load("vol_loi_derived")._volatile_mode == "loi_derived"


def test_h2o_derived_mode():
    """LOI present, no H2O → h2o_derived."""
    assert _load("vol_h2o_derived")._volatile_mode == "h2o_derived"


def test_direct_mode():
    """Both H2O and LOI present → direct."""
    assert _load("vol_direct")._volatile_mode == "direct"


# ---------------------------------------------------------------------------
# Raw SSoT values  (_simple_oxides['H2O'] and loi_measured)
# These are what the Phase-C exporter must serialise as in.H2O / in.LOI.
# ---------------------------------------------------------------------------

def test_loi_derived_raw_ssot():
    comp = _load("vol_loi_derived")
    # H2O=2.00 imported directly into _simple_oxides; loi_measured never touched.
    assert comp._simple_oxides["H2O"] == pytest.approx(2.00, abs=1e-9)
    assert comp.loi_measured           == pytest.approx(0.0,  abs=1e-9)


def test_h2o_derived_raw_ssot():
    comp = _load("vol_h2o_derived")
    # H2O never imported → stays at default 0.0; loi_measured=5.00 set via root.
    assert comp._simple_oxides["H2O"] == pytest.approx(0.0,  abs=1e-9)
    assert comp.loi_measured           == pytest.approx(5.00, abs=1e-9)


def test_direct_raw_ssot():
    comp = _load("vol_direct")
    # Both imported independently; neither is derived from the other.
    assert comp._simple_oxides["H2O"] == pytest.approx(3.00, abs=1e-9)
    assert comp.loi_measured           == pytest.approx(8.00, abs=1e-9)


# ---------------------------------------------------------------------------
# Computed volatile views
# ---------------------------------------------------------------------------

def test_loi_derived_loi_display():
    """loi_derived: loi_display = _simple_oxides['H2O'] + CO2_tot + SO3_tot."""
    comp = _load("vol_loi_derived")
    expected = comp._simple_oxides["H2O"] + comp.carbon.co2_wt + comp.sulfur.so3_wt
    assert comp.loi_display == pytest.approx(expected, abs=1e-9)
    assert comp.loi_display > 4.0  # sanity: ~4.21 with C=0.40, S=0.30, H2O=2.00


def test_h2o_derived_h2o_computed():
    """h2o_derived: get_oxide_wt('H2O') = loi_measured - CO2_tot - SO3_tot."""
    comp = _load("vol_h2o_derived")
    expected = comp.loi_measured - comp.carbon.co2_wt - comp.sulfur.so3_wt
    assert comp.get_oxide_wt("H2O") == pytest.approx(expected, abs=1e-9)
    assert comp.get_oxide_wt("H2O") > 2.0  # sanity: ~2.17 with C=0.50, S=0.40, LOI=5.00


# ---------------------------------------------------------------------------
# direct mode: deliberate inconsistency must be preserved
# ---------------------------------------------------------------------------

def test_direct_inconsistency_preserved():
    """
    vol_direct carries H2O=3.00 and LOI=8.00 that are deliberately inconsistent:
      loi_derived  formula → LOI ≈ 4.72   (≠ 8.00)
      h2o_derived  formula → H2O ≈ 6.28   (≠ 3.00)

    In 'direct' mode neither value may be recomputed from the other.  If either
    assertion fails, a silent recomputation has occurred.
    """
    comp = _load("vol_direct")
    co2 = comp.carbon.co2_wt
    so3 = comp.sulfur.so3_wt

    loi_if_formula = comp._simple_oxides["H2O"] + co2 + so3
    h2o_if_formula = comp.loi_measured - co2 - so3

    assert abs(comp.loi_measured          - loi_if_formula) > 1.0, \
        f"LOI ({comp.loi_measured:.5f}) equals loi_derived formula ({loi_if_formula:.5f}) — silent recompute?"
    assert abs(comp._simple_oxides["H2O"] - h2o_if_formula) > 1.0, \
        f"H2O ({comp._simple_oxides['H2O']:.5f}) equals h2o_derived formula ({h2o_if_formula:.5f}) — silent recompute?"


# ===========================================================================
# Phase D — export→import round-trip (import(export(X)).ssot == X.ssot)
# ===========================================================================

from thermochemx.core.exporter import PerplexExporter
from thermochemx.core.dat_importer import (
    DatImportError, parse_dat_snapshot, parse_dat_snapshots, apply_snapshot_to_model,
)

FIXTURES = Path(__file__).parent / "fixtures"
# in.* uses repr(float) serialisation — float(repr(x)) == x exactly,
# so round-trip comparisons use == (not a tolerance).


def _ssot(comp: BulkComposition) -> dict:
    """Extract all SSoT fields for round-trip comparison."""
    return {
        "volatile_mode":   comp._volatile_mode,
        "simple_oxides":   dict(comp._simple_oxides),
        "loi_measured":    comp.loi_measured,
        "fe2o3_tot_wt":    comp.iron.fe2o3_tot_wt,
        "fe3_fetot_ratio": comp.iron.fe3_fetot_ratio,
        "c_wt":            comp.carbon.c_wt,
        "co2_ctot_ratio":  comp.carbon.co2_ctot_ratio,
        "s_wt":            comp.sulfur.s_wt,
        "so3_stot_ratio":  comp.sulfur.so3_stot_ratio,
        "s1_sred_ratio":   comp.sulfur.s1_sred_ratio,
        "sample_name":     comp.sample_name,
    }


def _assert_ssot_equal(orig: dict, recv: dict, label: str) -> None:
    """
    Assert two SSoT snapshots are exactly equal.

    The in.* section uses repr(float) serialisation which guarantees
    float(repr(x)) == x bit-for-bit, so the round-trip residual must be
    exactly zero -- not just within a tolerance.
    """
    assert orig["volatile_mode"] == recv["volatile_mode"], (
        f"{label}: volatile_mode: {orig['volatile_mode']!r} != {recv['volatile_mode']!r}"
    )
    for ox in orig["simple_oxides"]:
        a, b = orig["simple_oxides"][ox], recv["simple_oxides"][ox]
        assert a == b, f"{label}: simple_oxides[{ox!r}]: {a!r} != {b!r}"
    assert orig["loi_measured"]    == recv["loi_measured"],    f"{label}: loi_measured"
    assert orig["fe2o3_tot_wt"]    == recv["fe2o3_tot_wt"],    f"{label}: fe2o3_tot_wt"
    assert orig["fe3_fetot_ratio"] == recv["fe3_fetot_ratio"], f"{label}: fe3_fetot_ratio"
    assert orig["c_wt"]            == recv["c_wt"],            f"{label}: c_wt"
    assert orig["co2_ctot_ratio"]  == recv["co2_ctot_ratio"],  f"{label}: co2_ctot_ratio"
    assert orig["s_wt"]            == recv["s_wt"],            f"{label}: s_wt"
    assert orig["so3_stot_ratio"]  == recv["so3_stot_ratio"],  f"{label}: so3_stot_ratio"
    assert orig["s1_sred_ratio"]   == recv["s1_sred_ratio"],   f"{label}: s1_sred_ratio"
    assert orig["sample_name"]     == recv["sample_name"],     f"{label}: sample_name"


def _round_trip(comp: BulkComposition, source_file: str = "") -> BulkComposition:
    """Export comp to .dat snapshot text, then reimport into a fresh BulkComposition."""
    snapshot_text = PerplexExporter(comp).generate_snapshot(source_file=source_file)
    result = parse_dat_snapshot(snapshot_text)
    new_comp = BulkComposition()
    apply_snapshot_to_model(result, new_comp)
    return new_comp


def _load_fixture(csv_path: Path) -> BulkComposition:
    comp = BulkComposition()
    apply_to_model(parse_file(str(csv_path)), comp)
    return comp


# ---------------------------------------------------------------------------
# GROUP 4 — volatile-mode round-trips (all three modes)
# ---------------------------------------------------------------------------

def test_roundtrip_loi_derived(qapp):
    """loi_derived: raw H2O and zero loi_measured survive export→import."""
    comp = _load("vol_loi_derived")
    orig = _ssot(comp)
    recv = _ssot(_round_trip(comp, source_file="vol_loi_derived"))
    _assert_ssot_equal(orig, recv, "vol_loi_derived")

    # Verify the computed view also matches after round-trip
    recovered = _round_trip(comp, source_file="vol_loi_derived")
    expected_loi = recovered._simple_oxides["H2O"] + recovered.carbon.co2_wt + recovered.sulfur.so3_wt
    assert recovered.loi_display == pytest.approx(expected_loi, abs=1e-9)


def test_roundtrip_h2o_derived(qapp):
    """h2o_derived: zero raw H2O and raw loi_measured survive; computed H2O reappears."""
    comp = _load("vol_h2o_derived")
    orig = _ssot(comp)
    recv = _ssot(_round_trip(comp, source_file="vol_h2o_derived"))
    _assert_ssot_equal(orig, recv, "vol_h2o_derived")

    # Verify computed H2O reappears correctly after round-trip
    recovered = _round_trip(comp, source_file="vol_h2o_derived")
    expected_h2o = recovered.loi_measured - recovered.carbon.co2_wt - recovered.sulfur.so3_wt
    assert recovered.get_oxide_wt("H2O") == pytest.approx(expected_h2o, abs=1e-9)


def test_roundtrip_direct(qapp):
    """direct: both H2O and LOI survive independently; inconsistency is preserved."""
    comp = _load("vol_direct")
    orig = _ssot(comp)
    recv = _ssot(_round_trip(comp, source_file="vol_direct"))
    _assert_ssot_equal(orig, recv, "vol_direct")

    # Both raw values must still be mutually inconsistent after round-trip
    recovered = _round_trip(comp, source_file="vol_direct")
    co2 = recovered.carbon.co2_wt
    so3 = recovered.sulfur.so3_wt
    loi_formula = recovered._simple_oxides["H2O"] + co2 + so3
    h2o_formula = recovered.loi_measured - co2 - so3
    assert abs(recovered.loi_measured          - loi_formula) > 1.0
    assert abs(recovered._simple_oxides["H2O"] - h2o_formula) > 1.0


def test_roundtrip_h2o_derived_sulfidic(qapp):
    """
    Intersection test: h2o_derived mode with active sulfate + sulfide.

    SO3 participates in BOTH the volatile budget (H2O = LOI - CO2 - SO3)
    and the redox budget (sulfate O2 term, phantom-O from sulfide).
    This is the one place the two orthogonal logics share a number.

    Fixture (vol_h2o_derived_sulfidic.csv):
      LOI=6.00 wt% (raw),  C=0.50 wt% (co2_ratio=0.50),  S=0.60 wt% (so3_ratio=0.40, s1_ratio=0.60)
      CO2_tot ≈ 1.832 wt%,  SO3_tot ≈ 1.498 wt%
      H2O_derived = 6.00 − CO2_tot − SO3_tot ≈ 2.670 wt%
      phantom-O from S¹⁻ + S²⁻ ≈ 0.126 wt%

    With repr() serialisation all SSoT scalars round-trip exactly (residual = 0).
    The computed H2O must also reappear correctly after round-trip since it
    depends on the now-exact loi_measured, c_wt, co2_ctot_ratio, s_wt, so3_stot_ratio.
    """
    comp = _load("vol_h2o_derived_sulfidic")
    assert comp._volatile_mode == "h2o_derived"
    assert comp.sulfur.s1_wt > 0, "fixture must have S1- for phantom-O"
    assert comp.sulfur.s2_wt > 0, "fixture must have S2- for phantom-O"
    assert comp.sulfur.s6_wt > 0, "fixture must have sulfate (SO3 in volatile budget)"

    orig = _ssot(comp)
    recovered = _round_trip(comp, source_file="vol_h2o_derived_sulfidic")
    recv = _ssot(recovered)
    _assert_ssot_equal(orig, recv, "vol_h2o_derived_sulfidic")

    # Verify the computed H2O reappears exactly from the recovered SSoT
    expected_h2o = recovered.loi_measured - recovered.carbon.co2_wt - recovered.sulfur.so3_wt
    assert recovered.get_oxide_wt("H2O") == pytest.approx(expected_h2o, abs=1e-12)


# ---------------------------------------------------------------------------
# GROUP 5 — redox-corner fixtures (all loi_derived; test Fe/C/S SSoT round-trip)
# ---------------------------------------------------------------------------

REDOX_CASES = sorted(FIXTURES.glob("*.csv"))


@pytest.mark.parametrize("csv", REDOX_CASES, ids=lambda p: p.stem)
def test_roundtrip_redox_fixture(csv, qapp):
    """
    import(export(X)).ssot == X.ssot for every redox-corner fixture.

    These are all loi_derived; the main test here is Fe/C/S SSoT fidelity.
    """
    comp = _load_fixture(csv)
    orig = _ssot(comp)
    recv = _ssot(_round_trip(comp, source_file=csv.stem))
    _assert_ssot_equal(orig, recv, csv.stem)


# ---------------------------------------------------------------------------
# GROUP 6 — parser correctness: multi-block and full .dat
# ---------------------------------------------------------------------------

def test_parse_full_dat_file(qapp):
    """parse_dat_snapshots finds the snapshot block inside a full .dat file."""
    comp = _load("vol_loi_derived")
    full_dat = PerplexExporter(comp).generate_perplex_data()
    results = parse_dat_snapshots(full_dat)
    assert len(results) == 1
    new_comp = BulkComposition()
    apply_snapshot_to_model(results[0], new_comp)
    _assert_ssot_equal(_ssot(comp), _ssot(new_comp), "full_dat")


def test_parse_multi_block(qapp):
    """parse_dat_snapshots returns one result per snapshot block in a multi-block text."""
    comp1 = _load_fixture(FIXTURES / "mixed.csv")
    comp2 = _load_fixture(FIXTURES / "oxidised.csv")
    snap1 = PerplexExporter(comp1).generate_snapshot()
    snap2 = PerplexExporter(comp2).generate_snapshot()
    multi_text = snap1 + "\n\n" + snap2
    results = parse_dat_snapshots(multi_text)
    assert len(results) == 2
    for result, original in zip(results, [comp1, comp2]):
        new_comp = BulkComposition()
        apply_snapshot_to_model(result, new_comp)
        _assert_ssot_equal(_ssot(original), _ssot(new_comp), "multi_block")


# ---------------------------------------------------------------------------
# GROUP 7 — error handling: malformed blocks
# ---------------------------------------------------------------------------

def test_parse_empty_text_raises():
    """parse_dat_snapshot raises DatImportError when no snapshot block is found."""
    with pytest.raises(DatImportError, match="No 'begin composition snapshot'"):
        parse_dat_snapshot("some random text with no snapshot")


def test_parse_missing_volatile_mode_raises():
    """parse_dat_snapshot raises DatImportError when in.volatile_mode is absent."""
    bad = (
        "begin composition snapshot\n"
        "tchx.format_version     1\n"
        "in.SiO2                 50.00000  # wt%\n"
        "end composition snapshot"
    )
    with pytest.raises(DatImportError, match="in.volatile_mode"):
        parse_dat_snapshot(bad)


def test_parse_unsupported_version_raises():
    """parse_dat_snapshot raises DatImportError for unsupported format_version."""
    bad = (
        "begin composition snapshot\n"
        "tchx.format_version     99\n"
        "in.volatile_mode        loi_derived\n"
        "end composition snapshot"
    )
    with pytest.raises(DatImportError, match="format_version"):
        parse_dat_snapshot(bad)


def test_parse_unknown_der_keys_tolerated():
    """Unknown der.* keys in a future-format snapshot are silently ignored."""
    text = (
        "begin composition snapshot\n"
        "tchx.format_version     1\n"
        "in.volatile_mode        loi_derived\n"
        "in.SiO2                 50.00000\n"
        "der.future_unknown_key  42.0\n"
        "tchx.future_meta        some_value\n"
        "end composition snapshot\n"
    )
    result = parse_dat_snapshot(text)   # must not raise
    assert result.format_version == 1
    assert result.data["in.volatile_mode"] == "loi_derived"
