# ThermoChemX — Copyright (C) 2026  Michał Bukała <michal.bukala@csic.es>
# This program is free software: GNU General Public License v3 or later.
# It comes with ABSOLUTELY NO WARRANTY. See LICENSE.txt for details.

"""
conftest.py — shared pytest fixtures for ThermoChemX tests.
A QCoreApplication is required for QObject subclasses (BulkComposition).
""" 

import sys
import os
import pytest

# Package root is one level above the project folder
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="session")
def qapp():
    """Session-scoped QApplication needed for QObject instantiation."""
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    yield app


@pytest.fixture
def composition(qapp):
    """Fresh BulkComposition for each test."""
    from thermochemx.core.composition import BulkComposition
    return BulkComposition()
