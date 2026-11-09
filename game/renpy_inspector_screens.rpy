# All inspection and navigation work runs in action/controller calls, not screen evaluation.
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
            spacing 8

            hbox:
                xfill True
                text "Ren'Py Inspector" style "renpy_inspector_title"
                null width 8
                textbutton "×" action Function(inspector.close)

            hbox:
                spacing 4
                textbutton "Overview" action Function(inspector.set_panel, "overview") selected inspector.panel == "overview"
                textbutton "Variables" action Function(inspector.set_panel, "variables") selected inspector.panel == "variables"
                textbutton "Scripts" action Function(inspector.set_panel, "scripts") selected inspector.panel == "scripts"
                textbutton "Settings" action Function(inspector.set_panel, "settings") selected inspector.panel == "settings"

            if inspector.panel == "variables":
                hbox:
                    spacing 4
                    textbutton "Store" action Function(inspector.set_scope, "store") selected inspector.scope == "store"
                    textbutton "Persistent" action Function(inspector.set_scope, "persistent") selected inspector.scope == "persistent"
                    textbutton "Favourites" action Function(inspector.set_scope, "favorites") selected inspector.scope == "favorites"
                    if inspector.named_scope_options:
                        textbutton "Named" action Function(inspector.show_named) selected inspector.scope.startswith("named:")
                    textbutton "↻" action Function(inspector.refresh)

                if inspector.scope.startswith("named:"):
                    hbox:
                        spacing 4
                        for named_scope in inspector.named_scope_options:
                            textbutton named_scope[6:]:
                                action Function(inspector.set_scope, named_scope)
                                selected inspector.scope == named_scope

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
                                    xysize (row_width, 38)
                                    spacing 6
                                    textbutton "★":
                                        style "renpy_inspector_row_button"
                                        action Function(inspector.toggle_favorite, favorite.location[0], favorite.location[1])
                                    vbox:
                                        spacing 0
                                        text favorite.label style "renpy_inspector_row_button_text" size 12 xmaximum (row_width - 62)
                                        text favorite.preview style "renpy_inspector_value" size 12 xmaximum (row_width - 62)
                    else:
                        text "No favourites. Pin variables with ☆ in a tree." style "renpy_inspector_hint"
                else:
                    hbox:
                        spacing 4
                        input:
                            value FieldInputValue(inspector, "search_query")
                            length 80
                            pixel_width max(120, row_width - 105)
                        textbutton "Find":
                            action Function(inspector.run_search)
                        if inspector.applied_search:
                            textbutton "Clear":
                                action Function(inspector.clear_search)
                    if inspector.applied_search:
                        text ("{} result(s), {} values scanned".format(len(inspector.search_matches), inspector.search_visited)) style "renpy_inspector_hint"
                        if inspector.search_truncated:
                            text "Limited results. Narrow your search." style "renpy_inspector_hint"
                        if inspector.search_errors:
                            text "Some branches could not be inspected." style "renpy_inspector_hint"
                        if inspector.search_matches:
                            vpgrid:
                                cols 1
                                xfill True
                                yfill True
                                mousewheel True
                                draggable True
                                scrollbars "vertical"
                                spacing 2
                                for match in inspector.search_matches:
                                    hbox:
                                        xysize (row_width, 40)
                                        spacing 6
                                        textbutton match.label:
                                            style "renpy_inspector_row_button"
                                            xmaximum (row_width - 110)
                                            action Function(inspector.reveal_search, match.scope, match.path)
                                        text match.preview style "renpy_inspector_value" xmaximum 95
                        else:
                            text "No matches in the bounded search." style "renpy_inspector_hint"
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
                                    spacing 4
                                    null width min(row.depth * 14, 120)
                                    if row.expandable:
                                        textbutton ("▾" if row.expanded else "▸"):
                                            style "renpy_inspector_row_button"
                                            action Function(inspector.toggle_node, row.path)
                                    else:
                                        null width 24
                                    textbutton row.label:
                                        style "renpy_inspector_row_button"
                                        xmaximum 110
                                        action (Function(inspector.toggle_node, row.path) if row.expandable else NullAction())
                                    text row.type_name style "renpy_inspector_type"
                                    text row.preview style "renpy_inspector_value" xmaximum 95
                                    if row.pinnable and row.state not in ("error", "info"):
                                        textbutton ("★" if row.favorite else "☆"):
                                            style "renpy_inspector_row_button"
                                            action Function(inspector.toggle_favorite, inspector.scope, row.path)
                    else:
                        text "No values to display" style "renpy_inspector_hint"

            elif inspector.panel == "overview":
                text "Game & watcher overview" style "renpy_inspector_hint"
                for field, value in inspector.overview_rows:
                    hbox:
                        spacing 8
                        text field style "renpy_inspector_type" xsize 125
                        text value style "renpy_inspector_value" xmaximum (row_width - 140)
                null height 20
                textbutton "Refresh" action Function(inspector.refresh)

            elif inspector.panel == "scripts":
                text "Current script context (read-only)" style "renpy_inspector_hint"
                for field, value in inspector.script_rows:
                    hbox:
                        spacing 8
                        text field style "renpy_inspector_type" xsize 125
                        text value style "renpy_inspector_value" xmaximum (row_width - 140)
                text "Return destinations are not the current label or debugger stack." style "renpy_inspector_hint"
                textbutton "Refresh" action Function(inspector.refresh)

            else:
                text "Inspector preferences (not saved in game state)" style "renpy_inspector_hint"

            if inspector.panel == "settings":
                hbox:
                    spacing 4
                    text "Width" style "renpy_inspector_hint"
                    textbutton "−" action Function(inspector.adjust_width, -40)
                    text "[inspector.drawer_width]" style "renpy_inspector_hint"
                    textbutton "+" action Function(inspector.adjust_width, 40)

            if inspector.settings_error:
                text inspector.settings_error style "renpy_inspector_hint"

            hbox:
                spacing 4
                text "Poll:" style "renpy_inspector_hint"
                for ms in (0, 100, 250, 500, 1000):
                    textbutton ("Manual" if ms == 0 else "{}ms".format(ms)):
                        style "renpy_inspector_interval_button"
                        selected inspector.interval_ms == ms
                        action Function(inspector.set_interval, ms)
