# Copyright (C) 2026 Michał Bukała <michal.bukala@csic.es>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.

"""Entry point for ThermoChemX — launches the GUI."""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from .ui.main_window import ThermoChemXCalculator


def main() -> int:
    """Launch the ThermoChemX GUI. Returns the Qt event-loop exit code."""
    app = QApplication.instance() or QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setApplicationName("ThermoChemX")
    app.setApplicationVersion("1.0.0")

    window = ThermoChemXCalculator()
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())