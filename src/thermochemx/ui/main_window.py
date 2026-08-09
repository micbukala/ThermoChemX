# ThermoChemX — Copyright (C) 2026  Michał Bukała <michal.bukala@csic.es>
# This program is free software: GNU General Public License v3 or later.
# It comes with ABSOLUTELY NO WARRANTY. See LICENSE.txt for details.

"""Main application window: interactive oxide table, redox system panels, and file import/export dialogs with real-time mol/kg preview."""

import sys
import re
from collections import namedtuple
from PySide6.QtWidgets import (
    QAbstractScrollArea, QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGroupBox, QFormLayout, QDoubleSpinBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QLabel, QFrame, QScrollArea, QPushButton, QLineEdit,
    QFileDialog, QMessageBox, QInputDialog, QComboBox, QSizePolicy,
    QToolButton, QStyle, QDialog, QDialogButtonBox, QPlainTextEdit
)
from PySide6.QtCore import Qt, QLocale, QTimer, QPropertyAnimation, QEasingCurve, Signal, QObject, QThread, QSize, QUrl
from PySide6.QtGui import QColor, QDesktopServices
from ..core.composition import BulkComposition
from ..core.importer import parse_file_multi, apply_to_model
from ..core.exporter import PerplexExporter
from ..core.recalc.core import build_recalc_result
from ..core.targets.registry import get_adapter
from pathlib import Path


# ---------------------------------------------------------------------------
# Spinbox registry — single source of truth for all bidirectional spinboxes
# ---------------------------------------------------------------------------
# Iterated by:
#   - _setup_connections    (valueChanged -> _update_model)
#   - refresh_ui            (block all signals, then setValue from model)
#   - _setup_tab_order      (focus chain across panels)
# Order matches the desired visual / tab order on the left panel.

SpecField = namedtuple("SpecField", ["spin_attr", "system", "prop", "kind", "panel"])

SPEC_FIELDS: list[SpecField] = [
    # ── Iron ──
    SpecField("spin_feo_tot",          "iron",   "feo_tot_wt",      "total",   "iron"),
    SpecField("spin_feo",              "iron",   "fe2_oxide_wt",     "species", "iron"),
    SpecField("spin_fe2o3",            "iron",   "fe3_oxide_wt",     "species", "iron"),
    SpecField("spin_fe3_ratio",        "iron",   "fe3_fetot_ratio", "ratio",   "iron"),
    SpecField("spin_fe2_wt",           "iron",   "fe2_wt",          "species", "iron"),
    SpecField("spin_fe2_ugg",          "iron",   "fe2_ugg",         "species", "iron"),
    SpecField("spin_fe3_wt",           "iron",   "fe3_wt",          "species", "iron"),
    SpecField("spin_fe3_ugg",          "iron",   "fe3_ugg",         "species", "iron"),
    # ── Carbon ──
    SpecField("spin_c_wt",             "carbon", "c_wt",             "total",   "carbon"),
    SpecField("spin_c_ugg",            "carbon", "total_c_ugg",      "total",   "carbon"),
    SpecField("spin_co2_ratio",        "carbon", "co2_ctot_ratio",   "ratio",   "carbon"),
    SpecField("spin_c_graphite_wt",    "carbon", "c0_wt",            "species", "carbon"),
    SpecField("spin_c_graphite_ugg",   "carbon", "c0_ugg",           "species", "carbon"),
    SpecField("spin_c_carbonate_wt",   "carbon", "c4_wt",            "species", "carbon"),
    SpecField("spin_c_carbonates_ugg", "carbon", "c4_ugg",           "species", "carbon"),
    # ── Sulfur ──
    SpecField("spin_s_wt",             "sulfur", "s_wt",             "total",   "sulfur"),
    SpecField("spin_s_ugg",            "sulfur", "total_s_ugg",      "total",   "sulfur"),
    SpecField("spin_so3_ratio",        "sulfur", "so3_stot_ratio",   "ratio",   "sulfur"),
    SpecField("spin_s1_ratio",         "sulfur", "s1_sred_ratio",    "ratio",   "sulfur"),
    SpecField("spin_s_sulfate_wt",     "sulfur", "s6_wt",            "species", "sulfur"),
    SpecField("spin_s_sulfate_ugg",    "sulfur", "s6_ugg",           "species", "sulfur"),
    SpecField("spin_s1minus_wt",       "sulfur", "s1_wt",            "species", "sulfur"),
    SpecField("spin_s1minus_ugg",      "sulfur", "s1_ugg",           "species", "sulfur"),
    SpecField("spin_s2minus_wt",       "sulfur", "s2_wt",            "species", "sulfur"),
    SpecField("spin_s2minus_ugg",      "sulfur", "s2_ugg",           "species", "sulfur"),
]


# ---------------------------------------------------------------------------
# Helper widgets
# ---------------------------------------------------------------------------

