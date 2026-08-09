# ThermoChemX — Copyright (C) 2026  Michał Bukała <michal.bukala@csic.es>
# This program is free software: GNU General Public License v3 or later.
# It comes with ABSOLUTELY NO WARRANTY. See LICENSE.txt for details.

"""
Regression check for the PerplexElementAdapter wrapper.

Verifies that ``PerplexElementAdapter.render(result)`` produces output that is
byte-identical to ``PerplexExporter(comp).generate_perplex_data()`` for every
fixture.  This proves the Phase-0 golden lock implicitly covers the adapter too.
"""

from __future__ import annotations

import sys
import os
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from thermochemx.core.composition import BulkComposition
from thermochemx.core.importer import parse_file, apply_to_model
from thermochemx.core.exporter import PerplexExporter
from thermochemx.core.recalc.core import build_recalc_result
from thermochemx.core.targets.perplex_element import PerplexElementAdapter
from thermochemx.core.targets.registry import get_adapter

FIXTURES = Path(__file__).parent / "fixtures"
CASES    = sorted(FIXTURES.glob("*.csv"))


def build_composition(csv_path: Path) -> BulkComposition:
    comp = BulkComposition()
    apply_to_model(parse_file(str(csv_path)), comp)
    return comp


# ---------------------------------------------------------------------------
# 1. Byte-identical output for every fixture
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("csv", CASES, ids=lambda p: p.stem)
def test_render_byte_identical_to_exporter(csv, qapp):
    """
    render() must produce a string byte-for-byte identical to
    PerplexExporter(comp).generate_perplex_data().

    Snapshot output is now deterministic (no timestamp), so full-string
    comparison is valid again.
    """
    comp    = build_composition(csv)
    result  = build_recalc_result(comp, sample_name=csv.stem)
    adapter = PerplexElementAdapter()

    rendered, warnings = adapter.render(result)
    expected = PerplexExporter(comp).generate_perplex_data()

    assert not warnings, f"{csv.stem}: unexpected warnings: {warnings}"
    assert rendered == expected, (
        f"{csv.stem}: PerplexElementAdapter.render() differs from "
        f"PerplexExporter.generate_perplex_data().\n"
        f"First differing line:\n"
        + _first_diff(rendered, expected)
    )


# ---------------------------------------------------------------------------
# 2. Registry look-up works and returns a PerplexElementAdapter
# ---------------------------------------------------------------------------

def test_registry_lookup(qapp):
    adapter = get_adapter("perplex_element")
    assert isinstance(adapter, PerplexElementAdapter)


# ---------------------------------------------------------------------------
# 3. inject() is consistent with the existing PerplexExporter template flow
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("csv", CASES, ids=lambda p: p.stem)
def test_inject_consistent_with_exporter(csv, qapp):
    """inject() must produce the same modified template as generate_template_output()."""
    comp    = build_composition(csv)
    result  = build_recalc_result(comp, sample_name=csv.stem)
    adapter = PerplexElementAdapter()

    template = (
        "some header line\n"
        "begin thermodynamic component list\n"
        "Si    1  0.00000      0.00000      0.00000     molar amount\n"
        "end thermodynamic component list\n"
        "some footer\n"
    )

    injected, warnings  = adapter.inject(template, result)
    expected            = PerplexExporter(comp).generate_template_output(template)

    assert not warnings, f"{csv.stem}: unexpected inject warnings: {warnings}"
    assert injected == expected, f"{csv.stem}: inject() differs from generate_template_output()"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _first_diff(got: str, expected: str) -> str:
    for i, (a, b) in enumerate(zip(got.splitlines(), expected.splitlines())):
        if a != b:
            return f"  Line {i + 1}:\n    got:      {a!r}\n    expected: {b!r}"
    return "(lengths differ)"
