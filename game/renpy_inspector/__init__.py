"""Ren'Py Inspector. Mutable state stays outside rollback-aware game stores."""

from .controller import Inspector
from .settings import SettingsStore

inspector = Inspector()


def install(store_provider, persistent_provider, restart_interaction, savedir=None):
    """Bind roots, UI callback and optional per-game inspector-only JSON config."""
    settings = SettingsStore(savedir) if savedir else None
    inspector.bind(store_provider, persistent_provider, settings=settings)
    inspector._on_change = restart_interaction
