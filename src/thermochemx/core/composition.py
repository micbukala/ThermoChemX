# ThermoChemX — Copyright (C) 2026  Michał Bukała <michal.bukala@csic.es>
# This program is free software: GNU General Public License v3 or later.
# It comes with ABSOLUTELY NO WARRANTY. See LICENSE.txt for details.

"""Central stateful composition model: stores independent user inputs for all 
oxide, iron, carbon, and sulfur systems and derives all dependent quantities on demand."""

from typing import Dict
from .systems.iron import IronSystem
from .systems.carbon import CarbonSystem
from .systems.sulfur import SulfurSystem
from .model import MolarModel
from ..utils.constants import OXIDE_MASSES, ELEMENT_MASSES, BASIS_COMPONENT_MASSES
from PySide6.QtCore import QObject, Signal # Imports must be!

class BulkComposition(QObject): # Must inherit from QObject!
    compositionChanged = Signal()

    def __init__(self):
        super().__init__()
        
        self.iron = IronSystem()
        self.carbon = CarbonSystem()
        self.sulfur = SulfurSystem()

        self._simple_oxides: Dict[str, float] = {
            'SiO2': 0.0, 
            'TiO2': 0.0, 
            'Al2O3': 0.0, 
            'Cr2O3': 0.0, 
            'MnO': 0.0, 
            'MgO': 0.0, 
            'CaO': 0.0, 
            'NiO': 0.0, 
            'Na2O': 0.0, 
            'K2O': 0.0, 
            'P2O5': 0.0, 
            'H2O': 0.0
        }

        self.loi_measured: float = 0.0
        self.sample_name: str = ""

        # Volatile mode:
        # "direct"     — both H2O and LOI imported, both static
        # "h2o_derived" — LOI imported, H2O = LOI - CO2 - SO3
        # "loi_derived" — LOI NOT imported, LOI = H2O + CO2 + SO3 (default)
        self._volatile_mode: str = "loi_derived"
        
        # Initialize calculation engine PFU
        self.model = MolarModel(self)
    
    def emit_updated(self):
        """Helper method to trigger GUI refresh"""
        self.compositionChanged.emit()

    # --- Simple oxide management ---
    def set_oxide_wt(self, label: str, value: float) -> None:
        """Sets wt.% value for simple oxide."""
        if label in self._simple_oxides:
            self._simple_oxides[label] = max(0.0, value)

    def get_oxide_wt(self, label: str) -> float:
        """Gets wt.% value for simple oxide. H2O is computed in h2o_derived mode."""
        if label == 'H2O' and self._volatile_mode == "h2o_derived":
            return max(0.0, self.loi_measured - self.carbon.co2_wt - self.sulfur.so3_wt)
        return self._simple_oxides.get(label, 0.0)

    # --- Calculated properties (Properties) ---
    
    @property
    def loi_display(self) -> float:
        """LOI value for display. Computed reactively in loi_derived mode."""
        if self._volatile_mode == "loi_derived":
            return self.get_oxide_wt('H2O') + self.carbon.co2_wt + self.sulfur.so3_wt
        return self.loi_measured

    @property
    def total_calculated(self) -> float:
        """
        Sum of all entered oxides (Raw version).
        Uses Fe2O3_total and measured C and S values.
        """
        sum_simple = sum(self.get_oxide_wt(k) for k in self._simple_oxides)
        return (sum_simple + 
                self.iron.fe2o3_tot_wt + 
                self.carbon.co2_wt + 
                self.sulfur.so3_wt)

    
    @property
    def total_model(self) -> float:
        """
        Real model sum (accounts for redox speciation).
        Graphite and sulfides enter as bare elements (no oxygen); carbonates
        and sulfate enter with their actual oxygen (co2_real_wt, so3_real_wt).
        Used to check analysis quality (should be close to 100%).
        """
        sum_simple_dry = sum(val for k, val in self._simple_oxides.items() if k != 'H2O')
        return (sum_simple_dry +
                self.iron.fe2_oxide_wt +
                self.iron.fe3_oxide_wt +
                self.carbon.c4_oxide_wt +
                self.carbon.c0_wt +
                self.sulfur.s6_oxide_wt +
                self.sulfur.s_red_wt +
                self.get_oxide_wt('H2O'))
    
    # =================================================================
    # REDOX SPECIES (wt.% elements normalized to total_model)
    # =================================================================
    
    @property
    def fe2_norm_wt(self) -> float:
        """
        Returns: Amount of Fe²⁺ as wt.% element (normalized to 100%).
        Depends on: iron.fe2_oxide_wt, total_model_redox_corrected
        """
        if self.total_model_redox_corrected <= 0:
            return 0.0
        return self.iron.fe2_oxide_wt * (ELEMENT_MASSES['fe'] / OXIDE_MASSES['feo']) * 100 / self.total_model_redox_corrected

    @property
    def fe3_norm_wt(self) -> float:
        """
        Returns: Amount of Fe³⁺ as wt.% element (normalized to 100%).
        Depends on: iron.fe3_oxide_wt, total_model_redox_corrected
        """
        if self.total_model_redox_corrected <= 0:
            return 0.0
        return self.iron.fe3_oxide_wt * (2 * ELEMENT_MASSES['fe'] / OXIDE_MASSES['fe2o3']) * 100 / self.total_model_redox_corrected

    @property
    def c0_norm_wt(self) -> float:
        """Amount of C⁰ (graphite) as wt.% element normalized to total_model_redox_corrected."""
        if self.total_model_redox_corrected <= 0:
            return 0.0
        return self.carbon.c0_wt * 100 / self.total_model_redox_corrected

    @property
    def c4_norm_wt(self) -> float:
        """Amount of C⁴⁺ (carbonates) as wt.% element normalized to total_model_redox_corrected."""
        if self.total_model_redox_corrected <= 0:
            return 0.0
        return self.carbon.c4_wt * 100 / self.total_model_redox_corrected

    @property
    def s6_norm_wt(self) -> float:
        """Amount of S⁶⁺ (sulfate) as wt.% element normalized to total_model_redox_corrected."""
        if self.total_model_redox_corrected <= 0:
            return 0.0
        return self.sulfur.s6_wt * 100 / self.total_model_redox_corrected

    @property
    def s1_norm_wt(self) -> float:
        """Amount of S¹⁻ (disulfide/pyrite) as wt.% element normalized to total_model_redox_corrected."""
        if self.total_model_redox_corrected <= 0:
            return 0.0
        return self.sulfur.s1_wt * 100 / self.total_model_redox_corrected

    @property
    def s2_norm_wt(self) -> float:
        """Amount of S²⁻ (monosulfide) as wt.% element normalized to total_model_redox_corrected."""
        if self.total_model_redox_corrected <= 0:
            return 0.0
        return self.sulfur.s2_wt * 100 / self.total_model_redox_corrected

    @property
    def phantom_o_from_sulfide_wt(self) -> float:
        """
        Mass of phantom oxygen (wt.%) implied by XRF convention for sulfide-bearing
        phases. Only sulfide species carry phantom oxygen:
          - S²⁻ (monosulfide): 1 atom O displaced per S  → coefficient 1.0
          - S¹⁻ (disulfide/pyrite): 0.5 atom O displaced per S → coefficient 0.5
        Sulfate (S⁶⁺) oxygen is real and must NOT be included.

        NOTE: Do NOT simplify to (M_O/M_S)*s_sulfide_wt — that over-counts
        phantom-O for any composition containing S¹⁻ (pyrite).
        """
        return (ELEMENT_MASSES['o'] / ELEMENT_MASSES['s']) * (
            1.0 * self.sulfur.s2_wt +
            0.5 * self.sulfur.s1_wt
        )

    @property
    def total_model_redox_corrected(self) -> float:
        """
        Redox- and convention-corrected mass sum used as denominator for mol/kg
        normalisation (Perple_X basis). Equals total_model minus the phantom
        oxygen mass introduced by reporting sulfide metals as oxides.
        Should be close to 100% for a well-determined analysis.
        """
        return self.total_model - self.phantom_o_from_sulfide_wt

    @property
    def model_mass_redox_corrected(self) -> float:
        """
        Independent mass-closure check: Σ(mol_i/kg × M_i) over all Perple_X
        basis components. Should equal 1000.0 g/kg when total_model_redox_corrected
        is the correct normalisation denominator.
        """
        mol_kg = self.model.all_mol_kg
        return sum(mol_kg[k] * BASIS_COMPONENT_MASSES[k] for k in BASIS_COMPONENT_MASSES)


    @property
    def snapshot_dict(self) -> Dict[str, object]:
        """
        Returns complete composition state as an ordered dict for the export
        snapshot.  Built by iterating SNAPSHOT_SCHEMA so that key names,
        ordering, and the input/derived distinction live in one place.

        Used in generate_snapshot() for batch export.
        """
        from collections import OrderedDict
        from .composition_schema import SNAPSHOT_SCHEMA
        d = OrderedDict()
        for f in SNAPSHOT_SCHEMA:
            d[f.file_key] = f.get(self)
        return d

