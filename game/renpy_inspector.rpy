# Ren'Py Inspector: drop-in read-only overlay for Ren'Py 8.x desktop.
# Do not use `default` or `define` for inspector state: it is not game state.
init -100 python:
    import renpy_inspector

    if "renpy_inspector_overlay" not in config.overlay_screens:
        config.overlay_screens.append("renpy_inspector_overlay")

    if renpy_inspector.inspector.reset not in config.after_load_callbacks:
        config.after_load_callbacks.append(renpy_inspector.inspector.reset)

    renpy_inspector.install(
        lambda: renpy.store,
        lambda: renpy.store.persistent,
        renpy.restart_interaction,
    )
