# ThermoChemX — Copyright (C) 2026  Michał Bukała <michal.bukala@csic.es>
# This program is free software: GNU General Public License v3 or later.
# It comes with ABSOLUTELY NO WARRANTY. See LICENSE.txt for details.
 
"""
Session-only Settings dialog for ThermoChemX.

Presents one row per registered export target:
    [✓ checkbox]  <display name>   Template: <filename or none>  [ Browse… ]

The Browse button is enabled only for template-capable targets.  Perplex
templates are validated for the begin/end thermodynamic component list
markers.

No cross-launch persistence — choices are discarded when the app closes.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QDialogButtonBox, QCheckBox, QComboBox, QFileDialog, QMessageBox, QScrollArea,
    QWidget, QGridLayout,
)
from PySide6.QtCore import Qt


class SettingsDialog(QDialog):
    """Session export configuration: which targets to write and their templates."""

    def __init__(
        self,
        parent=None,
        export_targets: "set[str] | None" = None,
        template_paths: "dict[str, str] | None" = None,
        case_styles: "dict[str, str] | None" = None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Export Settings")
        self.setMinimumWidth(700)

        from ..core.targets.registry import list_targets, get_adapter

        self._export_targets: set[str] = set(export_targets or {"perplex_element"})
        self._template_paths: dict[str, str] = dict(template_paths or {})
        self._case_styles: dict[str, str] = dict(case_styles or {})

        # ── Per-target widgets ──────────────────────────────────────────
        self._checks: dict[str, QCheckBox] = {}
        self._tmpl_labels: dict[str, QLabel] = {}
        self._browse_btns: dict[str, QPushButton] = {}
        self._case_combos: dict[str, QComboBox] = {}

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        hdr = QLabel("Session preferences \u2014 not saved across restarts")
        hdr.setStyleSheet("color: #7E8AA0; font-style: italic;")
        layout.addWidget(hdr)

        sub_lbl = QLabel("Select which targets to include on Export / Export All:")
        layout.addWidget(sub_lbl)

        # Scrollable grid for the target rows
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        grid_widget = QWidget()
        grid = QGridLayout(grid_widget)
        grid.setContentsMargins(4, 4, 4, 4)
        grid.setSpacing(6)
        grid.setColumnStretch(1, 1)  # display-name column stretches

        for row_idx, name in enumerate(list_targets()):
            adapter = get_adapter(name)

            chk = QCheckBox()
            chk.setChecked(name in self._export_targets)
            self._checks[name] = chk
            grid.addWidget(chk, row_idx, 0, Qt.AlignVCenter)

            name_lbl = QLabel(adapter.display_name)
            grid.addWidget(name_lbl, row_idx, 1, Qt.AlignVCenter)

            # Template path label
            tmpl_path = self._template_paths.get(name, "")
            tmpl_lbl = QLabel(
                Path(tmpl_path).name if tmpl_path else "<no template>"
            )
            tmpl_lbl.setStyleSheet("color: #7E8AA0;")
            tmpl_lbl.setToolTip(tmpl_path or "")
            self._tmpl_labels[name] = tmpl_lbl
            grid.addWidget(tmpl_lbl, row_idx, 2, Qt.AlignVCenter)

            # Browse button — only for template-capable adapters
            if adapter.is_template_capable:
                btn = QPushButton("Browse\u2026")
                btn.setFixedWidth(110)
                btn.clicked.connect(lambda checked, n=name, a=adapter: self._on_browse(n, a))
                self._browse_btns[name] = btn
                grid.addWidget(btn, row_idx, 3, Qt.AlignVCenter)
            else:
                # Placeholder so the column stays consistent
                grid.addWidget(QLabel(""), row_idx, 3)
            # Case-style selector — only for perplex_oxide
            if name == "perplex_oxide":
                case_combo = QComboBox()
                case_combo.addItems(["Lowercase", "Uppercase"])
                current_case = self._case_styles.get(name, "lowercase")
                case_combo.setCurrentIndex(1 if current_case == "uppercase" else 0)
                self._case_combos[name] = case_combo
                grid.addWidget(case_combo, row_idx, 4, Qt.AlignVCenter)
            else:
                grid.addWidget(QLabel(""), row_idx, 4)
        scroll.setWidget(grid_widget)
        layout.addWidget(scroll)

        # ── Buttons ─────────────────────────────────────────────────────
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    # ------------------------------------------------------------------
    # Public accessors
    # ------------------------------------------------------------------

    def selected_targets(self) -> set[str]:
        """Return the set of checked target names."""
        return {name for name, chk in self._checks.items() if chk.isChecked()}

    def template_paths(self) -> dict[str, str]:
        """Return the dict of target_name → template_path (only for set paths)."""
        return dict(self._template_paths)

    def case_styles(self) -> dict[str, str]:
        """Return the dict of target_name → case style ('lowercase' or 'uppercase')."""
        return {name: combo.currentText().lower() for name, combo in self._case_combos.items()}

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_browse(self, target_name: str, adapter) -> None:
        """Open a file dialog and validate the chosen template for *target_name*."""
        default_dir = (
            str(Path(self._template_paths[target_name]).parent)
            if target_name in self._template_paths
            else ""
        )

        path, _ = QFileDialog.getOpenFileName(
            self,
            f"Select Perplex template \u2014 {adapter.display_name}",
            default_dir,
            "Perplex Template (*.dat);;All Files (*.*)",
        )

        if not path:
            return

        try:
            content = Path(path).read_text(encoding="utf-8")
        except Exception as exc:
            QMessageBox.critical(self, "Template Read Error",
                                 f"Cannot read template:\n{exc}")
            return
        for marker in (
            "begin thermodynamic component list",
            "end thermodynamic component list",
        ):
            if marker not in content:
                QMessageBox.warning(
                    self, "Invalid Template",
                    f"Missing required marker:\n\u2018{marker}\u2019",
                )
                return

        self._template_paths[target_name] = path
        name_only = Path(path).name
        self._tmpl_labels[target_name].setText(name_only)
        self._tmpl_labels[target_name].setToolTip(path)
        self._tmpl_labels[target_name].setStyleSheet("")

    def _on_accept(self) -> None:
        """Validate before closing: at least one target must be checked."""
        if not any(chk.isChecked() for chk in self._checks.values()):
            QMessageBox.warning(
                self, "No Target Selected",
                "Please check at least one export target.",
            )
            return
        self.accept()
