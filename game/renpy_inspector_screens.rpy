# The only native Ren'Py integration is an invisible F8 hotkey and timer.
# No drawer, tab, button, style or other in-game inspector UI is rendered.
screen renpy_inspector_overlay():
    key "K_F8" action Function(renpy_inspector_open_external)

    # Process bounded browser page requests on the Ren'Py interaction thread.
    # HTTP threads queue data-only requests and never read gameplay objects.
    if renpy_inspector.bridge.running:
        timer 0.25 repeat True action Function(renpy_inspector.bridge.tick, _update_screens=False)
