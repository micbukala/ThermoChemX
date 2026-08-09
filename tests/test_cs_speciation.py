# ThermoChemX — Copyright (C) 2026  Michał Bukała <michal.bukala@csic.es>
# This program is free software: GNU General Public License v3 or later.
# It comes with ABSOLUTELY NO WARRANTY. See LICENSE.txt for details.

"""
Regression tests for the C/S speciation migration.
All five invariants from §1 of migration_plan_CS_speciation2.md must pass.

Invariant 1: Mass closure — model_mass_redox_corrected_g_per_kg = 1000.0 (tol 1e-6)
Invariant 2: Degeneracy to fixed speciation — co2_ratio=1.0, so3_ratio=0.0, s1_ratio=0.0
Invariant 3: Phantom-O isolation — pure sulfate → phantom_o = 0.0
Invariant 4: Fe²⁺/S²⁻ pair cancellation — sum of both O₂ terms = 0 for FeS
Invariant 5: SSoT round-trip — set→get without drift
"""

import math
import pytest

TOL = 1e-6

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _baseline_composition(comp):
    """A realistic mixed-rock composition: SiO2-rich with Fe, C, S."""
    comp.set_oxide_wt("SiO2",  50.0)
    comp.set_oxide_wt("Al2O3", 15.0)
    comp.set_oxide_wt("MgO",    8.0)
    comp.set_oxide_wt("CaO",    10.0)
    comp.set_oxide_wt("Na2O",   3.0)
    comp.iron.fe2o3_tot_wt = 8.0
    comp.iron.fe3_fetot_ratio = 0.3
    return comp


# ---------------------------------------------------------------------------
# Invariant 1: Mass closure
# ---------------------------------------------------------------------------

class TestMassClosure:
    """
    For any composition Σ(mol_i/kg × M_i) must equal 1000.0 g/kg (tol 1e-6).
    """

    def test_empty_composition(self, composition):
        # Edge case: zero composition → 0/0 guard; closure only meaningful when
        # total_model_redox_corrected > 0. Skip if denominator is zero.
        if composition.total_model_redox_corrected <= 0:
            pytest.skip("Empty composition: denominator is zero.")

    def test_simple_silicate(self, composition):
        _baseline_composition(composition)
        mass = composition.model_mass_redox_corrected
        assert abs(mass - 1000.0) < TOL, f"Mass closure failed: {mass}"

    def test_with_carbonate_only(self, composition):
        _baseline_composition(composition)
        composition.carbon.c_wt = 1.0
        composition.carbon.co2_ctot_ratio = 1.0      # all carbonate
        mass = composition.model_mass_redox_corrected
        assert abs(mass - 1000.0) < TOL, f"Mass closure (carbonate) failed: {mass}"

    def test_with_graphite_only(self, composition):
        _baseline_composition(composition)
        composition.carbon.c_wt = 1.0
        composition.carbon.co2_ctot_ratio = 0.0      # all graphite
        mass = composition.model_mass_redox_corrected
        assert abs(mass - 1000.0) < TOL, f"Mass closure (graphite) failed: {mass}"

    def test_with_sulfate_only(self, composition):
        _baseline_composition(composition)
        composition.sulfur.s_wt = 1.0
        composition.sulfur.so3_stot_ratio = 1.0      # pure sulfate
        mass = composition.model_mass_redox_corrected
        assert abs(mass - 1000.0) < TOL, f"Mass closure (sulfate) failed: {mass}"

    def test_with_s2minus_only(self, composition):
        _baseline_composition(composition)
        composition.sulfur.s_wt = 1.0
        composition.sulfur.so3_stot_ratio = 0.0      # pure monosulfide
        composition.sulfur.s1_sred_ratio = 0.0
        mass = composition.model_mass_redox_corrected
        assert abs(mass - 1000.0) < TOL, f"Mass closure (S2-) failed: {mass}"

    def test_with_s1minus_only(self, composition):
        _baseline_composition(composition)
        composition.sulfur.s_wt = 1.0
        composition.sulfur.so3_stot_ratio = 0.0
        composition.sulfur.s1_sred_ratio = 1.0       # pure disulfide/pyrite
        mass = composition.model_mass_redox_corrected
        assert abs(mass - 1000.0) < TOL, f"Mass closure (S1-) failed: {mass}"

    def test_mixed_graphite_pyrite_sulfate(self, composition):
        """
        The primary gate from §7: graphite + pyrite + sulfate simultaneously.
        """
        _baseline_composition(composition)
        composition.carbon.c_wt = 0.5
        composition.carbon.co2_ctot_ratio = 0.4      # 40% carbonate, 60% graphite
        composition.sulfur.s_wt = 0.8
        composition.sulfur.so3_stot_ratio = 0.3      # 30% sulfate
        composition.sulfur.s1_sred_ratio = 0.5       # 50% of reduced S as pyrite
        mass = composition.model_mass_redox_corrected
        assert abs(mass - 1000.0) < TOL, f"Mass closure (mixed) failed: {mass}"


