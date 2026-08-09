# ThermoChemX — Copyright (C) 2026  Michał Bukała <michal.bukala@csic.es>
# This program is free software: GNU General Public License v3 or later.
# It comes with ABSOLUTELY NO WARRANTY. See LICENSE.txt for details.

"""
Tests for the optional comment-column (three-column) import layout.

Gate 4 (plan): two-column and three-column (comment) layouts both parse;
multi-sample horizontal still works.
"""

import os
import tempfile

import pytest

from thermochemx.core.importer import parse_file_multi, apply_to_model
from thermochemx.core.composition import BulkComposition


TOL = 1e-4


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _csv_to_comps(content: str) -> list[BulkComposition]:
    """Write *content* to a temp CSV, parse it, and return loaded BulkCompositions."""
    f = tempfile.NamedTemporaryFile(
        mode="w", suffix=".csv", delete=False, encoding="utf-8"
    )
    f.write(content)
    f.close()
    try:
        samples, _ = parse_file_multi(f.name)
        comps = []
        for s in samples:
            m = BulkComposition()
            apply_to_model(s.data, m)
            comps.append(m)
        return comps
    finally:
        os.unlink(f.name)


# ---------------------------------------------------------------------------
# Reference two-column CSV (legacy form, must keep working)
# ---------------------------------------------------------------------------

TWO_COL = """\
SiO2_wt,50.0
H2O_wt,2.0
Fe2O3_total_wt,10.0
Fe3plus_Fetotal_ratio,0.25
C_total_wt,1.0
C4plus_Ctotal_ratio,0.50
S_total_wt,0.5
S6plus_Stotal_ratio,0.30
S1minus_Ssulfides_ratio,0.40
"""

# Equivalent three-column comment CSV
THREE_COL = """\
SiO\u2082 (wt%),SiO2_wt,50.0
H\u2082O (wt%),H2O_wt,2.0
total iron as Fe\u2082O\u2083 (wt%),Fe2O3_total_wt,10.0
Fe\u00b3\u207a/\u03a3Fe molar ratio,Fe3plus_Fetotal_ratio,0.25
total carbon as element (wt%),C_total_wt,1.0
C\u2074\u207a/\u03a3C ratio,C4plus_Ctotal_ratio,0.50
total sulfur as element (wt%),S_total_wt,0.5
S\u2076\u207a/\u03a3S ratio,S6plus_Stotal_ratio,0.30
S\u00b9\u207b/\u03a3S(reduced) ratio,S1minus_Ssulfides_ratio,0.40
"""


class TestTwoColumnBackwardCompat:

    def test_two_column_parses(self):
        comps = _csv_to_comps(TWO_COL)
        assert len(comps) == 1

    def test_two_column_ssot_values(self):
        m = _csv_to_comps(TWO_COL)[0]
        assert abs(m.get_oxide_wt("SiO2")      - 50.0) < TOL
        assert abs(m.get_oxide_wt("H2O")       - 2.0)  < TOL
        assert abs(m.iron.fe2o3_tot_wt         - 10.0) < TOL
        assert abs(m.iron.fe3_fetot_ratio      - 0.25) < TOL
        assert abs(m.carbon.c_wt               - 1.0)  < TOL
        assert abs(m.carbon.co2_ctot_ratio     - 0.50) < TOL
        assert abs(m.sulfur.s_wt               - 0.5)  < TOL
        assert abs(m.sulfur.so3_stot_ratio     - 0.30) < TOL
        assert abs(m.sulfur.s1_sred_ratio      - 0.40) < TOL


