# ThermoChemX — Copyright (C) 2026  Michał Bukała <michal.bukala@csic.es>
# This program is free software: GNU General Public License v3 or later.
# It comes with ABSOLUTELY NO WARRANTY. See LICENSE.txt for details.

"""
Carbon redox system: 
maintains total C and the CO₂/ΣC ratio as the single source of truth and derives graphite (C⁰) and carbonate (C⁴⁺) species on demand.
"""

from ...utils.constants import ELEMENT_MASSES, OXIDE_MASSES


class CarbonSystem:
    def __init__(self):
        # ---------------------------------------------------------
        # SSoT (Only these 2 variables hold state!)
        # MUST HAVE underscore "_" prefix to avoid conflicts with @property!
        # ---------------------------------------------------------
        self._c_wt: float = 0.0         # Total elemental carbon [wt.%]
        self._co2_ratio: float = 0.0    # Molar ratio: oxidized(CO2) / total_C (c_wt)

    # =================================================================
    # 1. BASE PARAMETERS (Input #1 - Total C)
    # =================================================================

    @property
    def c_wt(self) -> float:
        """User entered/reads total carbon as element C"""
        return self._c_wt

    @c_wt.setter
    def c_wt(self, value: float):
        self._c_wt = max(0.0, value)

    @property
    def co2_wt(self) -> float:
        """User entered/reads total carbon expressed as CO2"""
        conversion_factor = OXIDE_MASSES['co2'] / ELEMENT_MASSES['c']
        return self._c_wt * conversion_factor

    @co2_wt.setter
    def co2_wt(self, value: float):
        conversion_factor = ELEMENT_MASSES['c'] / OXIDE_MASSES['co2']
        self._c_wt = max(0.0, value) * conversion_factor

    # =================================================================
    # 2. CARBON REDOX RATIO
    # =================================================================

    @property
    def co2_ctot_ratio(self) -> float:
        return self._co2_ratio

    @co2_ctot_ratio.setter
    def co2_ctot_ratio(self, value: float):
        self._co2_ratio = max(0.0, min(1.0, value))

    # =================================================================
    # 3. REAL SPECIES (Calculated on-the-fly)
    # =================================================================

    @property
    def c0_wt(self) -> float:
        """Atomic carbon bound in graphite [wt.%]"""
        return self._c_wt * (1.0 - self._co2_ratio)

    @c0_wt.setter
    def c0_wt(self, new_graphite: float):
        """
        When user enters new graphite amount directly:
        Preserve current carbonate amount (CO2) and recalculate Total and Ratio!
        """
        # Current oxidized carbon (in carbonates)
        current_c_in_carb = self._c_wt * self._co2_ratio

        # New total carbon (SSoT gets updated)
        self._c_wt = current_c_in_carb + new_graphite

        # New Ratio (SSoT gets updated)
        if self._c_wt > 0:
            self._co2_ratio = current_c_in_carb / self._c_wt
        else:
            self._co2_ratio = 0.0

    @property
    def c4_wt(self) -> float:
        """Atomic carbon bound in carbonates [wt.%]"""
        return self._c_wt * self._co2_ratio

    @c4_wt.setter
    def c4_wt(self, new_c_in_carb: float):
        """
        When user enters new carbonate amount (as C) directly:
        Preserve current graphite amount and recalculate Total and Ratio!
        """
        # Remember current graphite
        current_graphite = self.c0_wt

        # New total carbon (SSoT gets updated)
        self._c_wt = current_graphite + new_c_in_carb

        # New Ratio (SSoT gets updated)
        if self._c_wt > 0:
            self._co2_ratio = new_c_in_carb / self._c_wt
        else:
            self._co2_ratio = 0.0

    @property
    def c0_ugg(self) -> float:
        """Real mass of carbon (reduced C) in [μg/g]"""
        return self.c0_wt * 1e4  # 1 wt.% = 10,000 μg/g

    @c0_ugg.setter
    def c0_ugg(self, new_graphite_ugg: float):
        new_graphite_wt = new_graphite_ugg / 1e4
        self.c0_wt = new_graphite_wt  # This will automatically update SSoT

    @property
    def c4_ugg(self) -> float:
        """Real mass of carbon (oxidized C) expressed as C in [μg/g]"""
        return self.c4_wt * 1e4  # 1 wt.% = 10,000 μg/g

    @c4_ugg.setter
    def c4_ugg(self, new_carbonates_ugg: float):
        new_carbonates_wt = new_carbonates_ugg / 1e4
        self.c4_wt = new_carbonates_wt  # This will automatically update SSoT

    @property
    def total_c_ugg(self) -> float:
        """Total elemental carbon in [μg/g] (wt.% * 10,000)"""
        return self._c_wt * 1e4

    @total_c_ugg.setter
    def total_c_ugg(self, value: float):
        """Sets total carbon by conversion from μg/g to wt.%"""
        self._c_wt = value / 1e4

    # --- Specific for oxide sum ---

    @property
    def c4_oxide_wt(self) -> float:
        """Real CO2 mass as C equivalent in carbonates for oxide summation [wt.%]"""
        conversion_factor = OXIDE_MASSES['co2'] / ELEMENT_MASSES['c']
        return self.c4_wt * conversion_factor