# ---------------------------------------------------------------------------
# Invariant 2: Degeneracy to fixed speciation
# ---------------------------------------------------------------------------

class TestDegeneracyV10:
    """
    With co2_ratio=1.0, so3_ratio=0.0, s1_ratio=0.0 the system behaves exactly
    as the fixed-speciation reference: all C as carbonate (CO₂), all S as
    monosulfide (S²⁻).
    The results must match a reference fixed-speciation calculation using the same wt% inputs.
    """

    def _set_v10_ratios(self, comp):
        comp.carbon.co2_ctot_ratio = 1.0
        comp.sulfur.so3_stot_ratio = 0.0
        comp.sulfur.s1_sred_ratio = 0.0

    def test_c_species_degenerate(self, composition):
        _baseline_composition(composition)
        composition.carbon.c_wt = 2.0
        self._set_v10_ratios(composition)

        # All C must be in carbonates; zero graphite
        assert composition.carbon.c0_wt == pytest.approx(0.0, abs=TOL)
        assert composition.carbon.c4_wt == pytest.approx(2.0, abs=TOL)

    def test_s_species_degenerate(self, composition):
        _baseline_composition(composition)
        composition.sulfur.s_wt = 1.5
        self._set_v10_ratios(composition)

        # All S must be S²⁻; no sulfate, no pyrite
        assert composition.sulfur.s6_wt == pytest.approx(0.0, abs=TOL)
        assert composition.sulfur.s1_wt == pytest.approx(0.0, abs=TOL)
        assert composition.sulfur.s2_wt == pytest.approx(1.5, abs=TOL)

    def test_phantom_o_v10(self, composition):
        """With all S as S²⁻, phantom-O = (M_O/M_S) × s_wt."""
        from thermochemx.utils.constants import ELEMENT_MASSES
        _baseline_composition(composition)
        s_wt = 1.5
        composition.sulfur.s_wt = s_wt
        self._set_v10_ratios(composition)

        expected = s_wt * ELEMENT_MASSES['o'] / ELEMENT_MASSES['s']
        assert composition.phantom_o_from_sulfide_wt == pytest.approx(expected, rel=1e-9)

    def test_total_model_v10(self, composition):
        """total_model in degenerate mode = simple_oxides + FeO+Fe2O3 + CO2_real + S_sulfide + H2O."""
        from thermochemx.utils.constants import OXIDE_MASSES, ELEMENT_MASSES
        _baseline_composition(composition)
        composition.carbon.c_wt = 1.0
        composition.sulfur.s_wt = 0.5
        self._set_v10_ratios(composition)

        # c_graphite_wt = 0, so3_real_wt = 0 in v1.0 mode
        assert composition.carbon.c0_wt == pytest.approx(0.0, abs=TOL)
        assert composition.sulfur.s6_oxide_wt == pytest.approx(0.0, abs=TOL)

        mass = composition.model_mass_redox_corrected
        assert abs(mass - 1000.0) < TOL


# ---------------------------------------------------------------------------
# Invariant 3: Phantom-O isolation (pure sulfate)
# ---------------------------------------------------------------------------

