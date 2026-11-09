"""Ren'Py Inspector. Mutable state stays outside rollback-aware game stores."""

from .controller import Inspector
from .settings import SettingsStore
from .runtime import collect_context

inspector = Inspector()


def install(store_provider, persistent_provider, restart_interaction, savedir=None, context_provider=None):
    """Bind roots, UI callback and optional per-game inspector-only JSON config."""
    settings = SettingsStore(savedir) if savedir else None
    inspector.bind(store_provider, persistent_provider, settings=settings,
                   context_provider=context_provider)
    inspector._on_change = restart_interaction


def register_named_store(name, provider):
    """Configure a read-only root, for example from a Ren'Py init python block."""
    inspector.register_named_store(name, provider)
