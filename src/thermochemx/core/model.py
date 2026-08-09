# ThermoChemX — Copyright (C) 2026  Michał Bukała <michal.bukala@csic.es>
# This program is free software: GNU General Public License v3 or later.
# It comes with ABSOLUTELY NO WARRANTY. See LICENSE.txt for details.

"""
MolarModel: Stateless calculation engine for converting weight percentages to mol cations/kg.
Acts as the Single Source of Truth (SSoT) for mol/kg calculations.
"""

from typing import TYPE_CHECKING, Dict
from ..utils.constants import OXIDE_MASSES, ELEMENT_MASSES

if TYPE_CHECKING:
    from .composition import BulkComposition

class MolarModel:
    """
    Calculation engine converting wt% oxides to mol cations per kg of normalized rock.
    
    General formula:
        mol/kg = n_cations × (wt% / molar_mass) × 1000 / total_model
    
    Calculation basis:
    - Accepts reference to BulkComposition (orchestrator)
    - Reads data from _simple_oxides, iron.*, carbon.*, sulfur.*
    - Exposure: 15 properties for individual cations + `all_mol_kg` (dictionary)
    """
    
    def __init__(self, composition: "BulkComposition", strategy=None) -> None:
        """
        Args:
            composition: Instance of BulkComposition (composition orchestrator)
            strategy: NormalizationStrategy instance.  Defaults to MolKg1000g
                (existing Perple_X element-basis behaviour, regression anchor).
        """
        self._comp = composition
        if strategy is None:
            from .recalc.normalization import MolKg1000g
            strategy = MolKg1000g()
        self._strategy = strategy
    
    def _abs_mol(self, wt_value: float, molar_mass: float, n_cations: int = 1) -> float:
        """
        Unnormalised absolute moles: n_cations × wt_value / molar_mass.
        Used by build_recalc_result to obtain Layer-A quantities before any
        normalisation strategy is applied.
        """
        if molar_mass <= 0:
            return 0.0
        return n_cations * wt_value / molar_mass

    def _mol_kg(self, wt_value: float, molar_mass: float, n_cations: int = 1) -> float:
        """
        Calculates mol cations / kg rock normalized to total_model_redox_corrected.

        Uses the phantom-O-corrected denominator so that Σ(mol_i × M_i) = 1000 g/kg
        for any composition including sulfide-bearing rocks.
        
        Args:
            wt_value: Weight value of oxide or element (wt%)
            molar_mass: Molar mass of oxide (from OXIDE_MASSES) or element (from ELEMENT_MASSES)
            n_cations: Number of cations in formula unit (e.g., 2 for Al2O3)
        
        Returns:
            mol/kg (0.0 if total_model_redox_corrected <= 0)
        """
        # NOTE: route through strategy — do NOT inline or re-associate this
        # expression; the arithmetic order is guarded by the golden regression lock.
        denom = self._strategy.denom(self._comp)
        if denom <= 0:
            return 0.0
        return n_cations * wt_value / molar_mass * 1000 / denom
    
    # =====================================================================
    # PROPERTIES: INDIVIDUAL CATIONS
    # =====================================================================
    
    @property
    def si_mol_kg(self) -> float:
        """SiO2 → Si"""
        return self._mol_kg(
            self._comp.get_oxide_wt('SiO2'),
            OXIDE_MASSES['sio2'],
            n_cations=1
        )
    
    @property
    def ti_mol_kg(self) -> float:
        """TiO2 → Ti"""
        return self._mol_kg(
            self._comp.get_oxide_wt('TiO2'),
            OXIDE_MASSES['tio2'],
            n_cations=1
        )
    
    @property
    def al_mol_kg(self) -> float:
        """Al2O3 → Al (2 cations)"""
        return self._mol_kg(
            self._comp.get_oxide_wt('Al2O3'),
            OXIDE_MASSES['al2o3'],
            n_cations=2
        )
    
    @property
    def cr_mol_kg(self) -> float:
        """Cr2O3 → Cr (2 cations)"""
        return self._mol_kg(
            self._comp.get_oxide_wt('Cr2O3'),
            OXIDE_MASSES['cr2o3'],
            n_cations=2
        )
    
    @property
    def mn_mol_kg(self) -> float:
        """MnO → Mn"""
        return self._mol_kg(
            self._comp.get_oxide_wt('MnO'),
            OXIDE_MASSES['mno'],
            n_cations=1
        )
    
    @property
    def mg_mol_kg(self) -> float:
        """MgO → Mg"""
        return self._mol_kg(
            self._comp.get_oxide_wt('MgO'),
            OXIDE_MASSES['mgo'],
            n_cations=1
        )
    
    @property
    def ca_mol_kg(self) -> float:
        """CaO → Ca"""
        return self._mol_kg(
            self._comp.get_oxide_wt('CaO'),
            OXIDE_MASSES['cao'],
            n_cations=1
        )
    
    @property
    def ni_mol_kg(self) -> float:
        """NiO → Ni"""
        return self._mol_kg(
            self._comp.get_oxide_wt('NiO'),
            OXIDE_MASSES['nio'],
            n_cations=1
        )
    
    @property
    def na_mol_kg(self) -> float:
        """Na2O → Na (2 cations)"""
        return self._mol_kg(
            self._comp.get_oxide_wt('Na2O'),
            OXIDE_MASSES['na2o'],
            n_cations=2
        )
    
    @property
    def k_mol_kg(self) -> float:
        """K2O → K (2 cations)"""
        return self._mol_kg(
            self._comp.get_oxide_wt('K2O'),
            OXIDE_MASSES['k2o'],
            n_cations=2
        )
    
    @property
    def p_mol_kg(self) -> float:
        """P2O5 → P (2 cations)"""
        return self._mol_kg(
            self._comp.get_oxide_wt('P2O5'),
            OXIDE_MASSES['p2o5'],
            n_cations=2
        )
    
    @property
    def h2_mol_kg(self) -> float:
        """
        H2O → H2 (basis component = H₂, not H).
        Note: We don't multiply by 2 — one H2O gives one "H2 unit".
        """
        return self._mol_kg(
            self._comp.get_oxide_wt('H2O'),
            OXIDE_MASSES['h2o'],
            n_cations=1
        )
    
    @property
    def fe_mol_kg(self) -> float:
        """
        Total iron as FeO_total (actual, accounting for redox).
        """
        return self._mol_kg(
            self._comp.iron.feo_tot_wt,
            OXIDE_MASSES['feo'],
            n_cations=1
        )
    
    @property
    def c_mol_kg(self) -> float:
        """
        Elemental C (graphite, C⁰).
        """
        return self._mol_kg(
            self._comp.carbon.c_wt,
            ELEMENT_MASSES['c'],
            n_cations=1
        )
    
    @property
    def s2_mol_kg(self) -> float:
        """
        S₂ (basis component = S₂, not S).
        Note: Molar mass = ELEMENT_MASSES['s'] * 2 = 64.13 g/mol
        """
        return self._mol_kg(
            self._comp.sulfur.s_wt,
            ELEMENT_MASSES['s'] * 2,
            n_cations=1
        )
    
    # =====================================================================
    # PROPERTY: OXYGEN O₂ (oxygen balance)
    # =====================================================================

    @property
    def o2_mol_kg(self) -> float:
        """
        Total amount of O₂ in mol/kg.
        Sum of contribution from simple oxides and redox speciation (Fe, C, S, H).
        """
        return self._o2_from_simple_oxides + self._o2_from_redox_species

    @property
    def _o2_from_simple_oxides(self) -> float:
        """
        O₂ from simple oxides (SiO₂ ... P₂O₅, H₂O).
        n_anions = mol O₂ per mol cation = (number of O in oxide) / (n_cations × 2).
        H₂O included here because hydrogen has no redox speciation in this system.
        """
        return (
            self.si_mol_kg * 1.0 +       # SiO₂:  2O / 1Si / 2 = 1.0  O₂/Si
            self.ti_mol_kg * 1.0 +       # TiO₂:  2O / 1Ti / 2 = 1.0  O₂/Ti
            self.al_mol_kg * 0.75 +      # Al₂O₃: 3O / 2Al / 2 = 0.75 O₂/Al
            self.cr_mol_kg * 0.75 +      # Cr₂O₃: 3O / 2Cr / 2 = 0.75 O₂/Cr
            self.mn_mol_kg * 0.5 +       # MnO:   1O / 1Mn / 2 = 0.5  O₂/Mn
            self.mg_mol_kg * 0.5 +       # MgO:   1O / 1Mg / 2 = 0.5  O₂/Mg
            self.ca_mol_kg * 0.5 +       # CaO:   1O / 1Ca / 2 = 0.5  O₂/Ca
            self.ni_mol_kg * 0.5 +       # NiO:   1O / 1Ni / 2 = 0.5  O₂/Ni
            self.na_mol_kg * 0.25 +      # Na₂O:  1O / 2Na / 2 = 0.25 O₂/Na
            self.k_mol_kg * 0.25 +       # K₂O:   1O / 2K  / 2 = 0.25 O₂/K
            self.p_mol_kg * 1.25 +       # P₂O₅:  5O / 2P  / 2 = 1.25 O₂/P
            self.h2_mol_kg * 0.5         # H₂O:   1O / 1H₂ / 2 = 0.5  O₂/H₂
        )

    @property
    def _o2_from_redox_species(self) -> float:
        """
        O₂ from redox species: Fe²⁺, Fe³⁺, C⁴⁺, S²⁻, S¹⁻, S⁶⁺.
        O₂ balance required for oxidation/reduction from elemental state.
        Intermediate values in mol atoms / kg (not molecules).

        Graphite (C⁰) contributes 0 O₂ — bare carbon, no oxygen needed.
        S¹⁻ and S²⁻ carry negative phantom-O corrections; S⁶⁺ carries positive.
        These helpers are local to this method and are NOT added to all_mol_kg
        (which holds only Perple_X basis components).
        """
        fe2_mol_kg    = self._mol_kg(self._comp.iron.fe2_oxide_wt,       OXIDE_MASSES['feo'])
        fe3_mol_kg    = self._mol_kg(self._comp.iron.fe3_oxide_wt,       OXIDE_MASSES['fe2o3'], n_cations=2)
        c4_mol_kg     = self._mol_kg(self._comp.carbon.c4_wt,            ELEMENT_MASSES['c'])
        s2minus_mol_kg = self._mol_kg(self._comp.sulfur.s2_wt,           ELEMENT_MASSES['s'])
        s1minus_mol_kg = self._mol_kg(self._comp.sulfur.s1_wt,           ELEMENT_MASSES['s'])
        s6plus_mol_kg  = self._mol_kg(self._comp.sulfur.s6_wt,           ELEMENT_MASSES['s'])

        return (
            fe2_mol_kg    *  0.50 +    # Fe + ½O₂ → FeO          (+½    O₂/Fe)
            fe3_mol_kg    *  0.75 +    # Fe + ¾O₂ → ½Fe₂O₃      (+¾    O₂/Fe)
            c4_mol_kg     *  1.00 +    # C  +  O₂ → CO₂          (+1    O₂/C)
            s2minus_mol_kg * -0.50 +   # phantom-O monosulfide    (−½    O₂/S)
            s1minus_mol_kg * -0.25 +   # phantom-O disulfide      (−¼    O₂/S)
            s6plus_mol_kg  *  1.50     # S  + 1½O₂ → SO₃         (+1½   O₂/S)
        )

    # =====================================================================
    # PROPERTY: DICTIONARY OF ALL MOL/KG
    # =====================================================================
    
    @property
    def all_mol_kg(self) -> Dict[str, float]:
        """
        Returns dictionary {cation_symbol: mol/kg} for all species.
        
        Keys map directly to column 3 (mol pfu) in UI.
        
        Returns:
            {
                'Si': mol/kg, 'Ti': mol/kg, ..., 'S2': mol/kg
            }
        """
        return {
            'Si': self.si_mol_kg,
            'Ti': self.ti_mol_kg,
            'Al': self.al_mol_kg,
            'Cr': self.cr_mol_kg,
            'Mn': self.mn_mol_kg,
            'Mg': self.mg_mol_kg,
            'Ca': self.ca_mol_kg,
            'Ni': self.ni_mol_kg,
            'Na': self.na_mol_kg,
            'K':  self.k_mol_kg,
            'P':  self.p_mol_kg,
            'H2': self.h2_mol_kg,
            'Fe': self.fe_mol_kg,
            'C':  self.c_mol_kg,
            'S2':  self.s2_mol_kg,
            'O2':  self.o2_mol_kg,
        }