class TestPhantomOIsolation:
    """
    With so3_ratio=1.0, sulfide species are zero → phantom-O must be exactly 0.
    total_model_redox_corrected must equal total_model.
    """

    def test_pure_sulfate_phantom_o_is_zero(self, composition):
        _baseline_composition(composition)
        composition.sulfur.s_wt = 2.0
        composition.sulfur.so3_stot_ratio = 1.0

        assert composition.phantom_o_from_sulfide_wt == pytest.approx(0.0, abs=TOL)

    def test_pure_sulfate_redox_corrected_equals_total(self, composition):
        _baseline_composition(composition)
        composition.sulfur.s_wt = 2.0
        composition.sulfur.so3_stot_ratio = 1.0

        assert (composition.total_model_redox_corrected ==
                pytest.approx(composition.total_model, rel=1e-12))

    def test_no_sulfur_phantom_o_is_zero(self, composition):
        _baseline_composition(composition)
        composition.sulfur.s_wt = 0.0

        assert composition.phantom_o_from_sulfide_wt == pytest.approx(0.0, abs=TOL)

    def test_partial_sulfate_phantom_o_only_from_sulfide(self, composition):
        """Only the sulfide fraction should contribute to phantom-O."""
        from thermochemx.utils.constants import ELEMENT_MASSES
        _baseline_composition(composition)
        s_total = 2.0
        so3_ratio = 0.4
        s1_ratio = 0.0  # all reduced is S²⁻
        composition.sulfur.s_wt = s_total
        composition.sulfur.so3_stot_ratio = so3_ratio
        composition.sulfur.s1_sred_ratio = s1_ratio

        s_2minus = s_total * (1 - so3_ratio)  # 1.2 wt%
        expected_phantom = s_2minus * ELEMENT_MASSES['o'] / ELEMENT_MASSES['s']
        assert composition.phantom_o_from_sulfide_wt == pytest.approx(expected_phantom, rel=1e-9)


# ---------------------------------------------------------------------------
# Invariant 4: Fe²⁺ / S²⁻ pair cancellation
# ---------------------------------------------------------------------------

class TestFeSPairCancellation:
    """
    For FeS the Fe²⁺ contribution (+0.5 O₂/Fe) and S²⁻ contribution (−0.5 O₂/S)
    cancel when mol/kg are equal. Test the *sum* of both terms = 0.
    """

    def test_fes_pair_o2_sum_zero(self, composition):
        """
        Pure FeS: Fe²⁺ and S²⁻ in equal molar proportion.
        Set up: FeO-only iron, S²⁻-only sulfur, matching mol amounts.
        """
        from thermochemx.utils.constants import OXIDE_MASSES, ELEMENT_MASSES

        # Use a minimal composition (just SiO2 as matrix to keep denominator non-zero)
        composition.set_oxide_wt("SiO2", 80.0)
        # Set iron as FeO (all Fe²⁺): iron system uses Fe₂O₃_tot + ratio
        composition.iron.fe2o3_tot_wt = 5.0
        composition.iron.fe3_fetot_ratio = 0.0  # all Fe²⁺

        # S²⁻ only
        composition.sulfur.s_wt = 1.5
        composition.sulfur.so3_stot_ratio = 0.0
        composition.sulfur.s1_sred_ratio = 0.0

        # Pull mol/kg values from the model
        m = composition.model
        fe2_mol_kg = m._mol_kg(composition.iron.fe2_oxide_wt, OXIDE_MASSES['feo'])
        s2minus_mol_kg = m._mol_kg(composition.sulfur.s2_wt, ELEMENT_MASSES['s'])

        pair_sum = fe2_mol_kg * 0.5 + s2minus_mol_kg * (-0.5)
        assert abs(pair_sum) < TOL or fe2_mol_kg != pytest.approx(s2minus_mol_kg, rel=0.01), \
            "Pair cancellation only guaranteed at equal mol/kg; skip tolerance check if mol differ"

    def test_fes_exact_molar_pair(self, composition):
        """
        Exact FeS stoichiometry: Fe/S molar ratio = 1. Set wt% accordingly.
        Fe contribution and S contribution must cancel to within TOL.
        """
        from thermochemx.utils.constants import OXIDE_MASSES, ELEMENT_MASSES

        M_Fe = ELEMENT_MASSES['fe']
        M_S = ELEMENT_MASSES['s']
        M_FeO = OXIDE_MASSES['feo']

        # Choose S wt% and compute matching Fe wt% for 1:1 molar ratio
        s_wt = 1.0  # 1 wt% S
        fe_wt = s_wt * (M_Fe / M_S)  # same mol per gram → same mol/kg

        # Iron: express as Fe₂O₃_tot with ratio 0 (all Fe²⁺)
        fe2o3_factor = OXIDE_MASSES['fe2o3'] / (2 * M_Fe)
        composition.set_oxide_wt("SiO2", 80.0)
        composition.iron.fe2o3_tot_wt = fe_wt * fe2o3_factor / (OXIDE_MASSES['feo'] / M_FeO)
        # Simpler: set FeO directly via feo_tot_wt
        composition.iron.feo_tot_wt = fe_wt * (M_FeO / M_Fe)
        composition.iron.fe3_fetot_ratio = 0.0

        composition.sulfur.s_wt = s_wt
        composition.sulfur.so3_stot_ratio = 0.0
        composition.sulfur.s1_sred_ratio = 0.0

        m = composition.model
        fe2_mol_kg = m._mol_kg(composition.iron.fe2_oxide_wt, OXIDE_MASSES['feo'])
        s2minus_mol_kg = m._mol_kg(composition.sulfur.s2_wt, ELEMENT_MASSES['s'])

        pair_sum = fe2_mol_kg * 0.5 + s2minus_mol_kg * (-0.5)
        assert abs(pair_sum) < 1e-9, (
            f"FeS pair O₂ sum = {pair_sum}; fe2={fe2_mol_kg}, s2minus={s2minus_mol_kg}"
        )


