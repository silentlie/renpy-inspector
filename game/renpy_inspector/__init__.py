"""Ren'Py Inspector. Mutable state stays outside rollback-aware game stores."""

from .controller import Inspector
from .settings import SettingsStore
from .runtime import collect_context
from .bridge import InspectorBridge

inspector = Inspector()
# The external service remains dormant until the first F8 press.
bridge = InspectorBridge(inspector)


def install(store_provider, persistent_provider, restart_interaction, savedir=None, context_provider=None):
    """Bind roots, UI callback and optional per-game inspector-only JSON config."""
    settings = SettingsStore(savedir) if savedir else None
    inspector.bind(store_provider, persistent_provider, settings=settings,
                   context_provider=context_provider)
    inspector._on_change = restart_interaction
    bridge.configure_favourites_directory(savedir)


def reset_lifecycle():
    """Invalidate read-only caches after load or default-state restoration.

    Ren'Py runs after_default_callbacks following rollback as well as during
    startup/load. These callbacks never change gameplay variables or saves.
    """
    inspector.reset()
    bridge.invalidate()


def observe_legacy_rollback(renpy_api):
    """Conservative, read-only fallback for older Ren'Py builds.

    The modern after-default callback handles rollback directly. Ren'Py 7.4
    may not expose it, so consult in_rollback() on new interactions instead.
    Repeated invalidations in rollback replay are safe; missing APIs are not
    guessed or silently replaced by gameplay writes.
    """
    try:
        rolling = renpy_api.in_rollback()
    except Exception:
        return
    if rolling:
        reset_lifecycle()


def register_named_store(name, provider):
    """Configure a read-only root, for example from a Ren'Py init python block."""
    inspector.register_named_store(name, provider)
