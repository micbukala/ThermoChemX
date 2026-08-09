# ThermoChemX — Copyright (C) 2026  Michał Bukała <michal.bukala@csic.es>
# This program is free software: GNU General Public License v3 or later.
# It comes with ABSOLUTELY NO WARRANTY. See LICENSE.txt for details.

"""
Target adapter registry.

Maps target names (lowercase strings) to adapter instances.
Use get_adapter(name) to retrieve a fresh adapter by name.
"""
from __future__ import annotations

from .perplex_element import PerplexElementAdapter
from .perplex_oxide import PerplexOxideAdapter

__all__ = ["get_adapter", "list_targets"]

_REGISTRY: dict[str, type] = {
    "perplex_element": PerplexElementAdapter,
    "perplex_oxide":   PerplexOxideAdapter,
}


def get_adapter(name: str):
    """
    Return a new instance of the named adapter.

    Args:
        name: Target name (case-insensitive), e.g. "theriak".

    Raises:
        KeyError: If *name* is not registered.
    """
    cls = _REGISTRY.get(name.lower())
    if cls is None:
        raise KeyError(
            f"Unknown export target: {name!r}. "
            f"Available targets: {list(_REGISTRY)}"
        )
    return cls()


def list_targets() -> list[str]:
    """Return sorted list of registered target names."""
    return sorted(_REGISTRY)
