# ThermoChemX — Copyright (C) 2026  Michał Bukała <michal.bukala@csic.es>
# This program is free software: GNU General Public License v3 or later.
# It comes with ABSOLUTELY NO WARRANTY. See LICENSE.txt for details.

"""
Iron redox system: 
maintains total Fe and the Fe³⁺/ΣFe ratio as the single source of truth and derives all other iron representations on demand.
"""

from ...utils.constants import ELEMENT_MASSES, OXIDE_MASSES


class IronSystem:
    def __init__(self):
        # ---------------------------------------------------------
        # SSoT (Only these 2 variables hold state!)
        # MUST HAVE underscore "_" prefix to avoid conflicts with @property!
        # ---------------------------------------------------------
        self._fe2o3_tot_wt: float = 0.0  
        self._fe3_ratio: float = 0.0     # Molar Fe3+ / Fe_total

    # =================================================================
    # 1. BASE PARAMETERS (Direct access to SSoT)
    # =================================================================

    @property
    def fe2o3_tot_wt(self) -> float:
        return self._fe2o3_tot_wt

    @fe2o3_tot_wt.setter
    def fe2o3_tot_wt(self, value: float):
        self._fe2o3_tot_wt = max(0.0, value)

    @property
    def fe3_fetot_ratio(self) -> float:
        return self._fe3_ratio

    @fe3_fetot_ratio.setter
    def fe3_fetot_ratio(self, value: float):
        self._fe3_ratio = max(0.0, min(1.0, value))

    # =================================================================
    # 2. DERIVED PARAMETERS (Calculated on-the-fly)
    # =================================================================

    # ---------------------------------------------------
    # FeO TOTAL (Total iron as FeO)
    # ---------------------------------------------------
    @property
    def feo_tot_wt(self) -> float:
        """
        Returns: Total iron expressed as FeO [wt. %].
        Depends on: fe2o3_tot_wt
        """
        conversion_factor = (2 * OXIDE_MASSES['feo']) / OXIDE_MASSES['fe2o3']
        return self._fe2o3_tot_wt * conversion_factor

    @feo_tot_wt.setter
    def feo_tot_wt(self, value: float):
        """
        If user enters FeO_tot_wt, we recalculate it back to Fe2O3_tot_wt.
        Ratio remains unchanged!
        """
        conversion_factor = (2 * OXIDE_MASSES['feo']) / OXIDE_MASSES['fe2o3']
        self._fe2o3_tot_wt = value / conversion_factor 


    # ---------------------------------------------------
    # Fe2O3 (Real, oxidized)
    # ---------------------------------------------------
    @property
    def fe3_oxide_wt(self) -> float:
        """
        Returns: Real mass of oxidized iron (Fe2O3) in rock.
        Depends on: fe2o3_tot_wt, fe3_fetot_ratio
        """
        return self._fe2o3_tot_wt * self._fe3_ratio

    @fe3_oxide_wt.setter
    def fe3_oxide_wt(self, new_fe2o3_wt: float):
        """
        User provided new Fe2O3_wt directly in table.
        Must calculate new Total and new Ratio, preserving current FeO content (reduced iron)!
        """
        # 1. How much real FeO do we currently have?
        current_feo_wt = self.fe2_oxide_wt
        
        # 2. Convert both forms to moles of iron (Fe) so we can sum them
        moles_fe3 = (new_fe2o3_wt / OXIDE_MASSES['fe2o3']) * 2.0
        moles_fe2 = (current_feo_wt / OXIDE_MASSES['feo'])
        
        total_moles_fe = moles_fe3 + moles_fe2
        
        if total_moles_fe > 0:
            # Update SSoT: New molar ratio
            self._fe3_ratio = moles_fe3 / total_moles_fe
            # Update SSoT: New total Fe2O3
            self._fe2o3_tot_wt = (total_moles_fe / 2.0) * OXIDE_MASSES['fe2o3']
        else:
            self._fe3_ratio = 0.0
            self._fe2o3_tot_wt = 0.0

    # ---------------------------------------------------
    # FeO (Real, reduced)
    # ---------------------------------------------------
    @property
    def fe2_oxide_wt(self) -> float:
        """
        Returns: Real mass of reduced iron (FeO) in rock.
        Depends on: feo_tot_wt, fe3_fetot_ratio
        """
        # Reduced iron is simply 1 minus oxidized
        return self.feo_tot_wt * (1.0 - self._fe3_ratio)

    @fe2_oxide_wt.setter
    def fe2_oxide_wt(self, new_feo_wt: float):
        """
        User provided new FeO_wt directly in table.
        Update Total and Ratio, preserving current Fe2O3_wt.
        """
        # 1. How much real Fe2O3 do we currently have?
        current_fe2o3_wt = self.fe3_oxide_wt
        
        # 2. Moles
        moles_fe3 = (current_fe2o3_wt / OXIDE_MASSES['fe2o3']) * 2.0
        moles_fe2 = (new_feo_wt / OXIDE_MASSES['feo'])
        
        total_moles_fe = moles_fe3 + moles_fe2
        
        if total_moles_fe > 0:
            self._fe3_ratio = moles_fe3 / total_moles_fe
            self._fe2o3_tot_wt = (total_moles_fe / 2.0) * OXIDE_MASSES['fe2o3']
        else:
            self._fe3_ratio = 0.0
            self._fe2o3_tot_wt = 0.0

    # ---------------------------------------------------
    # Fe2+ (elemental, reduced) — raw wt.% of sample
    # ---------------------------------------------------
    @property
    def fe2_wt(self) -> float:
        """Mass of Fe in 2+ state expressed as elemental Fe [wt.% of sample]."""
        return self.fe2_oxide_wt * (ELEMENT_MASSES['fe'] / OXIDE_MASSES['feo'])

    @fe2_wt.setter
    def fe2_wt(self, new_fe2_wt: float):
        """
        Set Fe2+ elemental wt%, preserving current Fe3+ elemental wt%.
        Back-calculates SSoT (_fe2o3_tot_wt, _fe3_ratio).
        """
        current_fe3 = self.fe3_wt
        moles_fe2 = max(0.0, new_fe2_wt) / ELEMENT_MASSES['fe']
        moles_fe3 = current_fe3 / ELEMENT_MASSES['fe']
        total_moles_fe = moles_fe2 + moles_fe3

        if total_moles_fe > 0:
            self._fe3_ratio = moles_fe3 / total_moles_fe
            self._fe2o3_tot_wt = (total_moles_fe / 2.0) * OXIDE_MASSES['fe2o3']
        else:
            self._fe3_ratio = 0.0
            self._fe2o3_tot_wt = 0.0

    # ---------------------------------------------------
    # Fe3+ (elemental, oxidized) — raw wt.% of sample
    # ---------------------------------------------------
    @property
    def fe3_wt(self) -> float:
        """Mass of Fe in 3+ state expressed as elemental Fe [wt.% of sample]."""
        return self.fe3_oxide_wt * (2.0 * ELEMENT_MASSES['fe'] / OXIDE_MASSES['fe2o3'])

    @fe3_wt.setter
    def fe3_wt(self, new_fe3_wt: float):
        """
        Set Fe3+ elemental wt%, preserving current Fe2+ elemental wt%.
        Back-calculates SSoT (_fe2o3_tot_wt, _fe3_ratio).
        """
        current_fe2 = self.fe2_wt
        moles_fe3 = max(0.0, new_fe3_wt) / ELEMENT_MASSES['fe']
        moles_fe2 = current_fe2 / ELEMENT_MASSES['fe']
        total_moles_fe = moles_fe2 + moles_fe3

        if total_moles_fe > 0:
            self._fe3_ratio = moles_fe3 / total_moles_fe
            self._fe2o3_tot_wt = (total_moles_fe / 2.0) * OXIDE_MASSES['fe2o3']
        else:
            self._fe3_ratio = 0.0
            self._fe2o3_tot_wt = 0.0

    # ---------------------------------------------------
    # Fe2+ / Fe3+ in [μg/g] — convenience views of fe2_wt / fe3_wt
    # ---------------------------------------------------
    @property
    def fe2_ugg(self) -> float:
        """Fe2+ elemental concentration in [μg/g] (1 wt.% = 10,000 μg/g)."""
        return self.fe2_wt * 1e4

    @fe2_ugg.setter
    def fe2_ugg(self, new_fe2_ugg: float):
        self.fe2_wt = new_fe2_ugg / 1e4

    @property
    def fe3_ugg(self) -> float:
        """Fe3+ elemental concentration in [μg/g] (1 wt.% = 10,000 μg/g)."""
        return self.fe3_wt * 1e4

    @fe3_ugg.setter
    def fe3_ugg(self, new_fe3_ugg: float):
        self.fe3_wt = new_fe3_ugg / 1e4
