# ThermoChemX — Copyright (C) 2026  Michał Bukała <michal.bukala@csic.es>
# This program is free software: GNU General Public License v3 or later.
# It comes with ABSOLUTELY NO WARRANTY. See LICENSE.txt for details.

"""
Negative tests: removed v0 CSV alias keys are rejected with a clear
"unrecognized key" error (populating result.skipped + a hint warning),
NOT silently mis-parsed.

Gate 4 (plan): old v0-key CSV fails with a clear unrecognized-key error.
"""
import pytest

from thermochemx.core.importer import apply_to_model
from thermochemx.core.composition import BulkComposition

TOL = 1e-9

def _import(data):
    m = BulkComposition()
    r = apply_to_model(data, m)
    return m, r

class TestIronV0Rejected:

    def test_fe2o3t_rejected(self):
        """v0 key 'Fe2O3t' must land in skipped, not set the SSoT."""
        m, r = _import({"Fe2O3t": 8.0})
        assert m.iron.fe2o3_tot_wt == pytest.approx(0.0, abs=TOL)
        assert any("Fe2O3t" in s for s in r.skipped)

    def test_fe3_ratio_rejected(self):
        """v0 key 'fe3_ratio' must land in skipped."""
        m, r = _import({"fe3_ratio": 0.25})
        # ratio stays at default
        assert m.iron.fe3_fetot_ratio == pytest.approx(0.0, abs=TOL)
        assert any("fe3_ratio" in s for s in r.skipped)

    def test_bare_feo_rejected(self):
        """v0 bare 'FeO' (without _wt) must land in skipped."""
        m, r = _import({"FeO": 8.0})
        assert m.iron.fe2_oxide_wt == pytest.approx(0.0, abs=TOL)
        assert any("FeO" in s for s in r.skipped)

    def test_fe_ugg_v0_rejected(self):
        """v0 keys 'Fe2_ugg', 'Fe3_ugg' (without 'plus') must be skipped."""
        m, r = _import({"Fe2_ugg": 63800, "Fe3_ugg": 16100})
        assert m.iron.fe2o3_tot_wt == pytest.approx(0.0, abs=TOL)
        assert any("Fe2_ugg" in s for s in r.skipped)
        assert any("Fe3_ugg" in s for s in r.skipped)

    def test_hint_present_for_fe2o3t(self):
        """A v1.0 hint 'Fe2O3_total_wt' appears in the warning text."""
        _, r = _import({"Fe2O3t": 8.0})
        combined = " ".join(r.warnings)
        assert "Fe2O3_total_wt" in combined

    def test_hint_present_for_feo(self):
        """A v1.0 hint 'FeO_wt' appears in the warning text for bare 'FeO'."""
        _, r = _import({"FeO": 5.0})
        combined = " ".join(r.warnings)
        assert "FeO_wt" in combined


class TestSimpleOxideV0Rejected:

    def test_bare_sio2_rejected(self):
        """Bare 'SiO2' (without _wt) must be skipped."""
        m, r = _import({"SiO2": 60.0})
        assert m.get_oxide_wt("SiO2") == pytest.approx(0.0, abs=TOL)
        assert any("SiO2" in s for s in r.skipped)

    def test_bare_h2o_rejected(self):
        m, r = _import({"H2O": 2.0})
        assert m.get_oxide_wt("H2O") == pytest.approx(0.0, abs=TOL)
        assert any("H2O" in s for s in r.skipped)

    def test_bare_loi_rejected(self):
        m, r = _import({"LOI": 3.0})
        assert m.loi_measured == pytest.approx(0.0, abs=TOL)
        assert any("LOI" in s for s in r.skipped)

    def test_hint_for_bare_sio2(self):
        _, r = _import({"SiO2": 60.0})
        combined = " ".join(r.warnings)
        assert "SiO2_wt" in combined


class TestCarbonV0Rejected:

    def test_bare_c_rejected(self):
        m, r = _import({"C": 1.0})
        assert m.carbon.c_wt == pytest.approx(0.0, abs=TOL)
        assert any("C" in s for s in r.skipped)

    def test_co2t_rejected(self):
        m, r = _import({"CO2t": 2.0})
        assert m.carbon.c_wt == pytest.approx(0.0, abs=TOL)
        assert any("CO2t" in s for s in r.skipped)

    def test_co2_ratio_rejected(self):
        m, r = _import({"co2_ratio": 0.5})
        assert any("co2_ratio" in s for s in r.skipped)

    def test_c_graphite_rejected(self):
        m, r = _import({"C_graphite": 0.1, "C_carbonate": 0.3})
        assert m.carbon.c_wt == pytest.approx(0.0, abs=TOL)
        assert any("C_graphite" in s for s in r.skipped)

    def test_hint_for_co2t(self):
        _, r = _import({"CO2t": 2.0})
        combined = " ".join(r.warnings)
        assert "CO2_total_wt" in combined


