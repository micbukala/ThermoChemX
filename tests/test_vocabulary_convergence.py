# ThermoChemX — Copyright (C) 2026  Michał Bukała <michal.bukala@csic.es>
# This program is free software: GNU General Public License v3 or later.
# It comes with ABSOLUTELY NO WARRANTY. See LICENSE.txt for details.

"""
Vocabulary convergence test: a CSV using v1.0 keys and a .dat snapshot
re-import through dat_importer produce bit-exact identical SSoT.

Gate 5 (plan): the two live vocabularies converge on one registry.
"""
import pytest

from thermochemx.core.composition import BulkComposition
from thermochemx.core.importer import apply_to_model
from thermochemx.core.exporter import PerplexExporter
from thermochemx.core.dat_importer import parse_dat_snapshot, apply_snapshot_to_model

# ---------------------------------------------------------------------------
# Reference data (v1.0 CSV keys)
# ---------------------------------------------------------------------------

DATA_V1 = {
    "SiO2_wt": 50.00, "TiO2_wt": 1.00, "Al2O3_wt": 14.00,
    "MgO_wt": 6.00,   "CaO_wt": 9.00,  "Na2O_wt": 2.50,
    "K2O_wt": 1.00,   "H2O_wt": 2.00,
    "Fe2O3_total_wt": 10.00, "Fe3plus_Fetotal_ratio": 0.30,
    "C_total_wt": 0.40,      "C4plus_Ctotal_ratio": 0.50,
    "S_total_wt": 0.30,      "S6plus_Stotal_ratio": 0.40,
    "S1minus_Ssulfides_ratio": 0.60,
}

# Same data expressed with canonical SSoT ratio names
DATA_CANONICAL = {
    "SiO2_wt": 50.00, "TiO2_wt": 1.00, "Al2O3_wt": 14.00,
    "MgO_wt": 6.00,   "CaO_wt": 9.00,  "Na2O_wt": 2.50,
    "K2O_wt": 1.00,   "H2O_wt": 2.00,
    "Fe2O3_total_wt": 10.00, "fe3_fetot_ratio": 0.30,
    "C_total_wt": 0.40,      "co2_ctot_ratio": 0.50,
    "S_total_wt": 0.30,      "so3_stot_ratio": 0.40,
    "s1_sred_ratio": 0.60,
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _csv_comp(data: dict) -> BulkComposition:
    comp = BulkComposition()
    apply_to_model(data, comp)
    return comp


def _dat_roundtrip(comp: BulkComposition) -> BulkComposition:
    """Export to .dat snapshot text, then restore to a fresh BulkComposition."""
    snapshot_text = PerplexExporter(comp).generate_snapshot(source_file="convergence_test")
    result = parse_dat_snapshot(snapshot_text)
    new_comp = BulkComposition()
    apply_snapshot_to_model(result, new_comp)
    return new_comp


def _ssot(comp: BulkComposition) -> dict:
    return {
        "_volatile_mode":    comp._volatile_mode,
        "H2O_raw":           comp._simple_oxides["H2O"],
        "loi_measured":      comp.loi_measured,
        "fe2o3_tot_wt":      comp.iron.fe2o3_tot_wt,
        "fe3_fetot_ratio":   comp.iron.fe3_fetot_ratio,
        "c_wt":              comp.carbon.c_wt,
        "co2_ctot_ratio":    comp.carbon.co2_ctot_ratio,
        "s_wt":              comp.sulfur.s_wt,
        "so3_stot_ratio":    comp.sulfur.so3_stot_ratio,
        "s1_sred_ratio":     comp.sulfur.s1_sred_ratio,
    }


def _assert_ssot_equal(orig: dict, recv: dict, label: str) -> None:
    for key in orig:
        o, r = orig[key], recv[key]
        if isinstance(o, float):
            assert o == r, f"{label}: '{key}' diverged: {o} != {r}"
        else:
            assert o == r, f"{label}: '{key}' diverged: {o!r} != {r!r}"


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestCsvToDatConvergence:

    def test_v1_csv_keys_roundtrip(self):
        """CSV with new v1.0 keys → export → .dat re-import → identical SSoT."""
        csv_comp = _csv_comp(DATA_V1)
        dat_comp = _dat_roundtrip(csv_comp)
        _assert_ssot_equal(_ssot(csv_comp), _ssot(dat_comp), "v1_csv_keys")

    def test_canonical_ssot_keys_roundtrip(self):
        """CSV with canonical SSoT ratio names → export → .dat re-import → identical SSoT."""
        csv_comp = _csv_comp(DATA_CANONICAL)
        dat_comp = _dat_roundtrip(csv_comp)
        _assert_ssot_equal(_ssot(csv_comp), _ssot(dat_comp), "canonical_ssot_keys")

    def test_v1_and_canonical_yield_same_ssot(self):
        """New CSV key spelling and canonical SSoT spelling produce identical SSoT."""
        comp_v1  = _csv_comp(DATA_V1)
        comp_can = _csv_comp(DATA_CANONICAL)
        _assert_ssot_equal(_ssot(comp_v1), _ssot(comp_can), "v1_vs_canonical")

    def test_simple_oxides_roundtrip(self):
        """All 12 simple oxides survive export→import bit-exact."""
        csv_comp = _csv_comp(DATA_V1)
        dat_comp = _dat_roundtrip(csv_comp)
        oxides = ["SiO2", "TiO2", "Al2O3", "Cr2O3", "MnO", "MgO",
                  "CaO",  "NiO",  "Na2O",  "K2O",   "P2O5"]
        for ox in oxides:
            v1 = csv_comp.get_oxide_wt(ox)
            v2 = dat_comp.get_oxide_wt(ox)
            assert v1 == v2, f"Oxide '{ox}' diverged: {v1} != {v2}"

    def test_volatile_mode_preserved(self):
        """Volatile mode is preserved through the round-trip."""
        csv_comp = _csv_comp(DATA_V1)
        assert csv_comp._volatile_mode == "loi_derived"
        dat_comp = _dat_roundtrip(csv_comp)
        assert dat_comp._volatile_mode == "loi_derived"


class TestSkippedFieldsInDat:
    """IN_KEY_MAP covers exactly the authoritative in.* fields; der.* ignored."""

    def test_der_keys_tolerated_in_csv(self):
        """Derived keys from snapshot (der.*) are silently ignored, not errors."""
        data = dict(DATA_V1)
        data["der.fe2_oxide_wt"] = 99.0   # derived field — must be ignored
        comp = _csv_comp(data)
        # The der.* key should not crash and should not override the SSoT
        assert comp.iron.fe2_oxide_wt != pytest.approx(99.0)
