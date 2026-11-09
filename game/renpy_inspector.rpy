# Ren'Py Inspector: drop-in read-only overlay for Ren'Py 8.x desktop.
# Python package state is separate from Ren'Py's rollback-aware gameplay stores.
init -100 python:
    import renpy_inspector

    # Resolve the external UI from the real game directory, not __file__.
    # On some Ren'Py loaders the package import path is not a disk folder.
    renpy_inspector.bridge.configure_game_directory(config.gamedir)

    if "renpy_inspector_overlay" not in config.overlay_screens:
        config.overlay_screens.append("renpy_inspector_overlay")

    if renpy_inspector.inspector.reset not in config.after_load_callbacks:
        config.after_load_callbacks.append(renpy_inspector.inspector.reset)

    if renpy_inspector.bridge.invalidate not in config.after_load_callbacks:
        config.after_load_callbacks.append(renpy_inspector.bridge.invalidate)

    renpy_inspector.install(
        lambda: renpy.store,
        lambda: renpy.store.persistent,
        renpy.restart_interaction,
        getattr(config, "savedir", None),
        lambda: renpy_inspector.collect_context(renpy, config),
    )