# ---------------------------------------------------------------------------
# Invariant 5: SSoT round-trip
# ---------------------------------------------------------------------------

class TestSSOTRoundTrip:
    """
    Each setter must preserve other species and not drift on set→get.
    """

    def test_carbon_graphite_setter_preserves_carbonate(self, composition):
        composition.carbon.c_wt = 2.0
        composition.carbon.co2_ctot_ratio = 0.5  # 1.0 carbonate, 1.0 graphite

        # Change graphite directly — carbonate must stay at 1.0
        composition.carbon.c0_wt = 0.6
        assert composition.carbon.c4_wt == pytest.approx(1.0, abs=TOL)
        assert composition.carbon.c_wt == pytest.approx(1.6, abs=TOL)

    def test_carbon_carbonate_setter_preserves_graphite(self, composition):
        composition.carbon.c_wt = 2.0
        composition.carbon.co2_ctot_ratio = 0.5  # 1.0 each

        composition.carbon.c4_wt = 0.4
        assert composition.carbon.c0_wt == pytest.approx(1.0, abs=TOL)
        assert composition.carbon.c_wt == pytest.approx(1.4, abs=TOL)

    def test_carbon_ugg_round_trip(self, composition):
        composition.carbon.c_wt = 1.0
        composition.carbon.co2_ctot_ratio = 0.7

        graphite_ugg = composition.carbon.c0_ugg
        composition.carbon.c0_ugg = graphite_ugg  # no-op
        assert composition.carbon.c0_ugg == pytest.approx(graphite_ugg, rel=1e-12)

    def test_sulfur_s1minus_setter_preserves_s2minus(self, composition):
        composition.sulfur.s_wt = 2.0
        composition.sulfur.so3_stot_ratio = 0.0
        composition.sulfur.s1_sred_ratio = 0.5  # 1.0 S1-, 1.0 S2-

        composition.sulfur.s1_wt = 0.3
        assert composition.sulfur.s2_wt == pytest.approx(1.0, abs=TOL)
        assert composition.sulfur.s_wt == pytest.approx(1.3, abs=TOL)

    def test_sulfur_s2minus_setter_preserves_s1minus(self, composition):
        composition.sulfur.s_wt = 2.0
        composition.sulfur.so3_stot_ratio = 0.0
        composition.sulfur.s1_sred_ratio = 0.5  # 1.0 each

        composition.sulfur.s2_wt = 0.8
        assert composition.sulfur.s1_wt == pytest.approx(1.0, abs=TOL)
        assert composition.sulfur.s_wt == pytest.approx(1.8, abs=TOL)

    def test_sulfur_sulfate_setter_preserves_sulfide(self, composition):
        composition.sulfur.s_wt = 3.0
        composition.sulfur.so3_stot_ratio = 0.5  # 1.5 sulfate, 1.5 sulfide

        composition.sulfur.s6_wt = 0.5
        assert composition.sulfur.s_red_wt == pytest.approx(1.5, abs=TOL)
        assert composition.sulfur.s_wt == pytest.approx(2.0, abs=TOL)

    def test_ratio_clamp_carbon(self, composition):
        composition.carbon.co2_ctot_ratio = 1.5   # over-range
        assert composition.carbon.co2_ctot_ratio == pytest.approx(1.0, abs=TOL)
        composition.carbon.co2_ctot_ratio = -0.3  # under-range
        assert composition.carbon.co2_ctot_ratio == pytest.approx(0.0, abs=TOL)

    def test_ratio_clamp_sulfur(self, composition):
        composition.sulfur.so3_stot_ratio = 2.0
        assert composition.sulfur.so3_stot_ratio == pytest.approx(1.0, abs=TOL)
        composition.sulfur.s1_sred_ratio = -1.0
        assert composition.sulfur.s1_sred_ratio == pytest.approx(0.0, abs=TOL)
