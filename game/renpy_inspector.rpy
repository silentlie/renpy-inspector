# Ren'Py Inspector: drop-in read-only overlay for Ren'Py 7/8 desktop.
# Python package state is separate from Ren'Py's rollback-aware gameplay stores.
init -100 python:
    import renpy_inspector

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
