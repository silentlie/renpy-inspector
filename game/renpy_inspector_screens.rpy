# One overlay, one active timer. The UI renders cached snapshots, never raw game data.
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
    $ inspector = renpy_inspector.inspector
    $ drawer_width = min(inspector.drawer_width, int(config.screen_width * 0.9))
    $ row_width = max(250, drawer_width - 42)

    if inspector.interval_ms > 0:
        timer (inspector.interval_ms / 1000.0) repeat True action Function(inspector.tick, _update_screens=False)

    frame:
        style "renpy_inspector_drawer"
        xalign 1.0
        yalign 0.0
        xsize drawer_width
        yfill True

        vbox:
            spacing 9

            hbox:
                xfill True
                text "Ren'Py Inspector" style "renpy_inspector_title"
                null width 10
                textbutton "×" action Function(inspector.close)

            hbox:
                spacing 6
                textbutton "Store" action Function(inspector.set_scope, "store") selected inspector.scope == "store"
                textbutton "Persistent" action Function(inspector.set_scope, "persistent") selected inspector.scope == "persistent"
                textbutton "Favourites" action Function(inspector.set_scope, "favorites") selected inspector.scope == "favorites"
                textbutton "↻" action Function(inspector.refresh)

            text "Read-only | F8 to toggle | ☆ pin values" style "renpy_inspector_hint"

            if inspector.scope == "favorites":
                if inspector.favorite_rows:
                    vpgrid:
                        cols 1
                        xfill True
                        yfill True
                        mousewheel True
                        draggable True
                        scrollbars "vertical"
                        spacing 2

                        for favorite in inspector.favorite_rows:
                            hbox:
                                xysize (row_width, 34)
                                spacing 6
                                textbutton "★":
                                    style "renpy_inspector_row_button"
                                    action Function(inspector.toggle_favorite, favorite.location[0], favorite.location[1])
                                vbox:
                                    spacing 0
                                    text favorite.label style "renpy_inspector_row_button_text" size 12 xmaximum (row_width - 62)
                                    text favorite.preview style "renpy_inspector_value" size 12 xmaximum (row_width - 62)
                else:
                    text "No favourites. Pin variables with ☆ on Store or Persistent." style "renpy_inspector_hint"
            elif inspector.rows:
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
                            xysize (row_width, 30)
                            spacing 5
                            null width min(row.depth * 14, 120)
                            if row.expandable:
                                textbutton ("▾" if row.expanded else "▸"):
                                    style "renpy_inspector_row_button"
                                    action Function(inspector.toggle_node, row.path)
                            else:
                                null width 24
                            textbutton row.label:
                                style "renpy_inspector_row_button"
                                xmaximum 128
                                action (Function(inspector.toggle_node, row.path) if row.expandable else NullAction())
                            text row.type_name style "renpy_inspector_type"
                            text row.preview style "renpy_inspector_value" xmaximum 115
                            if row.pinnable and row.state not in ("error", "info"):
                                textbutton ("★" if row.favorite else "☆"):
                                    style "renpy_inspector_row_button"
                                    action Function(inspector.toggle_favorite, inspector.scope, row.path)
            else:
                text "No values to display" style "renpy_inspector_hint"

            if inspector.settings_error:
                text inspector.settings_error style "renpy_inspector_hint"

            hbox:
                spacing 4
                text "Width" style "renpy_inspector_hint"
                textbutton "−" action Function(inspector.adjust_width, -40)
                text "[inspector.drawer_width]" style "renpy_inspector_hint"
                textbutton "+" action Function(inspector.adjust_width, 40)

            hbox:
                spacing 5
                text "Poll:" style "renpy_inspector_hint"
                for ms in (0, 100, 250, 500, 1000):
                    textbutton ("Manual" if ms == 0 else "{}ms".format(ms)):
                        style "renpy_inspector_interval_button"
                        selected inspector.interval_ms == ms
                        action Function(inspector.set_interval, ms)
