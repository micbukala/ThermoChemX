# ThermoChemX — Copyright (C) 2026  Michał Bukała <michal.bukala@csic.es>
# This program is free software: GNU General Public License v3 or later.
# It comes with ABSOLUTELY NO WARRANTY. See LICENSE.txt for details.

"""
Golden file generator for the Perple_X element-basis regression lock.

Run after any intentional change to composition output:
    python tests/regression/_generate_golden.py

Or directly:
    python tests/regression/_generate_golden.py

Writes (per fixture):
    golden/{stem}_components.dat  — permanent component-list block (frozen; never regenerate unless physics changes)
    golden/{stem}_snapshot.dat    — versioned snapshot block (format v1; regenerate when format changes)
    golden/{stem}.json            — mol/kg snapshot + redox ratios

The timestamp in snapshot goldens is fixed to GOLDEN_SNAPSHOT_UTC for
determinism.  Tests import and use the same constant.
"""

from __future__ import annotations

import json
import sys
import os
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO_ROOT))

from thermochemx.core.composition import BulkComposition
from thermochemx.core.importer import parse_file, apply_to_model
from thermochemx.core.exporter import PerplexExporter

from PySide6.QtWidgets import QApplication
_qapp = QApplication.instance() or QApplication(sys.argv)

FIXTURES = Path(__file__).parent / "fixtures"
GOLDEN   = Path(__file__).parent / "golden"

# ---------------------------------------------------------------------------
# Expected redox ratios per fixture — fail fast if the importer misread one.
# Tolerance is loose (1e-6) because ratios are stored as floats with no
# further arithmetic; exact equality is expected in practice.
# ---------------------------------------------------------------------------
FIXTURE_GUARDS: dict[str, dict[str, float | None]] = {
    "oxidised":            {"fe3_fetot": 0.85, "co2_ctot": None, "so3_stot": None, "s1_sred": None,
                            "has_carbon": False, "has_sulfur": False},
    "reduced_graphitic":   {"fe3_fetot": 0.05, "co2_ctot": 0.00, "so3_stot": None, "s1_sred": None,
                            "has_carbon": True,  "has_sulfur": False},
    "sulfidic_pyrite":     {"fe3_fetot": 0.10, "co2_ctot": None, "so3_stot": 0.00, "s1_sred": 1.00,
                            "has_carbon": False, "has_sulfur": True},
    "sulfidic_pyrrhotite": {"fe3_fetot": 0.10, "co2_ctot": None, "so3_stot": 0.00, "s1_sred": 0.00,
                            "has_carbon": False, "has_sulfur": True},
    "sulfate":             {"fe3_fetot": 0.60, "co2_ctot": None, "so3_stot": 1.00, "s1_sred": 0.00,
                            "has_carbon": False, "has_sulfur": True},
    "mixed":               {"fe3_fetot": 0.35, "co2_ctot": 0.40, "so3_stot": 0.30, "s1_sred": 0.50,
                            "has_carbon": True,  "has_sulfur": True},
}

RTOL = 1e-6


