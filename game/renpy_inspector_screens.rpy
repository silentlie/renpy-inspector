# A single overlay screen and a single timer, active only while open.
# The UI only renders cached Rows, never introspects game objects.
screen renpy_inspector_overlay():
    zorder 200

    key "K_F8" action Function(renpy_inspector.inspector.toggle_open)

    if renpy_inspector.inspector.is_open:
        use renpy_inspector_drawer
    else:
        textbutton "Inspect" style "renpy_inspector_tab_button":
            xalign 1.0
            yalign 0.45
            action Function(renpy_inspector.inspector.open)

screen renpy_inspector_drawer():
    # UI is read-only; this screen intentionally doesn't capture other gameplay input.
    $ inspector = renpy_inspector.inspector

    if inspector.interval_ms > 0:
        timer (inspector.interval_ms / 1000.0) repeat True action Function(inspector.tick, _update_screens=False)

    frame:
        style "renpy_inspector_drawer"
        xalign 1.0
        yalign 0.0
        xsize min(460, int(config.screen_width * 0.9))
        yfill True

        vbox:
            spacing 10

            hbox:
                xfill True
                text "Ren'Py Inspector" style "renpy_inspector_title"
                null width 10
                textbutton "×" action Function(inspector.close)

            hbox:
                spacing 8
                textbutton "Store" action Function(inspector.set_scope, "store") selected inspector.scope == "store"
                textbutton "Persistent" action Function(inspector.set_scope, "persistent") selected inspector.scope == "persistent"
                textbutton "Refresh" action Function(inspector.refresh)

            text "Read-only  |  F8 to toggle" style "renpy_inspector_hint"

            if inspector.rows:
                vpgrid:
                    cols 1
                    xfill True
                    yfill True
                    mousewheel True
                    draggable True
                    scrollbars "vertical"
                    spacing 2

                    for row in inspector.rows:
                        hbox:
                            xysize (400, 30)
                            spacing 6
                            null width min(row.depth * 16, 150)
                            if row.expandable:
                                textbutton ("▾" if row.expanded else "▸"):
                                    style "renpy_inspector_row_button"
                                    action Function(inspector.toggle_node, row.path)
                            else:
                                null width 26
                            textbutton row.label:
                                style "renpy_inspector_row_button"
                                xmaximum 150
                                action (Function(inspector.toggle_node, row.path) if row.expandable else NullAction())
                            text row.type_name style "renpy_inspector_type"
                            text row.preview style "renpy_inspector_value" xmaximum 145
            else:
                text "No values to display" style "renpy_inspector_hint"

            hbox:
                spacing 5
                text "Poll:" style "renpy_inspector_hint"
                for ms in (0, 100, 250, 500, 1000):
                    textbutton ("Manual" if ms == 0 else "{}ms".format(ms)):
                        style "renpy_inspector_interval_button"
                        selected inspector.interval_ms == ms
                        action Function(inspector.set_interval, ms)
