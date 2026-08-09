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

"""Launcher for ThermoChemX.

Makes ``src/`` importable so the application runs directly from a source
checkout, with no installation step. Equivalent to ``python -m thermochemx``
after ``pip install -e .``.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from thermochemx.__main__ import main  # noqa: E402  (import follows sys.path setup)

if __name__ == "__main__":
    sys.exit(main())