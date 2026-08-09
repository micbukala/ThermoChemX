# ThermoChemX — Copyright (C) 2026  Michał Bukała <michal.bukala@csic.es>
# This program is free software: GNU General Public License v3 or later.
# It comes with ABSOLUTELY NO WARRANTY. See LICENSE.txt for details.

"""
TargetAdapter abstract base class (Layer C).

A thin adapter declares:
  - target_name       — human-readable identifier used by the registry
  - render(result)    — produce the formatted composition block / line as a str
  - inject(template, result) — splice the composition into an existing template

Both methods return (output_string, warnings_list).

Adapters MUST NOT recompute redox — they re-express RecalcResult.total_oxygen.
Adapters MUST NOT silently drop imported components (warn instead).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..recalc.result import RecalcResult
    from ..exporter import ExportResult

__all__ = ["TargetAdapter"]


class TargetAdapter(ABC):
    """Abstract base for all export-target adapters."""

    #: Short identifier used in the registry and in UI export menus.
    target_name: str = ""

    #: Human-readable label shown in the preview combobox and Settings dialog.
    display_name: str = ""

    #: Title for the Elements/Oxides group box in the right panel.
    group_title: str = "Elements"

    #: True → show the Cations-100 totals panel; False → show the mol/kg totals panel.
    uses_cation_totals: bool = False

    #: True → show a Browse button in the Settings dialog for template selection.
    is_template_capable: bool = False

    #: Filename suffix used when auto-naming a single-target Save-As (e.g. ``"_tchx.dat"``).
    default_suffix: str = ".dat"

    #: Qt file-dialog filter string for Save-As dialogs.
    file_dialog_filter: str = "All Files (*.*)"

    #: How this adapter handles excess O₂ < 0.
    #: ``"allow_negative"`` — export the true (possibly negative) value as-is.
    #: ``"cap_at_zero"``    — clamp to 0 (reserved for future MAGEMin/THERMOCALC).
    o2_cap_policy: str = "allow_negative"

    @abstractmethod
    def render(self, result: "RecalcResult") -> tuple[str, list[str]]:
        """
        Render the composition block / line for this target.

        Returns:
            (block_string, warnings) where warnings is a (possibly empty) list
            of human-readable strings that should be surfaced to the user.
        """
        ...

    @abstractmethod
    def inject(self, template_text: str, result: "RecalcResult") -> tuple[str, list[str]]:
        """
        Inject the composition into a target-format template file.

        Returns:
            (modified_template_text, warnings).
        """
        ...

    @abstractmethod
    def rows(self, result: "RecalcResult") -> list[tuple[str, float]]:
        """
        Return structured rows for the result table.

        Each entry is ``(label, value)`` where *label* is the display string for
        column 0 and *value* is the numeric quantity for column 1.  Always returns
        exactly 16 rows so the fixed-height table never reflows.
        """
        ...

    @abstractmethod
    def table_headers(self) -> tuple[str, str]:
        """Return ``(column0_header, column1_header)`` for the result table."""
        ...

    @abstractmethod
    def export_to_file(
        self,
        result: "RecalcResult",
        output: str,
        sample_name: str,
        template_path: "str | None" = None,
    ) -> "ExportResult":
        """
        Write composition to a file (or into a directory with auto-naming).

        Args:
            result:        RecalcResult from ``build_recalc_result()``.
            output:        Path to a *file* (used verbatim) **or** to an existing
                           *directory* (file is named automatically as
                           ``{sample_name}_<suffix>``).
            sample_name:   Base name used for auto-naming and companion files.
            template_path: Optional template path; if supplied a companion file
                           is written alongside the primary output.

        Returns:
            ExportResult with filepath, exported_components, warnings, and
            optional companion_filepath.
        """
        ...
