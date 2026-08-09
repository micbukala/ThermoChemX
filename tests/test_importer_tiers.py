# ThermoChemX — Copyright (C) 2026  Michał Bukała <michal.bukala@csic.es>
# This program is free software: GNU General Public License v3 or later.
# It comes with ABSOLUTELY NO WARRANTY. See LICENSE.txt for details.

"""
Tests for tier-based priority resolution in `core.importer.apply_to_model`.

Verifies SYSTEM_TIERS contract from utils.aliases:
  • First tier with any present input wins per system.
  • Later-tier keys produce skip-warnings.
  • RATIO_KEYS apply last and override the tier-derived ratio.
  • Carbon seeding (co2_ctot_ratio=1.0) fires only on Tier A without explicit ratio.

All input keys use the v1.0 vocabulary (e.g. Fe2O3_total_wt, C_total_wt,
S_total_wt).  Canonical SSoT ratio spellings (fe3_fetot_ratio, co2_ctot_ratio,
so3_stot_ratio, s1_sred_ratio) are also tested as a second live spelling.
"""
import math
import pytest

from thermochemx.core.importer import apply_to_model
from thermochemx.core.composition import BulkComposition

TOL = 1e-4

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _import(data):
    """Apply a raw dict to a fresh BulkComposition; return (model, result)."""
    m = BulkComposition()
    r = apply_to_model(data, m)
    return m, r


# ---------------------------------------------------------------------------
# Iron — tier resolution
# ---------------------------------------------------------------------------

class TestIronTiers:

    def test_tier_a_locks_iron(self):
        """Tier A (Fe2O3_total_wt + ratio) wins; Tier D µg/g warned."""
        m, r = _import({
            "Fe2O3_total_wt": 8.0, "Fe3plus_Fetotal_ratio": 0.25,
            "Fe2plus_ugg": 50000, "Fe3plus_ugg": 10000,
        })
        assert abs(m.iron.fe2o3_tot_wt - 8.0) < TOL
        assert abs(m.iron.fe3_fetot_ratio - 0.25) < TOL
        assert any("Fe2plus_ugg" in w and "iron system" in w for w in r.warnings)
        assert any("Fe3plus_ugg" in w and "iron system" in w for w in r.warnings)

    def test_tier_b_wins_iron_when_no_tier_a(self):
        """Tier B (FeO_wt + Fe2O3_wt) wins when Tier A absent."""
        m, r = _import({"FeO_wt": 8.0, "Fe2O3_wt": 2.0, "Fe3plus_Fetotal_ratio": 0.18})
        assert m.iron.fe2_oxide_wt > 0
        assert m.iron.fe3_oxide_wt > 0
        # Explicit ratio should override the derived one (Pass 2).
        assert abs(m.iron.fe3_fetot_ratio - 0.18) < TOL

    def test_tier_d_elemental_ugg(self):
        """Tier D (Fe2plus_ugg + Fe3plus_ugg) used when no higher tier present."""
        m, r = _import({"Fe2plus_ugg": 63800, "Fe3plus_ugg": 16100})
        # 1 wt% = 10000 µg/g → Fe2 = 6.38 wt% Fe, Fe3 = 1.61 wt% Fe
        assert m.iron.fe2o3_tot_wt > 0
        assert 0.18 < m.iron.fe3_fetot_ratio < 0.22
        assert r.warnings == []

    def test_explicit_ratio_overrides_tier_b(self):
        """An explicit ratio supplied alongside Tier B overrides the
        ratio derived from FeO_wt+Fe2O3_wt (RATIO_KEYS apply last)."""
        m, _ = _import({"FeO_wt": 9.0, "Fe2O3_wt": 1.0, "Fe3plus_Fetotal_ratio": 0.50})
        assert abs(m.iron.fe3_fetot_ratio - 0.50) < TOL

    def test_canonical_ssot_ratio_works(self):
        """Canonical SSoT spelling fe3_fetot_ratio is a live second spelling."""
        m, r = _import({"Fe2O3_total_wt": 8.0, "fe3_fetot_ratio": 0.30})
        assert abs(m.iron.fe2o3_tot_wt - 8.0) < TOL
        assert abs(m.iron.fe3_fetot_ratio - 0.30) < TOL
        assert r.skipped == []


# ---------------------------------------------------------------------------
# Carbon — tier resolution
# ---------------------------------------------------------------------------