class TestSulfurV0Rejected:

    def test_bare_s_rejected(self):
        m, r = _import({"S": 0.5})
        assert m.sulfur.s_wt == pytest.approx(0.0, abs=TOL)
        assert any("S" in s for s in r.skipped)

    def test_so3_ratio_rejected(self):
        m, r = _import({"so3_ratio": 0.2})
        assert any("so3_ratio" in s for s in r.skipped)

    def test_s1_ratio_rejected(self):
        m, r = _import({"s1_ratio": 0.3})
        assert any("s1_ratio" in s for s in r.skipped)

    def test_s_sulfate_rejected(self):
        m, r = _import({"S_sulfate": 0.1})
        assert m.sulfur.s_wt == pytest.approx(0.0, abs=TOL)
        assert any("S_sulfate" in s for s in r.skipped)

    def test_s1minus_bare_rejected(self):
        """Bare 'S1minus' (without _wt) must be skipped."""
        m, r = _import({"S1minus": 0.2})
        assert m.sulfur.s_wt == pytest.approx(0.0, abs=TOL)
        assert any("S1minus" in s for s in r.skipped)

    def test_s2minus_bare_rejected(self):
        """Bare 'S2minus' (without _wt) must be skipped."""
        m, r = _import({"S2minus": 0.1})
        assert m.sulfur.s_wt == pytest.approx(0.0, abs=TOL)
        assert any("S2minus" in s for s in r.skipped)

    def test_hint_for_so3_ratio(self):
        _, r = _import({"so3_ratio": 0.2})
        combined = " ".join(r.warnings)
        assert "S6plus_Stotal_ratio" in combined


class TestCanonicalSSoTRatiosStillWork:
    """Canonical SSoT ratio spellings must remain valid (not removed)."""

    def test_fe3_fetot_ratio_accepted(self):
        m, r = _import({
            "Fe2O3_total_wt": 10.0, "fe3_fetot_ratio": 0.25,
        })
        assert m.iron.fe2o3_tot_wt == pytest.approx(10.0, abs=1e-4)
        assert m.iron.fe3_fetot_ratio == pytest.approx(0.25, abs=1e-4)
        assert r.skipped == []

    def test_co2_ctot_ratio_accepted(self):
        m, r = _import({"C_total_wt": 1.0, "co2_ctot_ratio": 0.6})
        assert m.carbon.c_wt == pytest.approx(1.0, abs=1e-4)
        assert m.carbon.co2_ctot_ratio == pytest.approx(0.6, abs=1e-4)
        assert r.skipped == []

    def test_so3_stot_ratio_accepted(self):
        m, r = _import({"S_total_wt": 0.5, "so3_stot_ratio": 0.3})
        assert m.sulfur.s_wt == pytest.approx(0.5, abs=1e-4)
        assert m.sulfur.so3_stot_ratio == pytest.approx(0.3, abs=1e-4)
        assert r.skipped == []

    def test_s1_sred_ratio_accepted(self):
        m, r = _import({"S_total_wt": 0.5, "s1_sred_ratio": 0.4})
        assert m.sulfur.s1_sred_ratio == pytest.approx(0.4, abs=1e-4)
        assert r.skipped == []

    def test_all_four_canonicals_together(self):
        m, r = _import({
            "Fe2O3_total_wt": 10.0, "fe3_fetot_ratio": 0.25,
            "C_total_wt": 1.0,      "co2_ctot_ratio": 0.6,
            "S_total_wt": 0.5,      "so3_stot_ratio": 0.3,
            "s1_sred_ratio": 0.4,
        })
        assert m.iron.fe2o3_tot_wt == pytest.approx(10.0, abs=1e-4)
        assert m.iron.fe3_fetot_ratio == pytest.approx(0.25, abs=1e-4)
        assert m.carbon.c_wt == pytest.approx(1.0, abs=1e-4)
        assert m.carbon.co2_ctot_ratio == pytest.approx(0.6, abs=1e-4)
        assert m.sulfur.s_wt == pytest.approx(0.5, abs=1e-4)
        assert m.sulfur.so3_stot_ratio == pytest.approx(0.3, abs=1e-4)
        assert m.sulfur.s1_sred_ratio == pytest.approx(0.4, abs=1e-4)
        assert r.skipped == []
