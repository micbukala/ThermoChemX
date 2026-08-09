# ThermoChemX — Copyright (C) 2026  Michał Bukała <michal.bukala@csic.es>
# This program is free software: GNU General Public License v3 or later.
# It comes with ABSOLUTELY NO WARRANTY. See LICENSE.txt for details.

"""
Sulfur redox system: 
maintains total S, SO₃/ΣS, and S¹⁻/ΣS(red) as the single source of truth and derives sulfate, disulfide, and monosulfide species on demand.
"""

from ...utils.constants import ELEMENT_MASSES, OXIDE_MASSES

class SulfurSystem:
    def __init__(self):
        # ---------------------------------------------------------
        # SSoT (Only these 2 variables hold state!)
        # MUST HAVE underscore "_" prefix to avoid conflicts with @property!
        # ---------------------------------------------------------
        self._s_wt: float = 0.0         # Total elemental sulfur [wt.%]
        self._so3_ratio: float = 0.0    # Molar ratio: oxidized(SO3) / total_S (s_wt)
        self._s1_ratio: float = 0.0      # Molar ratio: S(1-) / S_sulfide (reduced)
                                         # Default 0.0 -> all reduced sulfur is S(2-)
    # =================================================================
    # 1. BASE PARAMETERS (S_total and SO3_total)
    # =================================================================

    @property
    def s_wt(self) -> float:
        """Total sulfur as element S [wt.%]"""
        return self._s_wt

    @s_wt.setter
    def s_wt(self, value: float):
        self._s_wt = max(0.0, value)

    @property
    def so3_wt(self) -> float:
        """Total sulfur expressed as oxide SO3 [wt.%]"""
        conversion_factor = OXIDE_MASSES['so3'] / ELEMENT_MASSES['s']
        return self._s_wt * conversion_factor

    @so3_wt.setter
    def so3_wt(self, value: float):
        """Sets total sulfur based on value entered as SO3_tot"""
        conversion_factor = ELEMENT_MASSES['s'] / OXIDE_MASSES['so3']
        self._s_wt = max(0.0, value) * conversion_factor

    # =================================================================
    # 2. SULFUR REDOX RATIO
    # =================================================================

    @property
    def so3_stot_ratio(self) -> float:
        """Molar ratio S(oxidized) / S(total)"""
        return self._so3_ratio

    @so3_stot_ratio.setter
    def so3_stot_ratio(self, value: float):
        self._so3_ratio = max(0.0, min(1.0, value))

    @property
    def s1_sred_ratio(self) -> float:
        """Ratio of S(1-) to total reduced sulfur (sulfidic)"""
        return self._s1_ratio

    @s1_sred_ratio.setter
    def s1_sred_ratio(self, value: float):
        self._s1_ratio = max(0.0, min(1.0, value))

    # =================================================================
    # 3. REAL SPECIES (Calculated on-the-fly)
    # =================================================================

    @property
    def s6_wt(self) -> float:
        """Oxidized sulfur (sulfate) as element S [wt.%]"""
        return self._s_wt * self._so3_ratio

    @s6_wt.setter
    def s6_wt(self, new_s_in_sulfate: float):
        """Update SSoT while preserving current sulfide amount"""
        current_sulfide = self.s_red_wt
        self._s_wt = current_sulfide + new_s_in_sulfate

        if self._s_wt > 0:
            self._so3_ratio = new_s_in_sulfate / self._s_wt
        else:
            self._so3_ratio = 0.0

    @property
    def s_red_wt(self) -> float:
        """Reduced sulfur (sulfide) as element S [wt.%]"""
        return self._s_wt * (1.0 - self._so3_ratio)

    @s_red_wt.setter
    def s_red_wt(self, new_sulfide: float):
        """Update SSoT while preserving current sulfate amount"""
        current_s_in_sulfate = self._s_wt * self._so3_ratio
        self._s_wt = current_s_in_sulfate + new_sulfide

        if self._s_wt > 0:
            self._so3_ratio = current_s_in_sulfate / self._s_wt
        else:
            self._so3_ratio = 0.0

    # --- Microgram units (μg/g) for GUI ---

    @property
    def s_red_ugg(self) -> float:
        return self.s_red_wt * 1e4

    @s_red_ugg.setter
    def s_red_ugg(self, value: float):
        self.s_red_wt = value / 1e4

    @property
    def s6_ugg(self) -> float:
        return self.s6_wt * 1e4

    @s6_ugg.setter
    def s6_ugg(self, value: float):
        self.s6_wt = value / 1e4

    @property
    def total_s_ugg(self) -> float:
        return self._s_wt * 1e4

    @total_s_ugg.setter
    def total_s_ugg(self, value: float):
        self._s_wt = value / 1e4

    @property
    def s1_ugg(self) -> float:
        return self.s1_wt * 1e4

    @s1_ugg.setter
    def s1_ugg(self, value: float):
        self.s1_wt = value / 1e4

    @property
    def s2_ugg(self) -> float:
        return self.s2_wt * 1e4

    @s2_ugg.setter
    def s2_ugg(self, value: float):
        self.s2_wt = value / 1e4

    # --- Specific for oxide sum ---

    @property
    def s6_oxide_wt(self) -> float:
        """Actual mass of SO3 as equivalent of S in sulfates for oxide summation [wt.%]"""
        conversion_factor = OXIDE_MASSES['so3'] / ELEMENT_MASSES['s']
        return self.s6_wt * conversion_factor

    # ---------------------------------------------------

    @property
    def s1_wt(self) -> float:
        """Sulfur S(1-) (e.g., in pyrite) [wt.%]"""
        return self.s_red_wt * self._s1_ratio

    @s1_wt.setter
    def s1_wt(self, new_s1_value: float):
        """
        Update SSoT while preserving current amount of S(2-).
        When user enters S(1-), we preserve S(2-) and recalculate total sulfur.
        """
        # 1. Preserve current S(2-)
        current_s2 = self.s2_wt

        # 2. Update total reduced sulfur
        new_sulfide_total = new_s1_value + current_s2

        # 3. Update SSoT for total sulfur (preserve sulfates)
        current_sulfate = self._s_wt * self._so3_ratio
        self._s_wt = current_sulfate + new_sulfide_total

        # 4. Update oxidation ratio
        if self._s_wt > 0:
            self._so3_ratio = current_sulfate / self._s_wt
        else:
            self._so3_ratio = 0.0

        # 5. Update sulfide redox ratio
        if new_sulfide_total > 0:
            self._s1_ratio = new_s1_value / new_sulfide_total
        else:
            self._s1_ratio = 0.0

    @property
    def s2_wt(self) -> float:
        """Sulfur S(2-) (standard sulfides) [wt.%]"""
        return self.s_red_wt * (1.0 - self._s1_ratio)

    @s2_wt.setter
    def s2_wt(self, new_s2_value: float):
        """
        Update SSoT while preserving current amount of S(1-).
        When user enters S(2-), we preserve S(1-) and recalculate total sulfur.
        """
        # 1. Preserve current S(1-)
        current_s1 = self.s1_wt

        # 2. Update total reduced sulfur
        new_sulfide_total = current_s1 + new_s2_value

        # 3. Update SSoT for total sulfur (preserve sulfates)
        current_sulfate = self._s_wt * self._so3_ratio
        self._s_wt = current_sulfate + new_sulfide_total

        # 4. Update oxidation ratio
        if self._s_wt > 0:
            self._so3_ratio = current_sulfate / self._s_wt
        else:
            self._so3_ratio = 0.0

        # 5. Update sulfide redox ratio
        if new_sulfide_total > 0:
            self._s1_ratio = current_s1 / new_sulfide_total
        else:
            self._s1_ratio = 0.0