class TestCarbonTiers:

    def test_tier_a_seeds_ratio_when_no_explicit(self):
        """CO2_total_wt supplied alone → co2_ctot_ratio seeded to 1.0."""
        m, _ = _import({"CO2_total_wt": 2.57})
        assert abs(m.carbon.co2_ctot_ratio - 1.0) < TOL

    def test_tier_a_c_total_wt_seeds_ratio(self):
        """C_total_wt alone → seeded to 1.0 (all carbonate default)."""
        m, _ = _import({"C_total_wt": 2.57})
        assert abs(m.carbon.co2_ctot_ratio - 1.0) < TOL

    def test_tier_a_with_explicit_ratio_no_seed(self):
        """Explicit C4plus_Ctotal_ratio always wins (Pass 2 override)."""
        m, _ = _import({"CO2_total_wt": 2.57, "C4plus_Ctotal_ratio": 0.5})
        assert abs(m.carbon.co2_ctot_ratio - 0.5) < TOL

    def test_tier_a_with_canonical_ratio(self):
        """Canonical co2_ctot_ratio also overrides seeding."""
        m, _ = _import({"C_total_wt": 2.57, "co2_ctot_ratio": 0.6})
        assert abs(m.carbon.co2_ctot_ratio - 0.6) < TOL

    def test_tier_b_species_pair(self):
        """C0_wt + C4plus_wt → c_wt and ratio derived from the pair."""
        m, r = _import({"C0_wt": 0.10, "C4plus_wt": 0.30})
        assert abs(m.carbon.c_wt - 0.40) < TOL
        # 0.30 of 0.40 total is carbonate → co2 fraction = 0.75
        assert abs(m.carbon.co2_ctot_ratio - 0.75) < TOL
        assert r.warnings == []

    def test_tier_c_overridden_by_tier_a(self):
        """When CO2_total_wt and C0_ugg both present, Tier A wins."""
        m, r = _import({
            "CO2_total_wt": 2.0, "C4plus_Ctotal_ratio": 1.0,
            "C0_ugg": 100, "C4plus_ugg": 500,
        })
        assert any("C0_ugg" in w for w in r.warnings)
        assert any("C4plus_ugg" in w for w in r.warnings)


# ---------------------------------------------------------------------------
# Sulfur — tier resolution
# ---------------------------------------------------------------------------

class TestSulfurTiers:

    def test_tier_b_three_species(self):
        """S6plus_wt + S1minus_wt + S2minus_wt → totals and ratios derived."""
        m, r = _import({"S6plus_wt": 0.01, "S1minus_wt": 0.03, "S2minus_wt": 0.04})
        # Total S = 0.08 wt%
        assert abs(m.sulfur.s_wt - 0.08) < TOL
        # Sulfate fraction = 0.01 / 0.08 = 0.125
        assert abs(m.sulfur.so3_stot_ratio - 0.125) < TOL
        # Of reduced S (0.07), S1- = 0.03 → s1_ratio ≈ 0.4286
        assert abs(m.sulfur.s1_sred_ratio - (0.03 / 0.07)) < TOL
        assert r.warnings == []

    def test_tier_c_ugg(self):
        """µg/g sulfur species → wt% conversion."""
        m, _ = _import({"S6plus_ugg": 120, "S1minus_ugg": 180, "S2minus_ugg": 240})
        # 120+180+240 = 540 µg/g = 0.054 wt%
        assert abs(m.sulfur.s_wt - 0.054) < TOL

    def test_tier_a_then_b_warns(self):
        """When Tier A (S_total_wt) and Tier B species both supplied, A wins, B warns."""
        m, r = _import({
            "S_total_wt": 0.10, "S6plus_Stotal_ratio": 0.10,
            "S6plus_wt": 0.05, "S1minus_wt": 0.02,
        })
        assert abs(m.sulfur.s_wt - 0.10) < TOL
        assert abs(m.sulfur.so3_stot_ratio - 0.10) < TOL
        assert any("S6plus_wt" in w for w in r.warnings)
        assert any("S1minus_wt" in w for w in r.warnings)

    def test_canonical_ssot_ratios_work(self):
        """Canonical SSoT spellings so3_stot_ratio and s1_sred_ratio are live."""
        m, r = _import({
            "S_total_wt": 0.5, "so3_stot_ratio": 0.3, "s1_sred_ratio": 0.4,
        })
        assert abs(m.sulfur.s_wt - 0.5) < TOL
        assert abs(m.sulfur.so3_stot_ratio - 0.3) < TOL
        assert abs(m.sulfur.s1_sred_ratio - 0.4) < TOL
        assert r.skipped == []


# ---------------------------------------------------------------------------
# Mixed-system conflict
# ---------------------------------------------------------------------------

class TestMixedConflict:

    def test_three_iron_tiers_one_wins(self):
        """Iron filled at Tier A + Tier B + Tier D → A wins, others warn."""
        m, r = _import({
            "Fe2O3_total_wt": 10.0, "Fe3plus_Fetotal_ratio": 0.30,
            "FeO_wt": 5.0, "Fe2O3_wt": 3.0,
            "Fe2plus_ugg": 40000, "Fe3plus_ugg": 20000,
        })
        assert abs(m.iron.fe2o3_tot_wt - 10.0) < TOL
        assert abs(m.iron.fe3_fetot_ratio - 0.30) < TOL
        # Tier B keys warned
        assert any("FeO_wt" in w for w in r.warnings)
        assert any("Fe2O3_wt" in w for w in r.warnings)
        # Tier D keys warned
        assert any("Fe2plus_ugg" in w for w in r.warnings)
        assert any("Fe3plus_ugg" in w for w in r.warnings)