def _assert_fixture(name: str, comp: BulkComposition) -> None:
    guard = FIXTURE_GUARDS.get(name)
    if guard is None:
        print(f"  [WARN] No fixture guard defined for '{name}' — skipping integrity check.")
        return

    if abs(comp.iron.fe3_fetot_ratio - guard["fe3_fetot"]) > RTOL:
        raise AssertionError(
            f"Fixture '{name}': fe3_fetot_ratio = {comp.iron.fe3_fetot_ratio}, "
            f"expected {guard['fe3_fetot']}"
        )

    if guard["has_carbon"]:
        if comp.carbon.c_wt <= 0:
            raise AssertionError(f"Fixture '{name}': expected carbon, got c_wt = 0")
        if guard["co2_ctot"] is not None and abs(comp.carbon.co2_ctot_ratio - guard["co2_ctot"]) > RTOL:
            raise AssertionError(
                f"Fixture '{name}': co2_ctot_ratio = {comp.carbon.co2_ctot_ratio}, "
                f"expected {guard['co2_ctot']}"
            )
    else:
        if comp.carbon.c_wt > 1e-9:
            raise AssertionError(
                f"Fixture '{name}': expected no carbon, got c_wt = {comp.carbon.c_wt}"
            )

    if guard["has_sulfur"]:
        if comp.sulfur.s_wt <= 0:
            raise AssertionError(f"Fixture '{name}': expected sulfur, got s_wt = 0")
        if guard["so3_stot"] is not None and abs(comp.sulfur.so3_stot_ratio - guard["so3_stot"]) > RTOL:
            raise AssertionError(
                f"Fixture '{name}': so3_stot_ratio = {comp.sulfur.so3_stot_ratio}, "
                f"expected {guard['so3_stot']}"
            )
        if guard["s1_sred"] is not None and abs(comp.sulfur.s1_sred_ratio - guard["s1_sred"]) > RTOL:
            raise AssertionError(
                f"Fixture '{name}': s1_sred_ratio = {comp.sulfur.s1_sred_ratio}, "
                f"expected {guard['s1_sred']}"
            )
    else:
        if comp.sulfur.s_wt > 1e-9:
            raise AssertionError(
                f"Fixture '{name}': expected no sulfur, got s_wt = {comp.sulfur.s_wt}"
            )


def _capture(comp: BulkComposition) -> dict:
    m = comp.model
    return {
        "all_mol_kg": dict(m.all_mol_kg),
        "o2_mol_kg": m.o2_mol_kg,
        "total_model": comp.total_model,
        "total_model_redox_corrected": comp.total_model_redox_corrected,
        "phantom_o_from_sulfide_wt": comp.phantom_o_from_sulfide_wt,
        "model_mass_redox_corrected": comp.model_mass_redox_corrected,
        "fe3_fetot_ratio": comp.iron.fe3_fetot_ratio,
        "co2_ctot_ratio": comp.carbon.co2_ctot_ratio,
        "so3_stot_ratio": comp.sulfur.so3_stot_ratio,
        "s1_sred_ratio": comp.sulfur.s1_sred_ratio,
    }


def main() -> None:
    GOLDEN.mkdir(exist_ok=True)
    csv_files = sorted(FIXTURES.glob("*.csv"))
    if not csv_files:
        print(f"ERROR: No fixture CSVs found in {FIXTURES}")
        sys.exit(1)

    errors: list[str] = []
    for csv in csv_files:
        name = csv.stem
        print(f"Processing {name} ...", end=" ")
        try:
            comp = BulkComposition()
            apply_to_model(parse_file(str(csv)), comp)

            _assert_fixture(name, comp)

            if comp.total_model_redox_corrected > 0:
                mass = comp.model_mass_redox_corrected
                if abs(mass - 1000.0) > 1e-4:
                    raise AssertionError(
                        f"Mass closure FAIL: {mass:.4f} g/kg (expected ~1000)"
                    )

            exporter = PerplexExporter(comp)

            # --- Permanent component-list golden ---
            components_text = exporter.generate_component_block()
            (GOLDEN / f"{name}_components.dat").write_text(
                components_text, encoding="utf-8", newline="\n"
            )

            # --- Versioned snapshot golden (format v1) ---
            snapshot_text = exporter.generate_snapshot(
                source_file=name,
            )
            (GOLDEN / f"{name}_snapshot.dat").write_text(
                snapshot_text, encoding="utf-8", newline="\n"
            )

            # --- JSON numerics golden (unchanged) ---
            (GOLDEN / f"{name}.json").write_text(
                json.dumps(_capture(comp), indent=2),
                encoding="utf-8",
            )

            print(f"OK  (mass={comp.model_mass_redox_corrected:.3f} g/kg)")

        except Exception as exc:
            print(f"FAILED")
            errors.append(f"  {name}: {exc}")

    print()
    if errors:
        print("ERRORS — golden files NOT complete:")
        for e in errors:
            print(e)
        sys.exit(1)
    else:
        print(f"All {len(csv_files)} golden files written to {GOLDEN}")


if __name__ == "__main__":
    main()
