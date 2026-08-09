# ThermoChemX — Copyright (C) 2026  Michał Bukała <michal.bukala@csic.es>
# This program is free software: GNU General Public License v3 or later.
# It comes with ABSOLUTELY NO WARRANTY. See LICENSE.txt for details.

"""Atomic and molecular masses used throughout the composition calculations."""

from types import MappingProxyType

# 1. Base: element atomic masses 
# Element atomic masses, consistent with dew24hp622ver_elements.dat (Perple_X 7.2.1).
# Deliberately NOT the IUPAC 2021 values (Prohaska et al. 2022): output must be
# bit-consistent with hand-calculated Perple_X input. Max. relative deviation
# from IUPAC 2021: 2.5e-4 (H), three orders below analytical uncertainty.

_ELEMENT_MASSES = {
    'si': 28.0850,
    'ti': 47.8670,
    'al': 26.9812,
    'fe': 55.8445,
    'mn': 54.9375,
    'mg': 24.3045,
    'ca': 40.0775,
    'na': 22.9898,
    'k':  39.0983,
    'p':  30.97,
    'ni': 58.6935,
    'cr': 51.9958,
    'h':  1.00775,
    'c':  12.0110,
    's':  32.0650,
    'o':  15.9995
}

# 2. Oxide molar masses.
_OXIDE_MASSES = {
    'sio2':  _ELEMENT_MASSES['si'] + 2 * _ELEMENT_MASSES['o'],
    'tio2':  _ELEMENT_MASSES['ti'] + 2 * _ELEMENT_MASSES['o'],
    'al2o3': 2 * _ELEMENT_MASSES['al'] + 3 * _ELEMENT_MASSES['o'],
    'feo':   _ELEMENT_MASSES['fe'] + _ELEMENT_MASSES['o'],
    'fe2o3': 2 * _ELEMENT_MASSES['fe'] + 3 * _ELEMENT_MASSES['o'],
    'mno':   _ELEMENT_MASSES['mn'] + _ELEMENT_MASSES['o'],
    'mgo':   _ELEMENT_MASSES['mg'] + _ELEMENT_MASSES['o'],
    'cao':   _ELEMENT_MASSES['ca'] + _ELEMENT_MASSES['o'],
    'na2o':  2 * _ELEMENT_MASSES['na'] + _ELEMENT_MASSES['o'],
    'k2o':   2 * _ELEMENT_MASSES['k'] + _ELEMENT_MASSES['o'],
    'p2o5':  2 * _ELEMENT_MASSES['p'] + 5 * _ELEMENT_MASSES['o'],
    'nio':   _ELEMENT_MASSES['ni'] + _ELEMENT_MASSES['o'],
    'cr2o3': 2 * _ELEMENT_MASSES['cr'] + 3 * _ELEMENT_MASSES['o'],
    'h2o':   2 * _ELEMENT_MASSES['h'] + _ELEMENT_MASSES['o'],
    'co2':   _ELEMENT_MASSES['c'] + 2 * _ELEMENT_MASSES['o'],
    'so3':   _ELEMENT_MASSES['s'] + 3 * _ELEMENT_MASSES['o'],
    
}

# 3. Molar masses of Perple_X basis components (mol/kg basis).
# Keys correspond to those in MolarModel.all_mol_kg.
_BASIS_COMPONENT_MASSES = {
    'Si': _ELEMENT_MASSES['si'],
    'Ti': _ELEMENT_MASSES['ti'],
    'Al': _ELEMENT_MASSES['al'],
    'Cr': _ELEMENT_MASSES['cr'],
    'Mn': _ELEMENT_MASSES['mn'],
    'Mg': _ELEMENT_MASSES['mg'],
    'Ca': _ELEMENT_MASSES['ca'],
    'Ni': _ELEMENT_MASSES['ni'],
    'Na': _ELEMENT_MASSES['na'],
    'K':  _ELEMENT_MASSES['k'],
    'P':  _ELEMENT_MASSES['p'],
    'H2': 2 * _ELEMENT_MASSES['h'],
    'Fe': _ELEMENT_MASSES['fe'],
    'C':  _ELEMENT_MASSES['c'],
    'S2': 2 * _ELEMENT_MASSES['s'],
    'O2': 2 * _ELEMENT_MASSES['o'],
}

# 4. Export: freeze the dicts to make them read-only (thread-safe & mutation-safe)
ELEMENT_MASSES = MappingProxyType(_ELEMENT_MASSES)
OXIDE_MASSES = MappingProxyType(_OXIDE_MASSES)
BASIS_COMPONENT_MASSES = MappingProxyType(_BASIS_COMPONENT_MASSES)

# Additional thermodynamic constants, exported for use elsewhere if needed
GAS_CONST_R = 8.31446261815324  # J/(mol*K)