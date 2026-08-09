# ThermoChemX — Copyright (C) 2026  Michał Bukała <michal.bukala@csic.es>
# This program is free software: GNU General Public License v3 or later.
# It comes with ABSOLUTELY NO WARRANTY. See LICENSE.txt for details.

"""
Perple_X element-basis adapter.

Thin wrapper so the existing element-basis output is accessible through the
TargetAdapter interface (registry, GUI tabs, 'Export as' menu) without altering
any arithmetic.

The render() method reconstructs ``all_mol_kg`` from RecalcResult exclusively
— no live BulkComposition needed — producing output that is byte-identical to
``PerplexExporter(comp).generate_perplex_data()``.  The Phase-0 regression
lock is the authoritative check for this identity.

inject() splices the component block into a Perplex template using the shared
``_inject_component_block`` helper from exporter.py.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .base import TargetAdapter
from ..exporter import _format_value, _format_component_line, _inject_component_block

if TYPE_CHECKING:
    from ..recalc.result import RecalcResult

__all__ = ["PerplexElementAdapter"]

# Canonical key order — must match MolarModel.all_mol_kg insertion order.
_EL_KEYS   = ["Si", "Ti", "Al", "Cr", "Mn", "Mg", "Ca", "Ni", "Na", "K", "P", "H2", "Fe", "C"]
_ALL_KEYS  = _EL_KEYS + ["S2", "O2"]

# Display labels for the result table (Unicode subscripts for readability).
_TABLE_LABELS = [
    "Si", "Ti", "Al", "Cr", "Mn", "Mg", "Ca", "Ni",
    "Na", "K", "P", "H\u2082", "Fe", "C", "S\u2082", "O\u2082",
]


class PerplexElementAdapter(TargetAdapter):
    """
    Perple_X element-basis adapter.

    Reproduces the output of ``PerplexExporter.generate_perplex_data()``
    using only RecalcResult fields (element_moles, total_oxygen, denom,
    input_snapshot).
    """

    target_name         = "perplex_element"
    display_name        = "Perple_X-element (.dat)"
    group_title         = "Elements"
    uses_cation_totals  = False
    is_template_capable = True
    default_suffix      = "_elem.dat"
    file_dialog_filter  = "Perplex Data Files (*.dat);;All Files (*.*)"
    o2_cap_policy       = "allow_negative"

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def render(self, result: "RecalcResult") -> tuple[str, list[str]]:
        """
        Return the full element-basis Perplex output (component block + snapshot).

        Equivalent to ``PerplexExporter(comp).generate_perplex_data()``.
        """
        if result.denom <= 0.0:
            return "", ["RecalcResult.denom is zero; cannot compute mol/kg."]

        component_block = self._component_block(result)
        snapshot        = self._snapshot(result)
        return component_block + "\n\n" + snapshot, []

    def inject(self, template_text: str, result: "RecalcResult") -> tuple[str, list[str]]:
        """
        Splice the element-basis component block into a Perplex template.

        Equivalent to ``PerplexExporter(comp).generate_template_output(template_text)``.
        """
        if result.denom <= 0.0:
            return template_text, ["RecalcResult.denom is zero; cannot inject."]
        try:
            out = _inject_component_block(template_text, self._component_block(result))
        except ValueError as exc:
            return template_text, [str(exc)]
        return out, []

    # ------------------------------------------------------------------ #
    # Private helpers                                                      #
    # ------------------------------------------------------------------ #

    def _mol_kg(self, result: "RecalcResult") -> dict[str, float]:
        """Reconstruct all_mol_kg from RecalcResult (no live composition needed)."""
        factor = 1000.0 / result.denom
        em     = result.element_moles
        mol_kg: dict[str, float] = {k: em.get(k, 0.0) * factor for k in _EL_KEYS}
        mol_kg["S2"] = em.get("S", 0.0) / 2.0 * factor
        mol_kg["O2"] = result.total_oxygen * factor
        return mol_kg

    def _component_block(self, result: "RecalcResult") -> str:
        """Build the ``begin/end thermodynamic component list`` block."""
        mol_kg = self._mol_kg(result)
        lines  = ["begin thermodynamic component list"]
        for key in _ALL_KEYS:
            val = mol_kg[key]
            if val != 0.0:
                lines.append(_format_component_line(key, val))
        lines.append("end thermodynamic component list")
        return "\n".join(lines)

    def _snapshot(self, result: "RecalcResult") -> str:
        """Build the composition snapshot block (format v1) from result.input_snapshot."""
        from ..composition_schema import SNAPSHOT_SCHEMA

        KEY_W = 24
        units = {f.file_key: f.unit for f in SNAPSHOT_SCHEMA}

        lines = [
            "begin composition snapshot",
            "# ThermoChemX composition snapshot",
            f"{'tchx.format_version':<{KEY_W}}1",
            "",
            "# === input (authoritative; re-import reads ONLY in.* keys) ===",
        ]
        for key, val in result.input_snapshot.items():
            if not key.startswith("in."):
                continue
            if isinstance(val, str):
                lines.append(f"{key:<{KEY_W}}{val}".rstrip())
            else:
                comment = f"  # {units[key]}" if units.get(key) else ""
                lines.append(f"{key:<{KEY_W}}{repr(val)}{comment}")

        lines.append("")
        lines.append("# === derived (informational only; ignored on import) ===")
        for key, val in result.input_snapshot.items():
            if not key.startswith("der."):
                continue
            comment = f"  # {units[key]}" if units.get(key) else ""
            lines.append(f"{key:<{KEY_W}}{_format_value(val)}{comment}")

        lines.append("end composition snapshot")
        return "\n".join(lines)

    # ------------------------------------------------------------------ #
    # Table interface (GUI result view)                                   #
    # ------------------------------------------------------------------ #

    def rows(self, result: "RecalcResult") -> list[tuple[str, float]]:
        """Return 16 (label, mol/kg) pairs for the result table."""
        if result.denom <= 0.0:
            return [(lbl, 0.0) for lbl in _TABLE_LABELS]
        mol_kg = self._mol_kg(result)
        values = [mol_kg.get(k, 0.0) for k in _ALL_KEYS]
        return list(zip(_TABLE_LABELS, values))

    def table_headers(self) -> tuple[str, str]:
        return ("Element", "mol / kg of rock")

    # ------------------------------------------------------------------ #
    # File export                                                          #
    # ------------------------------------------------------------------ #

    def export_to_file(
        self,
        result: "RecalcResult",
        output: str,
        sample_name: str,
        template_path: "str | None" = None,
    ) -> "ExportResult":
        """Write element-basis Perplex data to *output* (file or directory).

        If *output* is a directory the file is named ``{sample_name}_tchx.dat``.
        If *template_path* is given a companion ``{prefix}{sample_name}.dat``
        is written to the same directory.
        """
        from pathlib import Path
        from ..exporter import ExportResult, _get_template_dim_suffix

        out = Path(output)
        out_path = out / f"{sample_name}_elem.dat" if out.is_dir() else out
        out_path.parent.mkdir(parents=True, exist_ok=True)

        text, warnings = self.render(result)
        if not text:
            return ExportResult(warnings=list(warnings), filepath=str(out_path))
        out_path.write_text(text, encoding="utf-8")

        mol_kg = self._mol_kg(result)
        exported = [k for k in _ALL_KEYS if mol_kg.get(k, 0.0) != 0.0]

        companion_filepath = ""
        if template_path:
            tmpl_text = Path(template_path).read_text(encoding="utf-8")
            injected, inject_warns = self.inject(tmpl_text, result)
            warnings = list(warnings) + inject_warns
            suffix = _get_template_dim_suffix(template_path)
            comp_path = out_path.parent / f"{sample_name}{suffix}.dat"
            comp_path.write_text(injected, encoding="utf-8")
            companion_filepath = str(comp_path)

        return ExportResult(
            exported_components=exported,
            filepath=str(out_path),
            warnings=list(warnings),
            companion_filepath=companion_filepath,
        )