# ---------------------------------------------------------------------------
# Consistency-based tier override
#
# When both Tier A (total) and a *complete* lower tier (species) are
# supplied and their sums agree within tolerance, the species tier is
# preferred so the redox ratios encoded in the split are preserved.
# ---------------------------------------------------------------------------

class TestConsistencyOverride:

    def test_sulfur_ugg_species_override_total_ugg(self):
        """Serpentinite: S_total_ugg=170 vs species ugg sum 80+42+48=170.
        Species Tier C wins → ratios derived, no warnings."""
        m, r = _import({
            "S_total_ugg": 170,
            "S6plus_ugg": 80, "S1minus_ugg": 42, "S2minus_ugg": 48,
        })
        assert abs(m.sulfur.s_wt - 0.017) < TOL
        assert abs(m.sulfur.so3_stot_ratio - 80.0 / 170.0) < TOL
        assert abs(m.sulfur.s1_sred_ratio - 42.0 / 90.0) < TOL
        assert not any("S6plus_ugg" in w or "S1minus_ugg" in w or "S2minus_ugg" in w
                       for w in r.warnings)

    def test_iron_species_wt_override_total_wt(self):
        """Serpentinite iron: Fe2O3_total=8.04 vs Fe2O3_wt=4.61 + FeO_wt=3.09.
        Sum as Fe wt%: 4.61×(2·55.845/159.69) + 3.09×(55.845/71.844) ≈ 5.628,
        Tier A total as Fe: 8.04×(2·55.845/159.69) ≈ 5.626 → consistent.
        Tier B wins → ratio derived, no warnings for FeO_wt/Fe2O3_wt."""
        m, r = _import({
            "Fe2O3_total_wt": 8.04, "FeO_wt": 3.09, "Fe2O3_wt": 4.61,
        })
        # Tier B recovered → SSoT holds sum of both oxides as Fe2O3-tot
        assert m.iron.fe3_fetot_ratio > 0.5   # ferric dominates
        assert m.iron.fe2_oxide_wt > 0
        assert m.iron.fe3_oxide_wt > 0
        assert not any("FeO_wt" in w or "Fe2O3_wt" in w for w in r.warnings)

    def test_carbon_species_wt_override_total_wt(self):
        """C0_wt=0.10 + C4plus_wt=0.30 (sum 0.40) vs C_total_wt=0.40.
        Tier B wins → ratio derived from species pair (0.75), no seeding."""
        m, r = _import({
            "C_total_wt": 0.40, "C0_wt": 0.10, "C4plus_wt": 0.30,
        })
        assert abs(m.carbon.c_wt - 0.40) < TOL
        assert abs(m.carbon.co2_ctot_ratio - 0.75) < TOL
        assert not any("C0_wt" in w or "C4plus_wt" in w for w in r.warnings)

    def test_incomplete_lower_tier_falls_back_to_A(self):
        """Only 2 of 3 sulfur species present → Tier A still wins with warnings."""
        m, r = _import({
            "S_total_wt": 0.10, "S6plus_wt": 0.05, "S1minus_wt": 0.02,
            # S2minus_wt missing → Tier B incomplete
        })
        assert abs(m.sulfur.s_wt - 0.10) < TOL
        assert any("S6plus_wt" in w for w in r.warnings)
        assert any("S1minus_wt" in w for w in r.warnings)

    def test_inconsistent_species_falls_back_to_A(self):
        """Complete species set but sum ≠ Tier A total → Tier A wins with warnings."""
        m, r = _import({
            "S_total_ugg": 170,
            "S6plus_ugg": 10, "S1minus_ugg": 20, "S2minus_ugg": 30,  # sum=60, not 170
        })
        assert abs(m.sulfur.s_wt - 0.017) < TOL   # from S_total_ugg
        assert abs(m.sulfur.so3_stot_ratio) < TOL # ratio stays at 0 (no override)
        assert any("S6plus_ugg" in w for w in r.warnings)

    def test_no_tier_a_lower_tier_still_wins_normally(self):
        """No Tier A present → lower tier wins as before (regression guard)."""
        m, r = _import({
            "S6plus_ugg": 80, "S1minus_ugg": 42, "S2minus_ugg": 48,
        })
        assert abs(m.sulfur.s_wt - 0.017) < TOL
        assert abs(m.sulfur.so3_stot_ratio - 80.0 / 170.0) < TOL
        assert r.warnings == []
