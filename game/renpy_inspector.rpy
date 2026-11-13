# Ren'Py Inspector: read-only by default; F8-only browser hotkey.
# Trusted game init code can opt in to Store primitive editing separately.
# Python package state is separate from Ren'Py's rollback-aware gameplay stores.
init -100 python:
    import renpy_inspector

    # Resolve the external UI from the real game directory, not __file__.
    # On some Ren'Py loaders the package import path is not a disk folder.
    renpy_inspector.bridge.configure_game_directory(config.gamedir)
    renpy_inspector.bridge.configure_script_runtime(renpy, config.gamedir)

    if "renpy_inspector_overlay" not in config.overlay_screens:
        config.overlay_screens.append("renpy_inspector_overlay")

    # after_load covers explicit save loads. after_default also runs after
    # rollback (and at startup); invalidate before the next browser capture.
    # Separate wrappers preserve callback provenance, not a guessed cause.
    # No gameplay values are written.
    if renpy_inspector.after_load_lifecycle not in config.after_load_callbacks:
        config.after_load_callbacks.append(renpy_inspector.after_load_lifecycle)
    # Ren'Py 7.4's config proxy throws Exception (not AttributeError)
    # for unknown config names; avoid an unsafe getattr(..., default).
    try:
        defaults_callbacks = config.after_default_callbacks
    except Exception:
        defaults_callbacks = None
    if defaults_callbacks is not None:
        if renpy_inspector.after_default_lifecycle not in defaults_callbacks:
            defaults_callbacks.append(renpy_inspector.after_default_lifecycle)
    else:
        # Older engines lack after_default_callbacks. At the next interaction
        # check their public in_rollback() flag, if exposed. The legacy
        # fallback may invalidate more than once during rollback replay.
        def renpy_inspector_legacy_rollback_check():
            renpy_inspector.observe_legacy_rollback(renpy)
        if renpy_inspector_legacy_rollback_check not in config.start_interact_callbacks:
            config.start_interact_callbacks.append(renpy_inspector_legacy_rollback_check)

    renpy_inspector.install(
        lambda: renpy.store,
        lambda: renpy.store.persistent,
        renpy.restart_interaction,
        getattr(config, "savedir", None),
        lambda: renpy_inspector.collect_context(renpy, config),
    )

# F8 starts the browser service on first press and opens it on every press.
# A transient diagnostic is shown only if setup fails, never a native drawer.
init -99 python:
    def renpy_inspector_open_external():
        if not renpy_inspector.bridge.launch_or_open():
            message = renpy_inspector.bridge.error or "Could not open the local browser."
            try:
                renpy.notify("Ren'Py Inspector: " + message)
            except Exception:
                pass
