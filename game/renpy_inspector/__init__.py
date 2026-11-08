"""Ren'Py Inspector. Module globals stay outside the rollback-aware game store."""

from .controller import Inspector

inspector = Inspector()


def install(store_provider, persistent_provider, restart_interaction):
    """Connect Ren'Py roots without exposing any mutable inspector state in saves."""
    inspector.bind(store_provider, persistent_provider)
    inspector._on_change = restart_interaction
