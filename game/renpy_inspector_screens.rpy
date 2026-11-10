# The only native Ren'Py integration is an invisible F8 hotkey and timer.
# No drawer, tab, button, style or other in-game inspector UI is rendered.
screen renpy_inspector_overlay():
    key "K_F8" action Function(renpy_inspector_open_external)

    # Inspect game objects only on Ren'Py's interaction thread.
    # The background HTTP server serves immutable cached JSON.
    if renpy_inspector.bridge.running:
        timer 1.5 repeat True action Function(renpy_inspector.bridge.publish, _update_screens=False)
