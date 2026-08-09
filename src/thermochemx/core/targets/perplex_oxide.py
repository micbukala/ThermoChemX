# ThermoChemX — Copyright (C) 2026  Michał Bukała <michal.bukala@csic.es>
# This program is free software: GNU General Public License v3 or later.
# It comes with ABSOLUTELY NO WARRANTY. See LICENSE.txt for details.

"""
Perple_X oxide-basis adapter.

Representation: molar oxides, FeOt + excess O₂ convention.
Normalisation:  MolKg1000g (same denominator as the element-basis anchor).
Redox:          excess O₂ from ``core.recalc.representation.to_perplex_oxide``.

Negative-O₂ handling (adapter policy = "cap_at_zero"):
  Perple_X oxide databases reject negative excess-O₂ component values.
  When excess O₂ < 0, this adapter clamps it to 0.0, emits a user-facing
  corrective warning, and records the event in the composition snapshot
  (``oxide_o2_capped``, ``oxide_o2_value_molkg``).  Mass closure in the
  exported oxide composition is deliberately broken when the cap fires —
  this is an encoding limitation of the oxide basis, not a rock property.
  To preserve the full reduction state, use the element-basis adapter.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .base import TargetAdapter
from ..exporter import _format_value, _format_component_line, _inject_component_block
from ..recalc.representation import to_perplex_oxide, cap_at_zero, OXIDE_KEY_ORDER

if TYPE_CHECKING:
    from ..recalc.result import RecalcResult

__all__ = ["PerplexOxideAdapter"]

# Display labels for the 16-row result table.
_TABLE_LABELS = [
    "SiO\u2082", "TiO\u2082", "Al\u2082O\u2083", "Cr\u2082O\u2083",
    "FeO\u209c", "MnO", "MgO", "NiO", "CaO",
    "Na\u2082O", "K\u2082O", "P\u2082O\u2085", "H\u2082O",
    "CO\u2082", "S\u2082", "O\u2082 (excess)",
]


class PerplexOxideAdapter(TargetAdapter):
    """
    Perple_X oxide-basis adapter (FeOt + excess O₂).

    ``render(result)``  → full component block + snapshot (with provenance when O₂ < 0).
    ``inject(…)``       → Perplex template with oxide component block spliced in.
    ``rows(result)``    → 16 (label, mol/kg) pairs for the result table.
    """

    target_name         = "perplex_oxide"
    display_name        = "Perple_X-oxide (.dat)"
    group_title         = "Oxides"
    uses_cation_totals  = False
    is_template_capable = True
    file_dialog_filter  = "Perplex Data Files (*.dat);;All Files (*.*)"
    o2_cap_policy       = "cap_at_zero"
    uppercase           = False  # when True, component keys are uppercased in .dat output

    @property
    def default_suffix(self) -> str:
        return "_ox_up.dat" if self.uppercase else "_ox_low.dat"

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def render(self, result: "RecalcResult") -> tuple[str, list[str]]:
        """
        Return the full oxide-basis Perplex output (component block + snapshot).

        When excess O₂ is negative the value is capped at 0, a corrective
        warning is added, and the snapshot records the original negative value.
        """
        if result.denom <= 0.0:
            return "", ["RecalcResult.denom is zero; cannot compute mol/kg."]

        oxide_mol_kg, excess_o2, _info_warnings, _o2_is_negative = to_perplex_oxide(result)
        capped_o2, o2_is_capped, cap_warning = cap_at_zero(excess_o2)
        if o2_is_capped:
            oxide_mol_kg["O2"] = capped_o2
            warnings: list[str] = [cap_warning]
        else:
            warnings = _info_warnings

        component_block = self._component_block(oxide_mol_kg, o2_is_capped)
        snapshot        = self._snapshot(result, o2_is_capped, excess_o2)

        return component_block + "\n\n" + snapshot, warnings

    def inject(self, template_text: str, result: "RecalcResult") -> tuple[str, list[str]]:
        """
        Splice the oxide-basis component block into a Perplex template.

        The snapshot is NOT appended (consistent with PerplexExporter.generate_template_output).
        When excess O₂ is negative it is capped at 0 and a corrective warning is added.
        """
        if result.denom <= 0.0:
            return template_text, ["RecalcResult.denom is zero; cannot inject."]

        oxide_mol_kg, excess_o2, _info_warnings, _o2_is_negative = to_perplex_oxide(result)
        capped_o2, o2_is_capped, cap_warning = cap_at_zero(excess_o2)
        if o2_is_capped:
            oxide_mol_kg["O2"] = capped_o2
            warnings: list[str] = [cap_warning]
        else:
            warnings = _info_warnings
        try:
            out = _inject_component_block(template_text, self._component_block(oxide_mol_kg, o2_is_capped))
        except ValueError as exc:
            return template_text, list(warnings) + [str(exc)]
        return out, warnings

    # ------------------------------------------------------------------ #
    # Table interface (GUI result view)                                   #
    # ------------------------------------------------------------------ #

    def rows(self, result: "RecalcResult") -> list[tuple[str, float]]:
        """Return 16 (label, mol/kg) pairs for the result table."""
        if result.denom <= 0.0:
            return [(lbl, 0.0) for lbl in _TABLE_LABELS]
        oxide_mol_kg, excess_o2, _warns, _neg = to_perplex_oxide(result)
        capped_o2, o2_is_capped, _cw = cap_at_zero(excess_o2)
        if o2_is_capped:
            oxide_mol_kg["O2"] = capped_o2
        values = [oxide_mol_kg.get(k, 0.0) for k in OXIDE_KEY_ORDER]
        return list(zip(_TABLE_LABELS, values))

    def table_headers(self) -> tuple[str, str]:
        return ("Oxide component", "mol / kg of rock")

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
        """Write oxide-basis Perplex data to *output* (file or directory).

        If *output* is a directory the file is named
        ``{sample_name}_perplex_oxide.dat``.
        If *template_path* is given a companion file is written alongside.
        """
        from pathlib import Path
        from ..exporter import ExportResult, _get_template_dim_suffix

        out = Path(output)
        primary_suffix = "_ox_up" if self.uppercase else "_ox_low"
        out_path = (
            out / f"{sample_name}{primary_suffix}.dat" if out.is_dir() else out
        )
        out_path.parent.mkdir(parents=True, exist_ok=True)

        text, warnings = self.render(result)
        if not text:
            return ExportResult(warnings=list(warnings), filepath=str(out_path))
        out_path.write_text(text, encoding="utf-8")

        oxide_mol_kg, excess_o2, _warns, _neg = to_perplex_oxide(result)
        capped_o2, o2_is_capped, _cw = cap_at_zero(excess_o2)
        if o2_is_capped:
            oxide_mol_kg["O2"] = capped_o2
        exported = [
            k for k in OXIDE_KEY_ORDER
            if oxide_mol_kg.get(k, 0.0) != 0.0 or (k == "O2" and o2_is_capped)
        ]

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

    # ------------------------------------------------------------------ #
    # Private helpers                                                      #
    # ------------------------------------------------------------------ #

    def _component_block(self, oxide_mol_kg: dict[str, float], o2_is_capped: bool = False) -> str:
        """Build the ``begin/end thermodynamic component list`` block.

        When *o2_is_capped* is True the O\u2082 line is always written even if its
        value is 0.0 \u2014 Perple_X requires the explicit 0 for capped-reducing compositions.
        """
        lines = ["begin thermodynamic component list"]
        for key in OXIDE_KEY_ORDER:
            val = oxide_mol_kg.get(key, 0.0)
            if val != 0.0 or (key == "O2" and o2_is_capped):
                used_key = key.upper() if self.uppercase else key
                lines.append(_format_component_line(used_key, val))
        lines.append("end thermodynamic component list")
        return "\n".join(lines)

    def _snapshot(
        self,
        result: "RecalcResult",
        o2_is_capped: bool,
        excess_o2_mol_kg: float,
    ) -> str:
        """
        Build the snapshot block (format v1).

        When the cap fires, appends provenance keys:
          - ``der.oxide_o2_capped``       = 1.0  (flag; mass closure is broken)
          - ``der.oxide_o2_value_molkg``  = <original negative value>
        """
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

        if o2_is_capped:
            lines.append(f"{'der.oxide_o2_capped':<{KEY_W}}{_format_value(0.0)}")
            lines.append(f"{'der.oxide_o2_value_molkg':<{KEY_W}}{_format_value(excess_o2_mol_kg)}")

        lines.append("end composition snapshot")
        return "\n".join(lines)