class TestThreeColumnCommentLayout:

    def test_three_column_parses(self):
        comps = _csv_to_comps(THREE_COL)
        assert len(comps) == 1

    def test_three_column_same_ssot_as_two_column(self):
        """Three-column comment form and two-column form yield bit-identical SSoT."""
        two = _csv_to_comps(TWO_COL)[0]
        three = _csv_to_comps(THREE_COL)[0]

        assert abs(two.get_oxide_wt("SiO2")  - three.get_oxide_wt("SiO2"))  < TOL
        assert abs(two.get_oxide_wt("H2O")   - three.get_oxide_wt("H2O"))   < TOL
        assert abs(two.iron.fe2o3_tot_wt     - three.iron.fe2o3_tot_wt)     < TOL
        assert abs(two.iron.fe3_fetot_ratio  - three.iron.fe3_fetot_ratio)  < TOL
        assert abs(two.carbon.c_wt           - three.carbon.c_wt)           < TOL
        assert abs(two.carbon.co2_ctot_ratio - three.carbon.co2_ctot_ratio) < TOL
        assert abs(two.sulfur.s_wt           - three.sulfur.s_wt)           < TOL
        assert abs(two.sulfur.so3_stot_ratio - three.sulfur.so3_stot_ratio) < TOL
        assert abs(two.sulfur.s1_sred_ratio  - three.sulfur.s1_sred_ratio)  < TOL

    def test_three_column_comment_ignored(self):
        """Description column does not bleed into any setter."""
        m = _csv_to_comps(THREE_COL)[0]
        # If description column were mis-parsed as a key, some oxide would be wrong.
        assert m.get_oxide_wt("SiO2") == pytest.approx(50.0, abs=TOL)

    def test_three_column_with_sample_name_row(self):
        """sample_name row in col1 is detected correctly in comment layout."""
        csv = (
            "Description,key,MySample\n"
            "sample label,sample_name,MySample\n"
            "SiO\u2082 (wt%),SiO2_wt,55.0\n"
        )
        comps = _csv_to_comps(csv)
        assert len(comps) == 1
        assert abs(comps[0].get_oxide_wt("SiO2") - 55.0) < TOL


class TestThreeColumnMultiSample:

    def test_multi_sample_comment_layout(self):
        """Three-column comment form with multiple samples."""
        csv = (
            "Description,key,Sample_A,Sample_B\n"
            "sample label,sample_name,Sample_A,Sample_B\n"
            "SiO\u2082 (wt%),SiO2_wt,50.0,60.0\n"
            "total iron as Fe\u2082O\u2083 (wt%),Fe2O3_total_wt,10.0,8.0\n"
            "Fe\u00b3\u207a/\u03a3Fe ratio,Fe3plus_Fetotal_ratio,0.30,0.20\n"
        )
        comps = _csv_to_comps(csv)
        assert len(comps) == 2
        assert abs(comps[0].get_oxide_wt("SiO2") - 50.0) < TOL
        assert abs(comps[1].get_oxide_wt("SiO2") - 60.0) < TOL
        assert abs(comps[0].iron.fe2o3_tot_wt - 10.0) < TOL
        assert abs(comps[1].iron.fe2o3_tot_wt - 8.0)  < TOL
        assert abs(comps[0].iron.fe3_fetot_ratio - 0.30) < TOL
        assert abs(comps[1].iron.fe3_fetot_ratio - 0.20) < TOL


class TestHorizontalMultiSampleUnchanged:
    """Horizontal (transposed) multi-sample CSV must still work after changes."""

    def test_horizontal_two_sample(self):
        csv = (
            "sample_name,Sample_A,Sample_B\n"
            "SiO2_wt,50.0,60.0\n"
            "Fe2O3_total_wt,10.0,8.0\n"
            "Fe3plus_Fetotal_ratio,0.25,0.20\n"
        )
        comps = _csv_to_comps(csv)
        assert len(comps) == 2
        assert abs(comps[0].get_oxide_wt("SiO2") - 50.0) < TOL
        assert abs(comps[1].get_oxide_wt("SiO2") - 60.0) < TOL
        assert abs(comps[0].iron.fe2o3_tot_wt - 10.0) < TOL
        assert abs(comps[1].iron.fe2o3_tot_wt - 8.0)  < TOL

    def test_horizontal_three_sample(self):
        csv = (
            "sample_name,A,B,C\n"
            "SiO2_wt,50.0,55.0,60.0\n"
            "Fe2O3_total_wt,10.0,9.0,8.0\n"
        )
        comps = _csv_to_comps(csv)
        assert len(comps) == 3
        assert abs(comps[0].get_oxide_wt("SiO2") - 50.0) < TOL
        assert abs(comps[1].get_oxide_wt("SiO2") - 55.0) < TOL
        assert abs(comps[2].get_oxide_wt("SiO2") - 60.0) < TOL