class AutoSelectSpinBox(QDoubleSpinBox):
    """QDoubleSpinBox that auto-selects all text when focused."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setLocale(QLocale.c())

    def focusInEvent(self, event):
        super().focusInEvent(event)
        self.selectAll()


class AutoSelectTableWidget(QTableWidget):
    """QTableWidget with auto-selection on edit and smart TAB navigation."""

    def __init__(self, rows, columns, parent=None):
        super().__init__(rows, columns, parent)

    def edit(self, index, trigger, event):
        result = super().edit(index, trigger, event)
        if result and index.column() == 1 and 0 <= index.row() <= 16:
            editor = QApplication.focusWidget()
            if editor and isinstance(editor, QLineEdit):
                QTimer.singleShot(0, editor.selectAll)
        return result

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Tab:
            current_row = self.currentRow()
            current_col = self.currentColumn()
            next_row = current_row + 1 if current_col == 1 else 0
            while next_row <= 16:
                item = self.item(next_row, 1)
                if item and (item.flags() & Qt.ItemIsEditable):
                    self.setCurrentCell(next_row, 1)
                    event.accept()
                    return
                next_row += 1
            parent_window = self.window()
            if hasattr(parent_window, 'spin_feo_tot'):
                parent_window.spin_feo_tot.setFocus()
            event.accept()
            return

        elif event.key() == Qt.Key_Backtab or (
            event.key() == Qt.Key_Tab and event.modifiers() & Qt.ShiftModifier
        ):
            current_row = self.currentRow()
            current_col = self.currentColumn()
            prev_row = current_row - 1 if current_col == 1 else 16
            while prev_row >= 0:
                item = self.item(prev_row, 1)
                if item and (item.flags() & Qt.ItemIsEditable):
                    self.setCurrentCell(prev_row, 1)
                    event.accept()
                    return
                prev_row -= 1
            event.accept()
            return

        super().keyPressEvent(event)


class CollapsibleSection(QWidget):
    """
    Section with a clickable header that reveals/hides extra content.

    Layout:
        [Header (toggle)]
        [Always-visible QFormLayout]     <- optional; hide via hide_always_area()
        [Collapsible QFormLayout]        <- animated open/close

    Public API:
        always_layout(), extra_layout()  – QFormLayouts for callers to fill
        hide_always_area()               – use widget purely as collapsible body
        expand(), collapse()             – programmatic open/close
        set_collapsed(bool)              – idempotent setter
        is_collapsed                     – current state
    """

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self._collapsed = True
        self._anim_in_flight = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Container frame (border + radius)
        self._container = QFrame()
        self._container.setObjectName("collapsibleFrame")
        container_layout = QVBoxLayout(self._container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)

        # Header button
        self._header = QToolButton()
        self._header.setText(f"  {title}")
        self._header.setObjectName("collapsibleHeader")
        self._header.setCheckable(False)
        self._header.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self._header.setArrowType(Qt.RightArrow)
        self._header.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._header.clicked.connect(self._toggle)
        container_layout.addWidget(self._header)

        # Always-visible area
        self._always_widget = QWidget()
        self._always_widget.setObjectName("collapsibleAlways")
        self._always_layout = QFormLayout(self._always_widget)
        self._always_layout.setContentsMargins(10, 6, 10, 6)
        self._always_layout.setSpacing(4)
        self._always_layout.setLabelAlignment(Qt.AlignLeft)
        container_layout.addWidget(self._always_widget)

        # Expandable area
        self._extra_widget = QWidget()
        self._extra_widget.setObjectName("collapsibleExtra")
        self._extra_layout = QFormLayout(self._extra_widget)
        self._extra_layout.setContentsMargins(10, 6, 10, 10)
        self._extra_layout.setSpacing(4)
        self._extra_layout.setLabelAlignment(Qt.AlignLeft)
        self._extra_widget.setMaximumHeight(0)
        self._extra_widget.setVisible(False)
        container_layout.addWidget(self._extra_widget)

        outer.addWidget(self._container)

        self._anim = QPropertyAnimation(self._extra_widget, b"maximumHeight")
        self._anim.setDuration(180)
        self._anim.setEasingCurve(QEasingCurve.InOutQuad)
        self._anim.finished.connect(self._on_anim_finished)

    # ----- public layout accessors -----
    def always_layout(self) -> QFormLayout:
        return self._always_layout

    def extra_layout(self) -> QFormLayout:
        return self._extra_layout

    def hide_always_area(self):
        """Remove the always-visible area entirely (use widget as pure collapsible body)."""
        self._always_widget.setVisible(False)
        self._always_widget.setMaximumHeight(0)

    # ----- state -----
    @property
    def is_collapsed(self) -> bool:
        return self._collapsed

    def set_collapsed(self, collapsed: bool):
        if collapsed == self._collapsed:
            return
        self._toggle()

    def expand(self):
        self.set_collapsed(False)

    def collapse(self):
        self.set_collapsed(True)

    # ----- internals -----
    def _toggle(self):
        self._collapsed = not self._collapsed
        if self._collapsed:
            # Animate down to 0, then hide
            self._header.setArrowType(Qt.RightArrow)
            current = self._extra_widget.height() or self._extra_widget.sizeHint().height()
            self._anim.stop()
            self._anim.setStartValue(current)
            self._anim.setEndValue(0)
            self._anim_in_flight = True
            self._anim.start()
        else:
            # Show, then defer sizing until QFormLayout has settled
            self._header.setArrowType(Qt.DownArrow)
            self._extra_widget.setVisible(True)
            self._extra_widget.setMaximumHeight(0)
            self._anim_in_flight = True
            QTimer.singleShot(0, self._start_expand_anim)

    def _start_expand_anim(self):
        # Read sizeHint after a layout pass so QFormLayout reports real height
        self._extra_widget.adjustSize()
        target = max(self._extra_widget.sizeHint().height(),
                     self._extra_layout.sizeHint().height() + 16)
        self._anim.stop()
        self._anim.setStartValue(0)
        self._anim.setEndValue(target)
        self._anim.start()

    def _on_anim_finished(self):
        if not self._anim_in_flight:
            return
        self._anim_in_flight = False
        if self._collapsed:
            self._extra_widget.setVisible(False)
        else:
            # Release the height cap so the widget reflows on window resize
            self._extra_widget.setMaximumHeight(16777215)

    def add_separator(self):
        """Add a horizontal separator line to the always-visible layout."""
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        line.setObjectName("collapsibleSep")
        self._always_layout.addRow(line)


# ---------------------------------------------------------------------------
# Color grammar (Nord + redox)
# ---------------------------------------------------------------------------

COLOR_OXIDIZED     = "#EBCB8B"   # amber  — Fe³⁺, C⁴⁺, S⁶⁺
COLOR_INTERMEDIATE = "#88C0D0"   # cyan   — S¹⁻
COLOR_REDUCED      = "#5E81AC"   # blue   — Fe²⁺, C⁰, S²⁻
COLOR_NEUTRAL_BG   = "#434C5E"   # field bg (also empty redox track)
COLOR_MUTED        = "#7E8AA0"   # italic / sub-header / segment labels
COLOR_OK           = "#A3BE8C"   # quality green
COLOR_WARN         = "#EBCB8B"   # quality amber
COLOR_BAD          = "#BF616A"   # quality red


# ---------------------------------------------------------------------------
# Font sizes (global)
# ---------------------------------------------------------------------------

FONT_SIZE_MAIN    = 16   # body text, spinboxes, table rows
FONT_SIZE_HEADING = 16   # group-box titles, panel headers
FONT_SIZE_TABLE   = 16   # tables (kept separate so it can diverge)
FONT_SIZE_SMALL   = 11   # captions, species collapsible content
FONT_SIZE_WARN    = 14   # warning banner below the result table
FONT_SIZE_PREVIEW = 14   # export preview monospace text


# ---------------------------------------------------------------------------
# Main window dimensions (defaults)
# ---------------------------------------------------------------------------

WINDOW_DEFAULT_WIDTH  = 1100   # initial window width  (px)
WINDOW_DEFAULT_HEIGHT = 900   # initial window height (px)
WINDOW_MIN_WIDTH      = 900   # minimum window width  (px)
WINDOW_MIN_HEIGHT     = 600   # minimum window height (px)


# ---------------------------------------------------------------------------
# Redox speciation bar
# ---------------------------------------------------------------------------

class RedoxBar(QWidget):
    """
    Read-only horizontal segmented bar showing how one element is partitioned
    across its oxidation states. Segment widths are molar fractions; for
    single-element speciation, mol% ≡ wt% (atomic mass cancels).

    Construct with a list of (glyph_label, color_hex). Call set_values(...)
    in refresh_ui with the species wt% (the absolute values; the bar
    normalizes itself).
    """

    MIN_LABEL_FRACTION = 0.12   # below this, drop the inline label
    BAR_HEIGHT = 14
    BAR_TOP = 4
    LABEL_TOP_GAP = 4
    LABEL_HEIGHT = 14
    SEG_GAP = 2

    def __init__(self, segments: list[tuple[str, str]], parent=None):
        super().__init__(parent)
        self._segments = list(segments)
        self._values: list[float] = [0.0] * len(self._segments)
        self.setMinimumHeight(self.BAR_TOP + self.BAR_HEIGHT + self.LABEL_TOP_GAP + self.LABEL_HEIGHT)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._refresh_tooltip()

    def set_values(self, values: list[float]):
        if len(values) != len(self._segments):
            return
        self._values = [max(0.0, float(v)) for v in values]
        self._refresh_tooltip()
        self.update()

    def _refresh_tooltip(self):
        total = sum(self._values)
        if total <= 0:
            self.setToolTip("No data.")
            return
        lines = []
        for (glyph, _), v in zip(self._segments, self._values):
            lines.append(f"{glyph}  —  {v / total * 100:.1f} mol%")
        self.setToolTip("\n".join(lines))

    def paintEvent(self, event):
        from PySide6.QtGui import QPainter, QBrush, QFont
        from PySide6.QtCore import QRect
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        bar_w = self.width()
        bar_y = self.BAR_TOP
        bar_h = self.BAR_HEIGHT
        label_y = bar_y + bar_h + self.LABEL_TOP_GAP

        total = sum(self._values)
        if total <= 0:
            # Empty / neutral track
            p.setBrush(QBrush(QColor(COLOR_NEUTRAL_BG)))
            p.setPen(Qt.NoPen)
            p.drawRoundedRect(0, bar_y, bar_w, bar_h, 4, 4)
            p.setPen(QColor(COLOR_MUTED))
            f = QFont()
            f.setPointSizeF(8.5)
            p.setFont(f)
            p.drawText(QRect(0, label_y, bar_w, self.LABEL_HEIGHT),
                       Qt.AlignHCenter | Qt.AlignTop, "—")
            p.end()
            return

        fractions = [v / total for v in self._values]
        non_zero = sum(1 for f in fractions if f > 0)
        if non_zero <= 0:
            p.end()
            return
        gap_total = self.SEG_GAP * max(0, non_zero - 1)
        usable_w = max(0, bar_w - gap_total)

        # Pixel-rounded widths (last segment gets remainder)
        widths = [int(usable_w * f) for f in fractions]
        # Distribute rounding leftover to the largest segment
        leftover = usable_w - sum(widths)
        if leftover != 0 and widths:
            idx_max = max(range(len(widths)), key=lambda i: fractions[i])
            widths[idx_max] += leftover

        p.setPen(Qt.NoPen)
        font_label = QFont()
        font_label.setPointSizeF(8.5)

        x = 0
        for i, ((glyph, color), seg_w, frac) in enumerate(zip(self._segments, widths, fractions)):
            if seg_w <= 0 or frac <= 0:
                continue
            p.setBrush(QBrush(QColor(color)))
            p.drawRoundedRect(x, bar_y, seg_w, bar_h, 4, 4)
            if frac >= self.MIN_LABEL_FRACTION:
                p.setPen(QColor(COLOR_MUTED))
                p.setFont(font_label)
                txt = f"{glyph} {frac * 100:.0f}%"
                p.drawText(QRect(x, label_y, seg_w, self.LABEL_HEIGHT),
                           Qt.AlignHCenter | Qt.AlignTop, txt)
                p.setPen(Qt.NoPen)
            x += seg_w + self.SEG_GAP
        p.end()


# ---------------------------------------------------------------------------
# Import worker (background thread)
# ---------------------------------------------------------------------------

class ImportWorker(QObject):
    """Runs ``parse_file_multi`` on a background thread to keep the GUI responsive."""

    finished = Signal(list, list)   # samples: list[SampleData], file_warnings: list[str]
    error = Signal(str)

    def __init__(self, path: str):
        super().__init__()
        self._path = path

    def run(self) -> None:
        try:
            samples, file_warnings = parse_file_multi(self._path)
            self.finished.emit(samples, file_warnings)
        except Exception as exc:
            self.error.emit(str(exc))


# ---------------------------------------------------------------------------
# Main Window
# ---------------------------------------------------------------------------

class ThermoChemXCalculator(QMainWindow):

    WINDOW_DEFAULT_WIDTH = WINDOW_DEFAULT_WIDTH
    WINDOW_DEFAULT_HEIGHT = WINDOW_DEFAULT_HEIGHT
    WINDOW_MIN_WIDTH = WINDOW_MIN_WIDTH
    WINDOW_MIN_HEIGHT = WINDOW_MIN_HEIGHT
    FONT_SIZE_MAIN = FONT_SIZE_MAIN
    FONT_SIZE_HEADING = FONT_SIZE_HEADING
    FONT_SIZE_TABLE = FONT_SIZE_TABLE
    FONT_SIZE_SMALL = FONT_SIZE_SMALL
    FONT_SIZE_WARN = FONT_SIZE_WARN
    FONT_SIZE_PREVIEW = FONT_SIZE_PREVIEW

    def __init__(self):
        super().__init__()
        self.model = BulkComposition()
        self.last_import_dir = None
        self.last_export_dir = None

        self._samples: list[BulkComposition] = []
        self._sample_names: list[str] = []
        self._initial_data: list[dict] = []
        self._current_sample_idx: int = 0
        self._template_path: str | None = None
        self._default_export_target: str = "perplex_element"
        self._export_targets: set[str] = {"perplex_element"}
        self._template_paths: dict[str, str] = {}
        self._case_styles: dict[str, str] = {}

        self.setWindowTitle("ThermoChemX")
        self.resize(self.WINDOW_DEFAULT_WIDTH, self.WINDOW_DEFAULT_HEIGHT)
        self.setMinimumSize(self.WINDOW_MIN_WIDTH, self.WINDOW_MIN_HEIGHT)

        self._init_ui()
        self._apply_styling()
        # Now that QSS is applied, sibling buttons report their real (styled)
        # height. Pin the icon-only About button to match Import exactly.
        self.btn_about.setFixedHeight(self.btn_import.sizeHint().height())

        self.model.compositionChanged.connect(self.refresh_ui)
        self._setup_connections()

        self.btn_import.clicked.connect(self._on_import_click)
        self.btn_settings.clicked.connect(self._on_settings_click)
        self.btn_export.clicked.connect(self._on_export_click)
        self.btn_export_all.clicked.connect(self._on_export_all_click)
        self.btn_reset.clicked.connect(self._on_reset_click)
        self.btn_about.clicked.connect(self._on_about_click)
        self.sample_selector.currentIndexChanged.connect(self._on_sample_changed)

        self._setup_tab_order()
        self.refresh_ui()

    # ------------------------------------------------------------------
    # Message helpers
    # ------------------------------------------------------------------

    def _show_message(self, title, message, icon=QMessageBox.Information, truncate=True):
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle(title)
        msg_box.setIcon(icon)
        if truncate and (len(message) > 300 or message.count('\n') > 10):
            lines = message.split('\n')
            msg_box.setText(lines[0] if lines else message[:100])
            msg_box.setDetailedText(message)
        else:
            # Full text shown inline; no collapsible details panel.
            msg_box.setText(message)
        msg_box.setSizeGripEnabled(True)
        msg_box.setMinimumWidth(700)
        msg_box.setMinimumHeight(200)
        for label in msg_box.findChildren(QLabel):
            label.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)
            label.setWordWrap(True)
            label.setOpenExternalLinks(False)
        msg_box.exec()

    def _show_resizable_text_dialog(self, title: str, message: str,
                                     initial_width: int, initial_height: int) -> None:
        """Modal dialog with a scrollable, monospace text area and an OK button.

        Unlike QMessageBox this is genuinely resizable via edge drag and
        honours the initial_height passed in — QMessageBox's internal
        layout ignores both.
        """
        dlg = QDialog(self)
        dlg.setWindowTitle(title)
        dlg.setSizeGripEnabled(True)
        dlg.resize(initial_width, initial_height)
        dlg.setMinimumSize(500, 200)

        vbox = QVBoxLayout(dlg)
        vbox.setContentsMargins(12, 12, 12, 12)
        vbox.setSpacing(8)

        text_edit = QPlainTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setLineWrapMode(QPlainTextEdit.NoWrap)
        text_edit.setPlainText(message)
        vbox.addWidget(text_edit, stretch=1)

        btn_box = QDialogButtonBox(QDialogButtonBox.Ok)
        btn_box.accepted.connect(dlg.accept)
        vbox.addWidget(btn_box)

        dlg.exec()

    def _show_question(self, title, message) -> bool:
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle(title)
        msg_box.setText(message)
        msg_box.setIcon(QMessageBox.Question)
        msg_box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        msg_box.setDefaultButton(QMessageBox.No)
        msg_box.setSizeGripEnabled(True)
        msg_box.setMinimumWidth(700)
        for label in msg_box.findChildren(QLabel):
            label.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)
            label.setWordWrap(True)
        return msg_box.exec() == QMessageBox.Yes

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        root_layout = QVBoxLayout(central_widget)
        root_layout.setContentsMargins(16, 16, 16, 16)
        root_layout.setSpacing(10)

        # ── Toolbar row ──────────────────────────────────────────────
        root_layout.addLayout(self._build_toolbar())

        # ── Main two-column area ─────────────────────────────────────
        columns = QHBoxLayout()
        columns.setSpacing(12)

        columns.addWidget(self._build_left_panel(), stretch=1)
        columns.addWidget(self._build_right_panel(), stretch=1)

        root_layout.addLayout(columns)

    # ── Toolbar ──────────────────────────────────────────────────────

    def _build_toolbar(self) -> QHBoxLayout:
        bar = QHBoxLayout()
        bar.setSpacing(8)

        self.btn_import = QPushButton("Import")
        self.btn_import.setObjectName("btnImport")

        self.btn_settings = QPushButton("Settings")
        self.btn_settings.setObjectName("btnSettings")
        self.btn_settings.setToolTip("Configure export targets and templates")

        self.btn_export = QPushButton("Export")
        self.btn_export.setObjectName("btnExport")
        self.btn_export_all = QPushButton("Export All")
        self.btn_export_all.setObjectName("btnExport")
        self.btn_export_all.setVisible(False)

        self.btn_reset = QPushButton("Reset")
        self.btn_reset.setObjectName("btnReset")
        self.btn_reset.setEnabled(False)

        # About — icon-only button (no text); signal wiring deferred.
        # Bump the icon so the ❓ isn't dwarfed by button padding.
        # Height is pinned in __init__ AFTER _apply_styling() runs, so it
        # picks up the styled padding + bold-font metric like sibling buttons.
        self.btn_about = QPushButton()
        self.btn_about.setObjectName("btnAbout")
        self.btn_about.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_MessageBoxQuestion)
        )
        self.btn_about.setIconSize(QSize(22, 22))
        self.btn_about.setToolTip("About ThermoChemX")
        self.btn_about.setFixedWidth(42)

        for btn in [self.btn_import, self.btn_export, self.btn_export_all,
                    self.btn_settings, self.btn_reset, self.btn_about]:
            bar.addWidget(btn)

        bar.addStretch()

        # Sample name
        bar.addWidget(QLabel("Sample:"))
        self.sample_name_input = QLineEdit()
        self.sample_name_input.setText("unknown")
        self.sample_name_input.setPlaceholderText("Sample name")
        self.sample_name_input.setFixedWidth(160)
        self.sample_name_input.textChanged.connect(self._on_sample_name_changed)
        bar.addWidget(self.sample_name_input)

        # Sample selector (multi-sample mode)
        self.sample_selector = QComboBox()
        self.sample_selector.setToolTip("Select sample")
        self.sample_selector_widget = QWidget()
        ss_layout = QHBoxLayout(self.sample_selector_widget)
        ss_layout.setContentsMargins(0, 0, 0, 0)
        ss_layout.addWidget(QLabel("Sample list:"))
        ss_layout.addWidget(self.sample_selector)
        self.sample_selector_widget.setVisible(False)
        bar.addWidget(self.sample_selector_widget)

        return bar

    # ── Left panel (inputs) ───────────────────────────────────────────

    def _build_left_panel(self) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setObjectName("leftScroll")

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 6, 0)
        layout.setSpacing(10)

        # Header label
        hdr = QLabel("Input Data")
        hdr.setObjectName("panelHeader")
        hdr.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        layout.addWidget(hdr)

        # Main oxides group
        ox_group = QGroupBox("Oxides")
        ox_layout = QVBoxLayout(ox_group)
        ox_layout.setContentsMargins(6, 10, 6, 6)

        self.table = AutoSelectTableWidget(15, 2)
        self.table.setHorizontalHeaderLabels(["Oxide", "wt. %"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self._populate_oxide_table()
        # ← tweak this pixel value to taste
        self._fit_table_height(self.table, fixed_height=486)
        ox_layout.addWidget(self.table)
        layout.addWidget(ox_group)

        # ── Iron System ───────────────────────────────────────────
        self.spin_feo_tot   = self._create_spinbox(0, 100, 0.1,  3, suffix=" wt%")
        self.spin_feo       = self._create_spinbox(0, 100, 0.1,  3, suffix=" wt%")
        self.spin_fe2o3     = self._create_spinbox(0, 100, 0.1,  3, suffix=" wt%")
        self.spin_fe3_ratio = self._create_spinbox(0, 1,   0.05, 3, kind="ratio")
        self.spin_fe2_wt    = self._create_spinbox(0, 100,       0.01, 4, suffix=" wt%")
        self.spin_fe2_ugg   = self._create_spinbox(0, 1_000_000, 1.0,  1, suffix=" µg/g", min_width=92)
        self.spin_fe3_wt    = self._create_spinbox(0, 100,       0.01, 4, suffix=" wt%")
        self.spin_fe3_ugg   = self._create_spinbox(0, 1_000_000, 1.0,  1, suffix=" µg/g", min_width=92)
        self.spin_feo_tot.setToolTip("Total iron expressed as FeO.")
        self.spin_feo.setToolTip("Ferrous oxide FeO (real-oxide view of the same DOF as Fe²⁺).")
        self.spin_fe2o3.setToolTip("Ferric oxide Fe₂O₃ (real-oxide view of the same DOF as Fe³⁺).")
        self.spin_fe3_ratio.setToolTip("Molar fraction of total Fe present as ferric (Fe³⁺).")
        self.spin_fe2_wt.setToolTip("Ferrous iron (Fe²⁺) as wt.% element.")
        self.spin_fe2_ugg.setToolTip("Ferrous iron (Fe²⁺) as elemental Fe in µg/g.")
        self.spin_fe3_wt.setToolTip("Ferric iron (Fe³⁺) as wt.% element.")
        self.spin_fe3_ugg.setToolTip("Ferric iron (Fe³⁺) as elemental Fe in µg/g.")

        fe_group = QGroupBox("Iron System")
        fe_outer = QVBoxLayout(fe_group)
        fe_outer.setContentsMargins(8, 14, 8, 8)
        fe_outer.setSpacing(6)
        fe_always = QFormLayout()
        fe_always.setLabelAlignment(Qt.AlignLeft)
        fe_always.setSpacing(4)
        fe_always.addRow("FeO total:",      self.spin_feo_tot)
        fe_always.addRow("FeO:",            self.spin_feo)
        fe_always.addRow("Fe₂O₃:",          self.spin_fe2o3)
        fe_always.addRow("Fe³⁺/ΣFe ratio:", self.spin_fe3_ratio)
        fe_outer.addLayout(fe_always)
        fe_outer.addWidget(self._make_bar_caption("Fe speciation (mol %)"))
        self.bar_iron = RedoxBar([
            ("Fe³⁺", COLOR_OXIDIZED),
            ("Fe²⁺", COLOR_REDUCED),
        ])
        fe_outer.addWidget(self.bar_iron)
        self.collapse_iron = CollapsibleSection("Species (wt% · µg/g)")
        self.collapse_iron.hide_always_area()
        fe_extra = self.collapse_iron.extra_layout()
        fe_extra.addRow("Fe²⁺ :", self._pair_row(self.spin_fe2_wt, self.spin_fe2_ugg))
        fe_extra.addRow("Fe³⁺ :", self._pair_row(self.spin_fe3_wt, self.spin_fe3_ugg))
        fe_outer.addWidget(self.collapse_iron)
        layout.addWidget(fe_group)

        # ── Carbon System ─────────────────────────────────────────
        self.spin_c_wt            = self._create_spinbox(0, 100,       0.001, 4, suffix=" wt%")
        self.spin_c_ugg           = self._create_spinbox(0, 1_000_000, 1.0,   1, suffix=" µg/g", min_width=92)
        self.spin_co2_ratio       = self._create_spinbox(0, 1,         0.01,  3, kind="ratio")
        self.spin_c_graphite_wt   = self._create_spinbox(0, 100,       0.001, 4, suffix=" wt%")
        self.spin_c_graphite_ugg  = self._create_spinbox(0, 1_000_000, 1.0,   1, suffix=" µg/g", min_width=92)
        self.spin_c_carbonate_wt  = self._create_spinbox(0, 100,       0.001, 4, suffix=" wt%")
        self.spin_c_carbonates_ugg= self._create_spinbox(0, 1_000_000, 1.0,   1, suffix=" µg/g", min_width=92)
        self.spin_c_wt.setToolTip("Total carbon as element C.")
        self.spin_c_ugg.setToolTip("Total carbon as element C.")
        self.spin_co2_ratio.setToolTip("Molar fraction of total C present as carbonate (C⁴⁺) vs graphite (C⁰).")
        self.spin_c_graphite_wt.setToolTip("Graphite / elemental carbon (reduced). Contributes no oxygen to the O₂ budget.")
        self.spin_c_graphite_ugg.setToolTip("Graphite / elemental carbon (reduced). Contributes no oxygen to the O₂ budget.")
        self.spin_c_carbonate_wt.setToolTip("Carbonate carbon (oxidized). C + O₂ → CO₂.")
        self.spin_c_carbonates_ugg.setToolTip("Carbonate carbon (oxidized). C + O₂ → CO₂.")

        c_group = QGroupBox("Carbon System")
        c_outer = QVBoxLayout(c_group)
        c_outer.setContentsMargins(8, 14, 8, 8)
        c_outer.setSpacing(6)
        c_always = QFormLayout()
        c_always.setLabelAlignment(Qt.AlignLeft)
        c_always.setSpacing(4)
        self.lbl_co2_real = QLabel("0.000 wt%")
        self.lbl_co2_real.setObjectName("realOxideLabel")
        self.lbl_co2_real.setToolTip("Carbonate carbon expressed as CO₂ mass.")
        c_always.addRow("C total:",      self._pair_row(self.spin_c_wt, self.spin_c_ugg))
        c_always.addRow("CO₂:",          self.lbl_co2_real)
        c_always.addRow("C⁴⁺/ΣC ratio:", self.spin_co2_ratio)
        c_outer.addLayout(c_always)
        c_outer.addWidget(self._make_bar_caption("C speciation (mol %)"))
        self.bar_carbon = RedoxBar([
            ("C⁴⁺", COLOR_OXIDIZED),
            ("C⁰",  COLOR_REDUCED),
        ])
        c_outer.addWidget(self.bar_carbon)
        self.collapse_carbon = CollapsibleSection("Species (wt% · µg/g)")
        self.collapse_carbon.hide_always_area()
        c_extra = self.collapse_carbon.extra_layout()
        c_extra.addRow("C⁰ (in graphite):",   self._pair_row(self.spin_c_graphite_wt,  self.spin_c_graphite_ugg))
        c_extra.addRow("C⁴⁺ (in carbonate):", self._pair_row(self.spin_c_carbonate_wt, self.spin_c_carbonates_ugg))
        c_outer.addWidget(self.collapse_carbon)
        layout.addWidget(c_group)

        # ── Sulfur System ─────────────────────────────────────────
        self.spin_s_wt           = self._create_spinbox(0, 100,       0.001, 4, suffix=" wt%")
        self.spin_s_ugg          = self._create_spinbox(0, 1_000_000, 1.0,   1, suffix=" µg/g", min_width=92)
        self.spin_so3_ratio      = self._create_spinbox(0, 1,         0.01,  3, kind="ratio")
        self.spin_s1_ratio       = self._create_spinbox(0, 1,         0.01,  3, kind="ratio")
        self.spin_s_sulfate_wt   = self._create_spinbox(0, 100,       0.001, 4, suffix=" wt%")
        self.spin_s_sulfate_ugg  = self._create_spinbox(0, 1_000_000, 1.0,   1, suffix=" µg/g", min_width=92)
        self.spin_s1minus_wt     = self._create_spinbox(0, 100,       0.001, 4, suffix=" wt%")
        self.spin_s1minus_ugg    = self._create_spinbox(0, 1_000_000, 1.0,   1, suffix=" µg/g", min_width=92)
        self.spin_s2minus_wt     = self._create_spinbox(0, 100,       0.001, 4, suffix=" wt%")
        self.spin_s2minus_ugg    = self._create_spinbox(0, 1_000_000, 1.0,   1, suffix=" µg/g", min_width=92)
        self.spin_s_wt.setToolTip("Total sulfur as element S.")
        self.spin_s_ugg.setToolTip("Total sulfur as element S.")
        self.spin_so3_ratio.setToolTip("Molar fraction of total S present as sulfate (oxidized).")
        self.spin_s1_ratio.setToolTip("Molar fraction of reduced S present as disulfide (S¹⁻) vs monosulfide (S²⁻).")
        self.spin_s_sulfate_wt.setToolTip("Sulfate sulfur (oxidized). Carries real oxygen (SO₃); NOT subject to phantom-O correction.")
        self.spin_s_sulfate_ugg.setToolTip("Sulfate sulfur (oxidized). Carries real oxygen (SO₃); NOT subject to phantom-O correction.")
        self.spin_s1minus_wt.setToolTip("Disulfide sulfur (pyrite-type, MS₂). Phantom-O correction: 0.5 O per S atom.")
        self.spin_s1minus_ugg.setToolTip("Disulfide sulfur (pyrite-type, MS₂). Phantom-O correction: 0.5 O per S atom.")
        self.spin_s2minus_wt.setToolTip("Monosulfide sulfur (MS). Phantom-O correction: 1.0 O per S atom.")
        self.spin_s2minus_ugg.setToolTip("Monosulfide sulfur (MS). Phantom-O correction: 1.0 O per S atom.")

        s_group = QGroupBox("Sulfur System")
        s_outer = QVBoxLayout(s_group)
        s_outer.setContentsMargins(8, 14, 8, 8)
        s_outer.setSpacing(6)
        s_always = QFormLayout()
        s_always.setLabelAlignment(Qt.AlignLeft)
        s_always.setSpacing(4)
        self.lbl_so3_real = QLabel("0.000 wt%")
        self.lbl_so3_real.setObjectName("realOxideLabel")
        self.lbl_so3_real.setToolTip("Sulfate sulfur expressed as SO₃ mass.")
        s_always.addRow("S total:",                self._pair_row(self.spin_s_wt, self.spin_s_ugg))
        s_always.addRow("SO₃:",                    self.lbl_so3_real)
        s_always.addRow("S⁶⁺/ΣS ratio:",          self.spin_so3_ratio)
        s_always.addRow("S¹⁻/Sˢᵘˡᶠⁱᵈᵉˢ ratio:", self.spin_s1_ratio)
        s_outer.addLayout(s_always)
        s_outer.addWidget(self._make_bar_caption("S speciation (mol %)"))
        self.bar_sulfur = RedoxBar([
            ("S⁶⁺", COLOR_OXIDIZED),
            ("S¹⁻", COLOR_INTERMEDIATE),
            ("S²⁻", COLOR_REDUCED),
        ])
        s_outer.addWidget(self.bar_sulfur)
        self.collapse_sulfur = CollapsibleSection("Species (wt% · µg/g)")
        self.collapse_sulfur.hide_always_area()
        s_extra = self.collapse_sulfur.extra_layout()
        s_extra.addRow("S⁶⁺ (in sulfate):", self._pair_row(self.spin_s_sulfate_wt, self.spin_s_sulfate_ugg))
        s_extra.addRow("S¹⁻ (in disulfide):", self._pair_row(self.spin_s1minus_wt,   self.spin_s1minus_ugg))
        s_extra.addRow("S²⁻ (in monosulfide):", self._pair_row(self.spin_s2minus_wt,   self.spin_s2minus_ugg))
        s_outer.addWidget(self.collapse_sulfur)
        layout.addWidget(s_group)

        # ── Color-grammar legend (once, at the bottom) ────────────
        layout.addWidget(self._build_color_legend())

        scroll.setWidget(content)
        return scroll

    # ── Right panel (computed results) ────────────────────────────────

    def _build_right_panel(self) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setObjectName("rightScroll")

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(6, 0, 0, 0)
        layout.setSpacing(10)

        # ── Header row: title label + View combobox ──────────────
        from ..core.targets.registry import list_targets as _list_targets
        from ..core.targets.registry import get_adapter as _get_adp
        hdr_row = QWidget()
        hdr_row.setObjectName("panelHeaderRow")
        hdr_hl = QHBoxLayout(hdr_row)
        hdr_hl.setContentsMargins(0, 0, 0, 0)
        hdr_hl.setSpacing(6)
        hdr = QLabel("Computed Results")
        hdr.setObjectName("panelHeaderResult")
        hdr.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        hdr_hl.addWidget(hdr)
        hdr_hl.addStretch()
        view_lbl = QLabel("View:")
        view_lbl.setObjectName("panelHeaderViewLabel")
        hdr_hl.addWidget(view_lbl)
        self._result_view_combo = QComboBox()
        self._result_view_combo.setObjectName("resultViewCombo")
        for _name in _list_targets():
            _adp = _get_adp(_name)
            self._result_view_combo.addItem(_adp.display_name, userData=_name)
        self._result_view_combo.currentIndexChanged.connect(self._on_result_view_changed)
        hdr_hl.addWidget(self._result_view_combo)
        layout.addWidget(hdr_row)

        # ── Elements/Oxides table (content driven by active tab) ────
        self._el_group = QGroupBox("Elements")
        el_layout = QVBoxLayout(self._el_group)
        el_layout.setContentsMargins(6, 10, 6, 6)

        self.el_table = QTableWidget(16, 2)
        self.el_table.setHorizontalHeaderLabels(["Element", "mol / kg of rock"])
        self.el_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.el_table.verticalHeader().setVisible(False)
        self.el_table.setAlternatingRowColors(True)
        self.el_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._populate_element_table()
        self._fit_table_height(self.el_table, fixed_height=516)
        el_layout.addWidget(self.el_table)
        layout.addWidget(self._el_group)

        # ── Warning banner — shown only when a warning is present ──
        self._result_warning_label = QLabel()
        self._result_warning_label.setObjectName("previewWarning")
        self._result_warning_label.setWordWrap(True)
        self._result_warning_label.setVisible(False)
        layout.addWidget(self._result_warning_label)

        # ── Totals (with target-dependent bottom section) ───────────
        totals_group = QGroupBox("Totals")
        totals_main = QVBoxLayout(totals_group)
        totals_main.setContentsMargins(10, 12, 10, 10)
        totals_main.setSpacing(5)

        self.lbl_loi_m           = QLabel("0.00")
        self.lbl_total_calc       = QLabel("0.00")
        self.lbl_total_model      = QLabel("0.00")
        self.lbl_total_model_corr = QLabel("0.00")
        for lbl in [self.lbl_loi_m, self.lbl_total_calc,
                    self.lbl_total_model, self.lbl_total_model_corr]:
            lbl.setObjectName("resultLabel")

        totals_static = QFormLayout()
        totals_static.setLabelAlignment(Qt.AlignLeft)
        totals_static.setSpacing(5)
        totals_static.addRow("LOI:", self.lbl_loi_m)
        totals_static.addRow(self._make_separator())
        totals_static.addRow("Total (wt.%):",                   self.lbl_total_calc)
        totals_static.addRow("Total model (wt.%):",             self.lbl_total_model)
        totals_static.addRow("Total model O-corr. (wt.%):",    self.lbl_total_model_corr)
        self.lbl_total_model_corr.setToolTip(
            "Sum of oxides after redox + phantom-O correction; the normalization basis for mol/kg."
        )
        totals_main.addLayout(totals_static)

        # Perple_X basis mass
        _perp_w = QWidget()
        _perp_f = QFormLayout(_perp_w)
        _perp_f.setContentsMargins(0, 4, 0, 0)
        _perp_f.setSpacing(5)
        _perp_f.setLabelAlignment(Qt.AlignLeft)
        self.lbl_basis_mass = QLabel("0.00")
        self.lbl_basis_mass.setObjectName("resultLabel")
        self.lbl_basis_mass.setToolTip(
            "Mass of one normalized kg reconstructed from the molar components; must equal 1000 g/kg."
        )
        _perp_f.addRow("Mass-closure check (g/kg):", self.lbl_basis_mass)
        totals_main.addWidget(_perp_w)
        layout.addWidget(totals_group)

        # ── Export preview (collapsible, collapsed by default) ────────────────
        self._preview_section = CollapsibleSection("Export preview")
        self._preview_section.hide_always_area()

        # Copy button row
        _copy_row = QWidget()
        _copy_hl = QHBoxLayout(_copy_row)
        _copy_hl.setContentsMargins(0, 0, 0, 4)
        _copy_hl.setSpacing(0)
        _copy_hl.addStretch()
        self._btn_copy_preview = QPushButton("Copy to clipboard")
        self._btn_copy_preview.setObjectName("btnCopyPreview")
        self._btn_copy_preview.clicked.connect(self._on_copy_preview)
        _copy_hl.addWidget(self._btn_copy_preview)
        self._preview_section.extra_layout().addRow(_copy_row)

        # Text area
        self._export_preview_text = QPlainTextEdit()
        self._export_preview_text.setObjectName("exportPreview")
        self._export_preview_text.setReadOnly(True)
        self._export_preview_text.setLineWrapMode(QPlainTextEdit.NoWrap)
        self._export_preview_text.setFixedHeight(220)
        self._preview_section.extra_layout().addRow(self._export_preview_text)

        layout.addWidget(self._preview_section)

        layout.addStretch()

        scroll.setWidget(content)
        return scroll

    # ------------------------------------------------------------------
    # Table population
    # ------------------------------------------------------------------

    def _populate_oxide_table(self):
        """Fill the 15-row oxide table: editable simple oxides + read-only Fe₂O₃ total / CO₂ / SO₃ rows."""
        rows = [
            "SiO₂", "TiO₂", "Al₂O₃", "Cr₂O₃", "MnO", "MgO",
            "CaO", "NiO", "Na₂O", "K₂O", "P₂O₅", "H₂O",
            "Fe₂O₃ total", "CO₂ total", "SO₃ total",
        ]
        editable_rows = {0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11}
        dark_bg    = QColor("#3B4252")
        light_bg   = QColor("#434C5E")
        ro_bg      = QColor("#353B49")

        for row, oxide in enumerate(rows):
            is_editable = row in editable_rows

            item_oxide = QTableWidgetItem(oxide)
            item_oxide.setFlags(Qt.ItemIsEnabled)
            item_oxide.setBackground(dark_bg)
            item_oxide.setForeground(QColor("#B8B8B8"))
            self.table.setItem(row, 0, item_oxide)

            item_wt = QTableWidgetItem("0.000")
            item_wt.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            if is_editable:
                item_wt.setBackground(light_bg)
                item_wt.setForeground(QColor("#ECEFF4"))
            else:
                item_wt.setFlags(Qt.ItemIsEnabled)
                item_wt.setBackground(ro_bg)
                item_wt.setForeground(QColor("#81A1C1"))
            self.table.setItem(row, 1, item_wt)

    def _populate_element_table(self):
        """Fill the read-only element/mol table on the right panel (16 rows, aligned with Oxides)."""
        rows = [
            ("Si", ""), ("Ti", ""), ("Al", ""), ("Cr", ""), ("Mn", ""),
            ("Mg", ""), ("Ca", ""), ("Ni", ""), ("Na", ""), ("K",  ""),
            ("P",  ""), ("H₂",""), ("Fe",""), ("C", ""), ("S₂",""), ("O₂",""),
        ]
        dark_bg = QColor("#3B4252")
        for row, (elem, _) in enumerate(rows):
            item_el = QTableWidgetItem(elem)
            item_el.setFlags(Qt.ItemIsEnabled)
            item_el.setBackground(dark_bg)
            item_el.setForeground(QColor("#B8B8B8"))
            self.el_table.setItem(row, 0, item_el)

            item_val = QTableWidgetItem("")
            item_val.setFlags(Qt.ItemIsEnabled)
            item_val.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            item_val.setBackground(dark_bg)
            item_val.setForeground(QColor("#81A1C1"))
            self.el_table.setItem(row, 1, item_val)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _create_spinbox(self, min_val, max_val, step, decimals,
                        suffix: str | None = None,
                        kind: str | None = None,
                        min_width: int | None = None) -> AutoSelectSpinBox:
        sb = AutoSelectSpinBox()
        sb.setRange(min_val, max_val)
        sb.setSingleStep(step)
        sb.setDecimals(decimals)
        sb.setKeyboardTracking(False)
        sb.setFocusPolicy(Qt.StrongFocus)
        if suffix:
            sb.setSuffix(suffix)
        if kind == "ratio":
            sb.setObjectName("ratioSpin")
        if min_width is not None:
            sb.setMinimumWidth(min_width)
        return sb

    def _make_separator(self) -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        line.setStyleSheet("background-color: #4C566A;")
        return line

    def _pair_row(self, spin_wt: QDoubleSpinBox,
                  spin_ugg: QDoubleSpinBox) -> QWidget:
        """Compose a single QFormLayout field cell holding [wt%] [µg/g] side-by-side."""
        container = QWidget()
        h = QHBoxLayout(container)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(6)
        h.addWidget(spin_wt)
        h.addWidget(spin_ugg)
        return container

    def _make_sub_header(self, text: str) -> QLabel:
        """Italic muted label used as a mineral-model sub-header above species rows."""
        lbl = QLabel(text)
        lbl.setObjectName("speciesSubHeader")
        return lbl

    def _make_bar_caption(self, text: str) -> QLabel:
        """Small caption above a redox bar; tooltip explains mol% ≡ wt% for single-element speciation."""
        lbl = QLabel(text)
        lbl.setObjectName("barCaption")
        lbl.setToolTip(
            "Segments are molar fractions of the element among its redox species — "
            "driven by the molar ratios (so3_stot_ratio, s1_sred_ratio, "
            "co2_ctot_ratio, fe3_fetot_ratio). Because all segments of a bar are the "
            "same element, the atomic mass cancels and these molar fractions are "
            "numerically identical to the corresponding weight fractions. The label "
            "reads mol % to match the ratios that control them; for single-element "
            "speciation mol % ≡ wt %."
        )
        return lbl

    def _build_color_legend(self) -> QWidget:
        """One-row legend strip at the bottom of the input column."""
        container = QWidget()
        h = QHBoxLayout(container)
        h.setContentsMargins(4, 4, 4, 4)
        h.setSpacing(10)

        def swatch(color_hex: str, text: str) -> QWidget:
            row = QWidget()
            rh = QHBoxLayout(row)
            rh.setContentsMargins(0, 0, 0, 0)
            rh.setSpacing(4)
            sw = QFrame()
            sw.setFixedSize(14, 10)
            sw.setStyleSheet(f"background-color: {color_hex}; border-radius: 2px;")
            label = QLabel(text)
            label.setObjectName("legendLabel")
            rh.addWidget(sw)
            rh.addWidget(label)
            return row

        h.addWidget(QLabel("Redox legend:"))
        h.addWidget(swatch(COLOR_OXIDIZED,     "oxidized (Fe³⁺, C⁴⁺, S⁶⁺)"))
        h.addWidget(swatch(COLOR_INTERMEDIATE, "intermediate (S¹⁻)"))
        h.addWidget(swatch(COLOR_REDUCED,      "reduced (Fe²⁺, C⁰, S²⁻)"))
        h.addStretch()
        return container

    def _fit_table_height(self, table: QTableWidget, fixed_height: int | None = None) -> None:
        table.setSizeAdjustPolicy(QAbstractScrollArea.SizeAdjustPolicy.AdjustToContents)
        table.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        # Lock vertical size so neighbouring widgets in QSplitter / QVBoxLayout
        # can never steal space and clip rows.
        table.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        if fixed_height is not None:
            natural_h = fixed_height
        else:
            rows_h = sum(table.rowHeight(i) for i in range(table.rowCount()))
            natural_h = (
                table.horizontalHeader().sizeHint().height()
                + rows_h
                + 2 * table.frameWidth()
            )
        table.setMinimumHeight(natural_h)
        table.setFixedHeight(natural_h)

    def _apply_quality_color(self, label: QLabel, value: float, target: float,
                              ok_tol: float, warn_tol: float) -> None:
        """Color a totals label by closeness to target (green / amber / red)."""
        diff = abs(value - target)
        if diff <= ok_tol:
            color = COLOR_OK
        elif diff <= warn_tol:
            color = COLOR_WARN
        else:
            color = COLOR_BAD
        label.setStyleSheet(f"color: {color}; font-weight: bold; "
                            f"font-family: 'Roboto Mono', 'Consolas', monospace;")

    @staticmethod
    def _extract_component_block(render_text: str) -> str:
        """Return the thermodynamic component list block from adapter render output."""
        BEGIN = "begin thermodynamic component list"
        END   = "end thermodynamic component list"
        b = render_text.find(BEGIN)
        if b == -1:
            return render_text
        e = render_text.find(END, b)
        if e == -1:
            return render_text[b:]
        return render_text[b: e + len(END)]

    def _on_copy_preview(self) -> None:
        """Copy the current export preview text to the system clipboard."""
        QApplication.clipboard().setText(self._export_preview_text.toPlainText())

    def _normalize_oxide_name(self, name: str) -> str:
        subscript_map = str.maketrans('₀₁₂₃₄₅₆₇₈₉', '0123456789')
        subscript_letters = str.maketrans('ₜₒₐₗ', 'toal')
        name = name.translate(subscript_letters).translate(subscript_map)
        name = name.replace('toal', 't')
        return name

    def _sanitize_filename(self, text: str) -> str:
        sanitized = re.sub(r'[\\/:*?"<>|]', '_', text)
        sanitized = re.sub(r'_+', '_', sanitized)
        return sanitized.strip().strip('_')

    # ------------------------------------------------------------------
    # Model connections
    # ------------------------------------------------------------------

    def _setup_connections(self):
        # Drive every editable spinbox connection from the single SPEC_FIELDS
        # registry so the wiring cannot drift from the refresh / tab-order lists.
        for field in SPEC_FIELDS:
            spin = getattr(self, field.spin_attr)
            sysname, propname = field.system, field.prop
            spin.valueChanged.connect(
                lambda v, s=sysname, p=propname: self._update_model(s, p, v)
            )

        # Table
        self.table.cellChanged.connect(self._on_table_change)

    def _update_model(self, system_name, property_name, value):
        system = getattr(self.model, system_name)
        setattr(system, property_name, value)
        self.model.emit_updated()

    def _on_table_change(self, row, col):
        if col != 1:
            return
        # Rows 12-15 (FeO, Fe2O3, CO2, SO3) are read-only computed displays.
        if row > 11:
            return
        try:
            val = float(self.table.item(row, 1).text())
        except ValueError:
            return
        oxide = self.table.item(row, 0).text()
        oxide_key = self._normalize_oxide_name(oxide)
        self.model.set_oxide_wt(oxide_key, val)
        self.model.emit_updated()

    # ------------------------------------------------------------------
    # refresh_ui — synchronise GUI ← model
    # ------------------------------------------------------------------

    def refresh_ui(self):
        self.blockSignals(True)
        self.table.blockSignals(True)
        # Block every editable spinbox before writing values from the model.
        # Multiple spinboxes within one system are bidirectional views of the
        # same DOFs (totals / ratio / species / real-oxide); writing one would
        # fire the others without this guard.
        all_spinboxes = [getattr(self, f.spin_attr) for f in SPEC_FIELDS]
        for sp in all_spinboxes:
            sp.blockSignals(True)

        try:
            # ── Editable spinboxes — written from SPEC_FIELDS ──
            for field in SPEC_FIELDS:
                spin = getattr(self, field.spin_attr)
                sysobj = getattr(self.model, field.system)
                spin.setValue(getattr(sysobj, field.prop))

            # ── Totals ──
            self.lbl_loi_m.setText(f"{self.model.loi_display:.2f}")
            self.lbl_total_calc.setText(f"{self.model.total_calculated:.2f}")
            self.lbl_total_model.setText(f"{self.model.total_model:.2f}")
            total_corr = self.model.total_model_redox_corrected
            self.lbl_total_model_corr.setText(f"{total_corr:.2f}")
            self._apply_quality_color(self.lbl_total_model_corr, total_corr, 100.0, 0.5, 2.0)

            # ── Redox speciation bars (read-only) ──
            self.bar_iron.set_values([
                self.model.iron.fe3_wt,
                self.model.iron.fe2_wt,
            ])
            self.bar_carbon.set_values([
                self.model.carbon.c4_wt,
                self.model.carbon.c0_wt,
            ])
            self.bar_sulfur.set_values([
                self.model.sulfur.s6_wt,
                self.model.sulfur.s1_wt,
                self.model.sulfur.s2_wt,
            ])

            # ── Read-only real-oxide displays inside species collapsibles ──
            # co2_real_wt = ONLY the carbonate-C fraction expressed as CO₂ mass.
            # so3_real_wt = ONLY the sulfate-S  fraction expressed as SO₃ mass.
            # (vs carbon.co2_wt / sulfur.so3_wt which express *total* C / S as the oxide.)
            self.lbl_co2_real.setText(f"{self.model.carbon.c4_oxide_wt:.3f} wt%")
            self.lbl_so3_real.setText(f"{self.model.sulfur.s6_oxide_wt:.3f} wt%")

            # ── H2O editability based on volatile mode ──
            h2o_item = self.table.item(11, 1)
            if h2o_item:
                if self.model._volatile_mode == "h2o_derived":
                    h2o_item.setFlags(Qt.ItemIsEnabled)
                    h2o_item.setBackground(QColor("#353B49"))
                    h2o_item.setForeground(QColor("#81A1C1"))
                else:
                    h2o_item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEditable | Qt.ItemIsEnabled)
                    h2o_item.setBackground(QColor("#434C5E"))
                    h2o_item.setForeground(QColor("#ECEFF4"))

            # ── Oxide table (wt. %, left panel) ──
            simple_map = {
                0: "SiO2",  1: "TiO2", 2: "Al2O3", 3: "Cr2O3", 4: "MnO",
                5: "MgO",   6: "CaO",  7: "NiO",   8: "Na2O",  9: "K2O",
                10: "P2O5", 11: "H2O",
            }
            for row, key in simple_map.items():
                item = self.table.item(row, 1)
                if item:
                    item.setText(f"{self.model.get_oxide_wt(key):.3f}")

            # ── Computed oxide rows (read-only) ──
            computed_oxide = {
                12: self.model.iron.fe2o3_tot_wt,
                13: self.model.carbon.co2_wt,
                14: self.model.sulfur.so3_wt,
            }
            for row, val in computed_oxide.items():
                item = self.table.item(row, 1)
                if item:
                    item.setText(f"{val:.3f}")

            # ── Element table (mol/kg, right panel) ──
            # Content is rebuilt by _refresh_result_view() which runs after
            # this try/finally block — do not update el_table here.

        finally:
            self.table.blockSignals(False)
            for sp in all_spinboxes:
                sp.blockSignals(False)
            self.blockSignals(False)

        # ── Result view (tab-driven table + totals) ──────────────────
        self._refresh_result_view()

    # ------------------------------------------------------------------
    # TAB order
    # ------------------------------------------------------------------

    def _setup_tab_order(self):
        spinbox_chain = [getattr(self, f.spin_attr) for f in SPEC_FIELDS]
        self.setTabOrder(self.table, self.sample_name_input)
        if spinbox_chain:
            self.setTabOrder(self.sample_name_input, spinbox_chain[0])
        for i in range(len(spinbox_chain) - 1):
            self.setTabOrder(spinbox_chain[i], spinbox_chain[i + 1])
        self.table.setCurrentCell(0, 1)

    # ------------------------------------------------------------------
    # Styling — Nord Dark
    # ------------------------------------------------------------------

    def _apply_styling(self):
        FS = self.FONT_SIZE_MAIN
        FH = self.FONT_SIZE_HEADING
        FS_SMALL = self.FONT_SIZE_SMALL
        FW = self.FONT_SIZE_WARN
        FP = self.FONT_SIZE_PREVIEW
        self.setStyleSheet(f"""
            QMainWindow, QWidget {{
                background-color: #2E3440;
                color: #ECEFF4;
                font-family: 'Inter', 'Segoe UI', 'Helvetica Neue', sans-serif;
                font-size: {FS}px;
            }}

            /* ── Panel headers ─────────────────────────────────── */
            QLabel#panelHeader {{
                font-size: {FH}px;
                font-weight: bold;
                color: #A3BE8C;
                padding: 4px 0 2px 2px;
                background: transparent;
                border-bottom: 2px solid #A3BE8C;
            }}
            QLabel#panelHeaderResult {{
                font-size: {FH}px;
                font-weight: bold;
                color: #81A1C1;
                padding: 4px 0 2px 2px;
                background: transparent;
                border-bottom: 2px solid #81A1C1;
            }}

            /* ── Group boxes ───────────────────────────────────── */
            QGroupBox {{
                background-color: #3B4252;
                border: 1px solid #4C566A;
                border-radius: 6px;
                margin-top: 14px;
                padding: 14px 8px 8px 8px;
                font-weight: bold;
                color: #88C0D0;
                font-size: {FH}px;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 5px;
            }}

            /* ── Collapsible sections ──────────────────────────── */
            QFrame#collapsibleFrame {{
                background-color: #3B4252;
                border: 1px solid #4C566A;
                border-radius: 6px;
            }}
            QToolButton#collapsibleHeader {{
                background-color: #434C5E;
                color: #88C0D0;
                font-weight: bold;
                font-size: {FS_SMALL}px;
                border: none;
                border-bottom: 1px solid #4C566A;
                border-radius: 0px;
                padding: 4px 8px;
                text-align: left;
            }}
            QToolButton#collapsibleHeader:hover {{
                background-color: #4C566A;
            }}
            QWidget#collapsibleAlways {{
                background-color: transparent;
            }}
            QWidget#collapsibleExtra {{
                background-color: #323844;
                font-size: {FS_SMALL}px;
            }}
            QFrame#collapsibleSep {{
                background-color: #4C566A;
                max-height: 1px;
            }}

            /* ── Tables ────────────────────────────────────────── */
            QTableWidget {{
                background-color: #3B4252;
                border: 1px solid #4C566A;
                gridline-color: #4C566A;
                selection-background-color: #4C566A;
                font-family: 'Roboto Mono', 'Consolas', monospace;
                font-size: {FS}px;
            }}
            QTableWidget::item {{ padding: 3px 7px; }}
            QHeaderView::section {{
                background-color: #434C5E;
                color: #81A1C1;
                padding: 5px;
                border: 1px solid #4C566A;
                font-weight: bold;
                font-family: 'Inter', 'Segoe UI', sans-serif;
            }}

            /* ── Spinboxes ─────────────────────────────────────── */
            QDoubleSpinBox {{
                background-color: #434C5E;
                border: 1px solid #4C566A;
                border-left: 3px solid #5E81AC;
                border-radius: 4px;
                padding: 3px 6px;
                color: #ECEFF4;
                min-width: 90px;
                font-family: 'Roboto Mono', 'Consolas', monospace;
            }}
            QDoubleSpinBox#ratioSpin {{
                border-left: 3px solid #A3BE8C;
            }}
            QDoubleSpinBox:focus {{
                border-color: #88C0D0;
                border-left-color: #88C0D0;
            }}
            QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
                background-color: #4C566A;
                border: 1px solid #3B4252;
                border-radius: 2px;
                width: 14px;
            }}
            QDoubleSpinBox::up-button {{ subcontrol-position: top right; }}
            QDoubleSpinBox::down-button {{ subcontrol-position: bottom right; }}
            QDoubleSpinBox::up-button:hover, QDoubleSpinBox::down-button:hover {{
                background-color: #5E81AC;
            }}
            QDoubleSpinBox::up-arrow {{
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-bottom: 5px solid #ECEFF4;
                width: 0; height: 0; margin: 2px;
            }}
            QDoubleSpinBox::down-arrow {{
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 5px solid #ECEFF4;
                width: 0; height: 0; margin: 2px;
            }}

            /* ── Labels ────────────────────────────────────────── */
            QLabel {{
                color: #D8DEE9;
                background-color: transparent;
            }}
            QLabel#resultLabel {{
                font-weight: bold;
                color: #88C0D0;
                font-family: 'Roboto Mono', 'Consolas', monospace;
            }}
            QLabel#speciesSubHeader {{
                color: #7E8AA0;
                font-style: italic;
                font-size: 11px;
                padding: 2px 0 2px 0;
            }}
            QLabel#barCaption {{
                color: #7E8AA0;
                font-size: 11px;
                padding: 4px 0 0 0;
            }}
            QLabel#realOxideLabel {{
                color: #81A1C1;
                font-weight: bold;
                font-family: 'Roboto Mono', 'Consolas', monospace;
                background-color: #353B49;
                padding: 3px 6px;
                border-radius: 3px;
            }}
            QLabel#legendLabel {{
                color: #7E8AA0;
                font-size: 11px;
            }}

            /* ── Scroll areas ───────────────────────────────────── */
            QScrollArea {{ background-color: transparent; border: none; }}

            /* ── Buttons ───────────────────────────────────────── */
            QPushButton {{
                background-color: #434C5E;
                color: #ECEFF4;
                border: 1px solid #4C566A;
                border-radius: 4px;
                padding: 5px 12px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: #4C566A;
                border: 1px solid #88C0D0;
            }}
            QPushButton:pressed {{ background-color: #3B4252; }}
            QPushButton#btnImport {{
                border-left: 3px solid #A3BE8C;
            }}
            QPushButton#btnImport:hover {{ border-color: #A3BE8C; }}
            QPushButton#btnExport {{
                border-left: 3px solid #EBCB8B;
            }}
            QPushButton#btnExport:hover {{ border-color: #EBCB8B; }}

            QPushButton#btnSettings {{
                border-left: 3px solid #88C0D0;
            }}
            QPushButton#btnSettings:hover {{ border-color: #88C0D0; }}

            /* ── LineEdit / ComboBox ────────────────────────────── */
            QLineEdit, QComboBox {{
                background-color: #434C5E;
                border: 1px solid #4C566A;
                border-radius: 4px;
                padding: 3px 7px;
                color: #ECEFF4;
            }}
            QLineEdit:focus, QComboBox:focus {{ border-color: #88C0D0; }}
            QComboBox::drop-down {{ border: none; }}

            /* ── Result target tab bar ─────────────────────────── */
            QTabBar#resultTabBar {{
                background-color: transparent;
            }}
            QTabBar#resultTabBar::tab {{
                background-color: #3B4252;
                color: #7E8AA0;
                border: 1px solid #4C566A;
                border-bottom: none;
                border-radius: 4px 4px 0 0;
                padding: 4px 10px;
                font-size: {FS_SMALL}px;
                min-width: 100px;
            }}
            QTabBar#resultTabBar::tab:selected {{
                background-color: #434C5E;
                color: #88C0D0;
                font-weight: bold;
            }}
            QTabBar#resultTabBar::tab:hover {{ background-color: #4C566A; }}
            QLabel#previewWarning {{
                color: {COLOR_WARN};
                background-color: #3B3020;
                border: 1px solid {COLOR_WARN};
                border-radius: 3px;
                padding: 3px 6px;
                font-size: {FW}px;
            }}
            QPlainTextEdit#exportPreview {{
                background-color: #292E3A;
                color: #D8DEE9;
                border: 1px solid #4C566A;
                border-radius: 3px;
                font-family: 'Roboto Mono', 'Consolas', monospace;
                font-size: {FP}px;
                padding: 4px;
            }}
            QPushButton#btnCopyPreview {{
                background-color: #3B4252;
                color: #81A1C1;
                border: 1px solid #4C566A;
                border-radius: 3px;
                padding: 2px 10px;
                font-size: {FS_SMALL}px;
                font-weight: normal;
            }}
            QPushButton#btnCopyPreview:hover {{
                background-color: #4C566A;
                color: #88C0D0;
            }}
        """)

    # ------------------------------------------------------------------
    # Sample management
    # ------------------------------------------------------------------

    def _switch_to_sample(self, index: int):
        if not (0 <= index < len(self._samples)):
            return
        try:
            self.model.compositionChanged.disconnect(self.refresh_ui)
        except RuntimeError:
            pass
        self.model = self._samples[index]
        self._current_sample_idx = index
        self.model.compositionChanged.connect(self.refresh_ui)
        self.sample_name_input.blockSignals(True)
        self.sample_name_input.setText(self._sample_names[index])
        self.sample_name_input.blockSignals(False)
        self.refresh_ui()

    def _on_sample_changed(self, index: int):
        if 0 <= index < len(self._samples):
            self._switch_to_sample(index)

    def _on_sample_name_changed(self, text: str):
        sanitized = self._sanitize_filename(text)
        if sanitized != text:
            self.sample_name_input.blockSignals(True)
            cursor_pos = self.sample_name_input.cursorPosition()
            self.sample_name_input.setText(sanitized)
            self.sample_name_input.setCursorPosition(min(cursor_pos, len(sanitized)))
            self.sample_name_input.blockSignals(False)
        if self._sample_names and 0 <= self._current_sample_idx < len(self._sample_names):
            self._sample_names[self._current_sample_idx] = sanitized
            if self.sample_selector_widget.isVisible():
                self.sample_selector.blockSignals(True)
                self.sample_selector.setItemText(self._current_sample_idx, sanitized)
                self.sample_selector.blockSignals(False)

    def _on_reset_click(self):
        idx = self._current_sample_idx
        if not (0 <= idx < len(self._initial_data)):
            return
        composition = BulkComposition()
        result = apply_to_model(self._initial_data[idx], composition)
        composition.emit_updated()
        self._samples[idx] = composition
        self._switch_to_sample(idx)

    # ------------------------------------------------------------------
    # About / manual
    # ------------------------------------------------------------------

    def _on_about_click(self):
        from .. import __version__
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("About ThermoChemX")
        msg_box.setIcon(QMessageBox.NoIcon)  # avoid native alert sound on Windows/macOS
        msg_box.setText(
            f"ThermoChemX v{__version__}\n"
            "Copyright (C) 2026  Michał Bukała\n"
            "This program is free software: GNU General Public License v3 or later.\n"
            "It comes with ABSOLUTELY NO WARRANTY. See LICENSE.txt for details."
        )
        open_btn = msg_box.addButton("Open Manual", QMessageBox.ActionRole)
        msg_box.addButton(QMessageBox.Close)
        msg_box.exec()
        if msg_box.clickedButton() == open_btn:
            self._open_manual()

    def _open_manual(self):
        from importlib.resources import files
        manual = files("thermochemx") / "assets" / "manual.pdf"
        try:
            manual_path = Path(str(manual))
            exists = manual_path.exists()
        except (TypeError, FileNotFoundError):
            exists = False
        if not exists:
            self._show_message(
                "Manual Not Found",
                f"Could not find the manual at:\n{manual}",
                QMessageBox.Warning,
            )
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(manual_path)))

    # ------------------------------------------------------------------
    # Import / Export handlers
    # ------------------------------------------------------------------

    def _on_import_click(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Import Composition",
            self.last_import_dir or "",
            "All supported (*.dat *.xlsx *.csv);;ThermoChemX snapshot (*.dat);;Excel (*.xlsx);;CSV (*.csv)"
        )
        if not path:
            return

        # .dat snapshot: synchronous, single-sample (first block)
        if Path(path).suffix.lower() == ".dat":
            self._import_dat(path)
            return

        self.btn_import.setEnabled(False)
        self.btn_import.setText("Importing…")
        self._pending_import_path = path
        self._import_thread = QThread()
        self._import_worker = ImportWorker(path)
        self._import_worker.moveToThread(self._import_thread)
        self._import_thread.started.connect(self._import_worker.run)
        self._import_worker.finished.connect(self._on_import_finished)
        self._import_worker.error.connect(self._on_import_error)
        self._import_worker.finished.connect(self._import_thread.quit)
        self._import_worker.error.connect(self._import_thread.quit)
        self._import_thread.finished.connect(self._import_worker.deleteLater)
        self._import_thread.finished.connect(self._import_thread.deleteLater)
        self._import_thread.start()

    def _import_dat(self, path: str) -> None:
        """Load the first snapshot block from a .dat file into the session."""
        from ..core.dat_importer import parse_dat_snapshots, apply_snapshot_to_model, DatImportError
        from ..core.importer import _decode_file, ENCODING_FALLBACK_WARNING, UNREADABLE_FILE_MESSAGE
        try:
            # Same UTF-8 → cp1252 fallback used for CSV imports.
            text, file_warnings = _decode_file(path)
            blocks = parse_dat_snapshots(text)
        except DatImportError as exc:
            self._show_message("Import Error", str(exc), QMessageBox.Critical)
            return
        except ValueError as exc:
            # Clean user-facing message from _decode_file (never a raw codec traceback).
            self._show_message("Import Error", str(exc), QMessageBox.Critical)
            return
        except Exception:
            # Unexpected — keep the user out of stack-trace territory.
            self._show_message("Import Error", UNREADABLE_FILE_MESSAGE,
                               QMessageBox.Critical)
            return

        if not blocks:
            self._show_message("Import Error",
                               "No composition snapshot block found in this .dat file.",
                               QMessageBox.Critical)
            return

        block = blocks[0]
        sample_name = self._sanitize_filename(
            str(block.data.get("in.sample_name", "")) or Path(path).stem
        )

        composition = BulkComposition()
        try:
            apply_snapshot_to_model(block, composition)
        except DatImportError as exc:
            self._show_message("Import Error", str(exc), QMessageBox.Critical)
            return
        composition.emit_updated()

        self.last_import_dir = str(Path(path).parent)
        self._samples = [composition]
        self._sample_names = [sample_name]
        self._initial_data = [dict(block.data)]
        self._switch_to_sample(0)
        self.sample_name_input.setText(sample_name)
        self.sample_selector_widget.setVisible(False)
        self.btn_export_all.setVisible(False)
        self.btn_reset.setEnabled(True)

        if len(blocks) > 1:
            self._show_message(
                "Multi-sample file",
                f"This file contains {len(blocks)} samples. "
                f"The first (\u2018{sample_name}\u2019) was imported. "
                "To load multiple samples at once, use Export All to produce "
                "individual files and re-import them separately.",
                QMessageBox.Information,
            )

        # Encoding-fallback notice — same phrasing as the CSV path.
        if file_warnings:
            self._show_message(
                "Import completed with warnings",
                "\n".join(file_warnings),
                QMessageBox.Warning,
            )

    def _on_import_error(self, message: str) -> None:
        self.btn_import.setEnabled(True)
        self.btn_import.setText("Import")
        self._show_message("Import Error", f"Could not read file:\n{message}", QMessageBox.Critical)

    def _on_import_finished(self, sample_list: list, file_warnings: list = None) -> None:
        # ``file_warnings`` is optional to keep older signal connections working
        # in isolation, but ImportWorker.finished now always emits both args.
        if file_warnings is None:
            file_warnings = []
        self.btn_import.setEnabled(True)
        self.btn_import.setText("Import")
        path = self._pending_import_path
        if not sample_list:
            self._show_message("Import Warning", "No samples found in file.", QMessageBox.Warning)
            return

        self.last_import_dir = str(Path(path).parent)
        self._samples = []
        self._sample_names = []
        self._initial_data = []
        all_messages: list[str] = []

        # File-level warnings (e.g. cp1252 encoding fallback) go first,
        # attributed to the file rather than any single sample.
        if file_warnings:
            file_label = f"[{Path(path).name}]"
            for w in file_warnings:
                all_messages.append(f"{file_label}\n  • {w}")

        for sample_data in sample_list:
            composition = BulkComposition()
            result = apply_to_model(sample_data.data, composition)
            composition.emit_updated()
            sanitized_name = self._sanitize_filename(sample_data.name)
            self._samples.append(composition)
            self._sample_names.append(sanitized_name)
            self._initial_data.append(dict(sample_data.data))
            if result.skipped or result.warnings:
                # One formatted block per sample: header line +
                # bulleted warnings + full unrecognized-keys list.
                block_lines = [f"[{sanitized_name}]"]
                for w in result.warnings:
                    block_lines.append(f"  • {w}")
                if result.skipped:
                    block_lines.append(
                        "  • Unrecognized keys: " + ", ".join(result.skipped)
                    )
                all_messages.append("\n".join(block_lines))

        if len(self._samples) == 1:
            self._switch_to_sample(0)
            self.sample_name_input.setText(self._sample_names[0])
            self.sample_selector_widget.setVisible(False)
            self.btn_export_all.setVisible(False)
            self.btn_reset.setEnabled(True)
        else:
            self.sample_selector.blockSignals(True)
            self.sample_selector.clear()
            for name in self._sample_names:
                self.sample_selector.addItem(name)
            self.sample_selector.setCurrentIndex(0)
            self.sample_selector.blockSignals(False)
            self._switch_to_sample(0)
            self.sample_selector_widget.setVisible(True)
            self.btn_export_all.setVisible(True)
            self.btn_reset.setEnabled(True)

        if all_messages:
            message_text = "\n\n".join(all_messages)
            # Match ~2× the natural height of the Export Settings dialog;
            # instantiated (not shown) purely to read its sizeHint.
            from .settings_dialog import SettingsDialog
            settings_h = SettingsDialog(self).sizeHint().height()
            self._show_resizable_text_dialog(
                "Import completed with warnings",
                message_text,
                initial_width=700,
                initial_height=2 * settings_h,
            )
        else:
            count = len(self._samples)
            self._show_message("Success", f"Imported {count} sample(s) successfully.",
                               QMessageBox.Information)

    def _on_export_click(self):
        sample_name = self._sanitize_filename(self.sample_name_input.text().strip())
        if not sample_name:
            self._show_message("Sample Name Required",
                               "Please enter a sample name before exporting.", QMessageBox.Warning)
            name, ok = QInputDialog.getText(self, "Sample Name", "Name:", text="sample")
            if not ok or not name.strip():
                return
            sample_name = self._sanitize_filename(name.strip())
            self.sample_name_input.setText(sample_name)

        if not self._export_targets:
            self._show_message(
                "No Export Target",
                "No export targets are selected.\n\nOpen Settings to choose targets.",
                QMessageBox.Warning,
            )
            return

        from ..core.targets.registry import get_adapter as _get_adp
        sorted_targets = sorted(self._export_targets)

        if len(sorted_targets) == 1:
            # Single target → familiar Save-As dialog
            target_name = sorted_targets[0]
            adapter = _get_adp(target_name)
            default_dir  = self.last_export_dir or self.last_import_dir or str(Path.cwd())
            default_path = str(Path(default_dir) / f"{sample_name}{adapter.default_suffix}")
            out_path, _  = QFileDialog.getSaveFileName(
                self, f"Export \u2014 {adapter.display_name}",
                default_path, adapter.file_dialog_filter,
            )
            if not out_path:
                return
            self.last_export_dir = str(Path(out_path).parent)
            results_map = self._do_export_current(
                [(target_name, out_path)], sample_name,
            )
        else:
            # Multiple targets → pick output directory
            default_dir = self.last_export_dir or self.last_import_dir or ""
            out_dir = QFileDialog.getExistingDirectory(
                self, "Select Output Directory", default_dir,
            )
            if not out_dir:
                return
            self.last_export_dir = out_dir
            results_map = self._do_export_current(
                [(t, out_dir) for t in sorted_targets], sample_name,
            )

        self._show_export_summary(results_map)

    def _on_export_all_click(self):
        if not self._samples:
            self._show_message("No Data", "No samples to export.", QMessageBox.Warning)
            return
        if not self._export_targets:
            self._show_message(
                "No Export Target",
                "No export targets are selected.\n\nOpen Settings to choose targets.",
                QMessageBox.Warning,
            )
            return

        default_dir = self.last_export_dir or self.last_import_dir or ""
        output_dir = QFileDialog.getExistingDirectory(
            self, "Select Output Directory", default_dir,
        )
        if not output_dir:
            return
        self.last_export_dir = output_dir

        from ..core.targets.registry import get_adapter as _get_adp
        sorted_targets = sorted(self._export_targets)

        all_warnings: list[str] = []
        written = 0
        for sname, comp in zip(self._sample_names, self._samples):
            try:
                result = build_recalc_result(comp, sample_name=sname)
            except Exception as exc:
                all_warnings.append(f"{sname}: recalc failed — {exc}")
                continue
            for target_name in sorted_targets:
                try:
                    adapter = _get_adp(target_name)
                    if self._case_styles.get(target_name) == "uppercase":
                        adapter.uppercase = True
                    er = adapter.export_to_file(
                        result, output_dir, sname,
                        template_path=self._template_paths.get(target_name),
                    )
                    written += 1
                    for w in er.warnings:
                        all_warnings.append(f"{sname}/{target_name}: {w}")
                except Exception as exc:
                    all_warnings.append(f"{sname}/{target_name}: {exc}")

        total = len(self._samples) * len(sorted_targets)
        if all_warnings:
            warn_text = "\n\u2022 ".join(all_warnings[:15])
            if len(all_warnings) > 15:
                warn_text += f"\n\u2026 and {len(all_warnings) - 15} more"
            self._show_message(
                "Export All \u2014 Completed with Warnings",
                f"Written {written}/{total} files to:\n{output_dir}\n\nWarnings:\n\u2022 {warn_text}",
                QMessageBox.Warning,
            )
        else:
            self._show_message(
                "Export All Completed",
                f"Exported {written} file(s) for {len(self._samples)} sample(s) to:\n{output_dir}",
                QMessageBox.Information,
            )

    # ------------------------------------------------------------------
    # Export helpers
    # ------------------------------------------------------------------

    def _do_export_current(
        self,
        target_output_pairs: "list[tuple[str, str]]",
        sample_name: str,
    ) -> "dict[str, object]":
        """Export the current sample to each (target_name, out_path) pair.

        Returns a dict mapping target_name → ExportResult (or Exception).
        """
        from ..core.targets.registry import get_adapter as _get_adp
        results: dict = {}
        try:
            result = build_recalc_result(self.model, sample_name=sample_name)
        except Exception as exc:
            for target_name, _ in target_output_pairs:
                results[target_name] = exc
            return results

        for target_name, out_path in target_output_pairs:
            try:
                adapter = _get_adp(target_name)
                if self._case_styles.get(target_name) == "uppercase":
                    adapter.uppercase = True
                results[target_name] = adapter.export_to_file(
                    result, out_path, sample_name,
                    template_path=self._template_paths.get(target_name),
                )
            except Exception as exc:
                results[target_name] = exc
        return results

    def _show_export_summary(self, results_map: dict) -> None:
        """Show success or warning dialog based on export results."""
        from ..core.exporter import ExportResult
        warnings_lines: list[str] = []
        filepaths: list[str] = []

        for target_name, res in results_map.items():
            if isinstance(res, Exception):
                warnings_lines.append(f"{target_name}: {res}")
            elif isinstance(res, ExportResult):
                filepaths.append(res.filepath)
                if res.companion_filepath:
                    filepaths.append(res.companion_filepath)
                for w in res.warnings:
                    warnings_lines.append(f"{target_name}: {w}")

        files_text = "\n".join(filepaths)
        if warnings_lines:
            warn_text = "\n\u2022 ".join(warnings_lines)
            self._show_message(
                "Export \u2014 Completed with Warnings",
                f"Files written:\n{files_text}\n\nWarnings:\n\u2022 {warn_text}",
                QMessageBox.Warning,
            )
        else:
            self._show_message(
                "Export Completed",
                f"Files written:\n{files_text}",
                QMessageBox.Information,
            )

    # ------------------------------------------------------------------
    # Result view (tab-driven element/oxide table + target totals)
    # ------------------------------------------------------------------

    def _on_result_view_changed(self, index: int) -> None:
        """Called when the user switches the result preview target."""
        from ..core.targets.registry import list_targets, get_adapter as _get_adp
        targets = list_targets()
        target_name = targets[index] if 0 <= index < len(targets) else targets[0]
        adapter = _get_adp(target_name)
        self._el_group.setTitle(adapter.group_title)
        self._refresh_result_view()

    def _refresh_result_view(self) -> None:
        """Rebuild the result table and update totals for the active preview target."""
        from ..core.targets.registry import list_targets, get_adapter as _get_adp
        target_name = (
            self._result_view_combo.currentData()
            or list_targets()[0]
        )

        sample_name = self._sanitize_filename(self.sample_name_input.text().strip()) or "unknown"
        try:
            result = build_recalc_result(self.model, sample_name=sample_name)
        except Exception:
            return

        adapter = _get_adp(target_name)
        rows              = adapter.rows(result)
        header0, header1  = adapter.table_headers()
        rendered_text, warnings = adapter.render(result)

        # Suppress denom-zero warnings before any data is loaded
        if result.denom <= 0.0:
            warnings = []

        # Warning banner — show only when there is something to report
        if warnings:
            self._result_warning_label.setText("\u26a0  " + "  |  ".join(warnings))
            self._result_warning_label.setVisible(True)
        else:
            self._result_warning_label.setVisible(False)

        # Table headers and rows
        self.el_table.setHorizontalHeaderLabels([header0, header1])
        dark_bg = QColor("#3B4252")
        for row, (label, value) in enumerate(rows[:16]):
            item_lbl = self.el_table.item(row, 0)
            if item_lbl is None:
                item_lbl = QTableWidgetItem()
                item_lbl.setFlags(Qt.ItemIsEnabled)
                item_lbl.setBackground(dark_bg)
                item_lbl.setForeground(QColor("#B8B8B8"))
                self.el_table.setItem(row, 0, item_lbl)
            item_lbl.setText(label)

            item_val = self.el_table.item(row, 1)
            if item_val is None:
                item_val = QTableWidgetItem()
                item_val.setFlags(Qt.ItemIsEnabled)
                item_val.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                item_val.setBackground(dark_bg)
                item_val.setForeground(QColor("#81A1C1"))
                self.el_table.setItem(row, 1, item_val)
            item_val.setText(f"{value:.5f}")

        # Perple_X basis mass
        basis_mass = self.model.model_mass_redox_corrected
        self.lbl_basis_mass.setText(f"{basis_mass:.2f}")
        self._apply_quality_color(self.lbl_basis_mass, basis_mass, 1000.0, 5.0, 20.0)

        # Export preview
        if result.denom <= 0.0:
            self._export_preview_text.clear()
        else:
            self._export_preview_text.setPlainText(
                self._extract_component_block(rendered_text)
            )

    # ------------------------------------------------------------------
    # Settings dialog
    # ------------------------------------------------------------------

    def _on_settings_click(self):
        """Open the session-only settings dialog."""
        from .settings_dialog import SettingsDialog
        dlg = SettingsDialog(
            self,
            export_targets=self._export_targets,
            template_paths=self._template_paths,
            case_styles=self._case_styles,
        )
        if dlg.exec():
            self._export_targets  = dlg.selected_targets()
            self._template_paths  = dlg.template_paths()
            self._case_styles     = dlg.case_styles()
            # Optionally sync preview combo to first checked target
            from ..core.targets.registry import list_targets
            targets = list_targets()
            for name in targets:
                if name in self._export_targets:
                    idx = targets.index(name)
                    self._result_view_combo.setCurrentIndex(idx)
                    break


# ---------------------------------------------------------------------------

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = ThermoChemXCalculator()
    window.show()
    sys.exit(app.exec())