# Native Ren'Py Inspector UI kit. Every button has an inspector-specific style.
# Vpgrid children have fixed dimensions; the footer is outside every viewport.
screen renpy_inspector_overlay():
    zorder 200

    key "K_F8" action Function(renpy_inspector.inspector.toggle_open)

    if renpy_inspector.inspector.is_open:
        use renpy_inspector_drawer
    else:
        textbutton "Inspect":
            style "renpy_inspector_tab_button"
            xalign 1.0
            yalign 0.45
            action Function(renpy_inspector.inspector.open)


screen renpy_inspector_drawer():
    $ inspector = renpy_inspector.inspector
    $ drawer_width = min(inspector.drawer_width, int(config.screen_width * 0.94))
    $ inner_width = max(200, drawer_width - 24)
    $ row_width = max(180, inner_width - 18)
    $ compact = config.screen_height < 650
    $ title_h = 34 if compact else 40
    $ nav_h = 32 if compact else 36
    $ footer_h = 34 if compact else 38
    $ variables = inspector.panel == "variables"
    $ scope_h = 30 if variables else 0
    $ named_h = 28 if variables and inspector.scope.startswith("named:") else 0
    $ search_h = 38 if variables and inspector.scope != "favorites" else 0
    $ status_h = 20 if search_h and inspector.applied_search else 0
    $ section_count = 4 + int(bool(scope_h)) + int(bool(named_h)) + int(bool(search_h)) + int(bool(status_h))
    $ list_height = max(65, int(config.screen_height) - 20 - title_h - nav_h - footer_h - scope_h - named_h - search_h - status_h - 4 * (section_count - 1))

    if inspector.interval_ms > 0:
        timer (inspector.interval_ms / 1000.0) repeat True action Function(inspector.tick, _update_screens=False)

    frame:
        style "renpy_inspector_drawer"
        xalign 1.0
        yalign 0.0
        xsize drawer_width
        ysize config.screen_height

        vbox:
            xfill True
            spacing 4

            hbox:
                xfill True
                ysize title_h
                spacing 4
                text "Ren'Py Inspector":
                    style "renpy_inspector_title"
                    xmaximum (inner_width - 40)
                    yalign 0.5
                null width 1
                textbutton "×":
                    style "renpy_inspector_close_button"
                    yalign 0.5
                    action Function(inspector.close)

            hbox:
                xfill True
                ysize nav_h
                spacing 3
                textbutton "Overview":
                    style "renpy_inspector_nav_button"
                    selected inspector.panel == "overview"
                    action Function(inspector.set_panel, "overview")
                textbutton "Variables":
                    style "renpy_inspector_nav_button"
                    selected inspector.panel == "variables"
                    action Function(inspector.set_panel, "variables")
                textbutton "Scripts":
                    style "renpy_inspector_nav_button"
                    selected inspector.panel == "scripts"
                    action Function(inspector.set_panel, "scripts")
                textbutton "Settings":
                    style "renpy_inspector_nav_button"
                    selected inspector.panel == "settings"
                    action Function(inspector.set_panel, "settings")

            if variables:
                hbox:
                    xfill True
                    ysize scope_h
                    spacing 3
                    textbutton "Store":
                        style "renpy_inspector_scope_button"
                        selected inspector.scope == "store"
                        action Function(inspector.set_scope, "store")
                    textbutton "Persistent":
                        style "renpy_inspector_scope_button"
                        selected inspector.scope == "persistent"
                        action Function(inspector.set_scope, "persistent")
                    textbutton "Favourites":
                        style "renpy_inspector_scope_button"
                        selected inspector.scope == "favorites"
                        action Function(inspector.set_scope, "favorites")
                    if inspector.named_scope_options:
                        textbutton "Named":
                            style "renpy_inspector_scope_button"
                            selected inspector.scope.startswith("named:")
                            action Function(inspector.show_named)
                    textbutton "↻":
                        style "renpy_inspector_icon_button"
                        action Function(inspector.refresh)

                if named_h:
                    viewport:
                        xfill True
                        ysize named_h
                        draggable True
                        mousewheel "horizontal"
                        hbox:
                            spacing 3
                            for named_scope in inspector.named_scope_options:
                                textbutton named_scope[6:]:
                                    style "renpy_inspector_scope_button"
                                    selected inspector.scope == named_scope
                                    action Function(inspector.set_scope, named_scope)

                if search_h:
                    hbox:
                        xfill True
                        ysize search_h
                        spacing 4
                        frame:
                            style "renpy_inspector_search_field"
                            xsize max(100, inner_width - (116 if inspector.applied_search else 64))
                            ysize 31
                            input:
                                style "renpy_inspector_search_input"
                                value FieldInputValue(inspector, "search_query")
                                length 80
                                pixel_width max(90, inner_width - (130 if inspector.applied_search else 78))
                        textbutton "Find":
                            style "renpy_inspector_action_button"
                            action Function(inspector.run_search)
                        if inspector.applied_search:
                            textbutton "Clear":
                                style "renpy_inspector_action_button"
                                action Function(inspector.clear_search)

                if status_h:
                    text ("{} results · {} scanned{}".format(len(inspector.search_matches), inspector.search_visited, " · Limited" if inspector.search_truncated else "")):
                        style "renpy_inspector_hint"
                        ysize status_h

            frame:
                style "renpy_inspector_body"
                xfill True
                ysize list_height

                if variables and inspector.scope == "favorites":
                    if inspector.favorite_rows:
                        vpgrid:
                            cols 1
                            xfill True
                            ysize list_height
                            spacing 3
                            mousewheel True
                            draggable True
                            scrollbars "vertical"
                            for favorite in inspector.favorite_rows:
                                use renpy_inspector_favorite_row(inspector, favorite, row_width)
                    else:
                        text "No favourites yet. Use ☆ beside a variable to watch it.":
                            style "renpy_inspector_hint"
                            xmaximum row_width

                elif variables and inspector.applied_search:
                    if inspector.search_matches:
                        vpgrid:
                            cols 1
                            xfill True
                            ysize list_height
                            spacing 3
                            mousewheel True
                            draggable True
                            scrollbars "vertical"
                            for match in inspector.search_matches:
                                use renpy_inspector_match_row(inspector, match, row_width)
                    else:
                        text "No matches in the bounded search.":
                            style "renpy_inspector_hint"
                            xmaximum row_width

                elif variables:
                    if inspector.rows:
                        vpgrid:
                            cols 1
                            xfill True
                            ysize list_height
                            spacing 1
                            mousewheel True
                            draggable True
                            scrollbars "vertical"
                            for row in inspector.rows:
                                use renpy_inspector_tree_row(inspector, row, row_width)
                    else:
                        text "No values to display." style "renpy_inspector_hint"

                elif inspector.panel == "overview":
                    viewport:
                        xfill True
                        ysize list_height
                        draggable True
                        mousewheel True
                        vbox:
                            spacing 5
                            text "Game & watcher overview" style "renpy_inspector_section_title"
                            for field, value in inspector.overview_rows:
                                use renpy_inspector_detail_row(field, value, row_width)

                elif inspector.panel == "scripts":
                    viewport:
                        xfill True
                        ysize list_height
                        draggable True
                        mousewheel True
                        vbox:
                            spacing 5
                            text "Current script context" style "renpy_inspector_section_title"
                            for field, value in inspector.script_rows:
                                use renpy_inspector_detail_row(field, value, row_width)
                            text "Return labels are destinations, not a debugger stack.":
                                style "renpy_inspector_hint"
                                xmaximum row_width

                else:
                    viewport:
                        xfill True
                        ysize list_height
                        draggable True
                        mousewheel True
                        vbox:
                            spacing 10
                            text "Appearance" style "renpy_inspector_section_title"
                            hbox:
                                spacing 10
                                text "Drawer width" style "renpy_inspector_hint"
                                textbutton "−":
                                    style "renpy_inspector_action_button"
                                    action Function(inspector.adjust_width, -40)
                                text "{} px".format(inspector.drawer_width) style "renpy_inspector_value"
                                textbutton "+":
                                    style "renpy_inspector_action_button"
                                    action Function(inspector.adjust_width, 40)

                            null height 12
                            text "Polling interval" style "renpy_inspector_section_title"
                            text "Automatic refresh runs only while the drawer is open.":
                                style "renpy_inspector_hint"
                                xmaximum row_width
                            hbox:
                                spacing 4
                                for ms in (0, 100, 250, 500, 1000):
                                    textbutton ("Off" if ms == 0 else "{}".format(ms)):
                                        style "renpy_inspector_interval_button"
                                        selected inspector.interval_ms == ms
                                        action Function(inspector.set_interval, ms)
                            text ("Current interval: {}".format("Manual" if inspector.interval_ms == 0 else "{} ms".format(inspector.interval_ms))):
                                style "renpy_inspector_hint"
                            text "Off disables automatic polling. Use Refresh for manual updates.":
                                style "renpy_inspector_hint"
                                xmaximum row_width
                            null height 12
                            text "Data & privacy" style "renpy_inspector_section_title"
                            text "Inspector preferences are separate from gameplay saves.":
                                style "renpy_inspector_hint"
                                xmaximum row_width
                            if inspector.settings_error:
                                text inspector.settings_error:
                                    style "renpy_inspector_hint"
                                    xmaximum row_width

            # Fixed-height footer is deliberately not inside the scrollable grid.
            use renpy_inspector_footer(inspector, footer_h, inner_width)


screen renpy_inspector_tree_row(inspector, row, row_width):
    $ guide_count = min(row.depth, 7)
    $ content_width = max(100, row_width - guide_count * 12 - 62)

    frame:
        style "renpy_inspector_tree_row"
        xysize (row_width, 42)
        hbox:
            spacing 3
            for level in range(guide_count):
                fixed:
                    xysize (12, 38)
                    add Solid("#2c4865") xpos 6 xsize 1 ysize 38
            if row.state == "more":
                null width 6
                textbutton ("+  " + row.label):
                    style "renpy_inspector_load_more_button"
                    xmaximum (content_width + 25)
                    action Function(inspector.load_more_node, row.path[:-1])
            elif row.state == "info":
                null width 22
                vbox:
                    spacing 0
                    text row.label style "renpy_inspector_hint" xmaximum content_width
                    text row.preview style "renpy_inspector_value" xmaximum content_width
            else:
                if row.expandable:
                    textbutton ("▾" if row.expanded else "▸"):
                        style "renpy_inspector_icon_button"
                        action Function(inspector.toggle_node, row.path)
                else:
                    text "·":
                        style "renpy_inspector_tree_leaf"
                        xsize 20
                vbox:
                    xsize content_width
                    spacing 0
                    if row.expandable:
                        textbutton row.label:
                            style "renpy_inspector_tree_name_button"
                            xmaximum content_width
                            ymaximum 20
                            action Function(inspector.toggle_node, row.path)
                    else:
                        text row.label:
                            style "renpy_inspector_tree_name"
                            xmaximum content_width
                            ymaximum 20
                    text ("{}  ·  {}".format(row.type_name, row.preview)):
                        style "renpy_inspector_value"
                        xmaximum content_width
                        ymaximum 18
                if row.pinnable and row.state not in ("error", "info"):
                    textbutton ("★" if row.favorite else "☆"):
                        style "renpy_inspector_icon_button"
                        action Function(inspector.toggle_favorite, inspector.scope, row.path)
                else:
                    null width 21


screen renpy_inspector_match_row(inspector, match, row_width):
    frame:
        style "renpy_inspector_tree_row"
        xysize (row_width, 48)
        vbox:
            spacing 1
            textbutton match.label:
                style "renpy_inspector_tree_name_button"
                xmaximum (row_width - 16)
                ymaximum 21
                action Function(inspector.reveal_search, match.scope, match.path)
            text ("{}  ·  {}".format(match.type_name, match.preview)):
                style "renpy_inspector_value"
                xmaximum (row_width - 16)
                ymaximum 19


screen renpy_inspector_favorite_row(inspector, favorite, row_width):
    frame:
        style "renpy_inspector_tree_row"
        xysize (row_width, 48)
        hbox:
            spacing 4
            textbutton "★":
                style "renpy_inspector_icon_button"
                action Function(inspector.toggle_favorite, favorite.location[0], favorite.location[1])
            vbox:
                spacing 1
                text favorite.label:
                    style "renpy_inspector_tree_name"
                    xmaximum (row_width - 43)
                    ymaximum 21
                text ("{}  ·  {}".format(favorite.type_name, favorite.preview)):
                    style "renpy_inspector_value"
                    xmaximum (row_width - 43)
                    ymaximum 19


screen renpy_inspector_detail_row(field, value, row_width):
    frame:
        style "renpy_inspector_tree_row"
        xysize (row_width, 48)
        vbox:
            spacing 1
            text field style "renpy_inspector_hint" ymaximum 20
            text value style "renpy_inspector_tree_name" xmaximum (row_width - 16) ymaximum 21


screen renpy_inspector_footer(inspector, footer_h, inner_width):
    frame:
        style "renpy_inspector_footer"
        xfill True
        ysize footer_h
        hbox:
            xfill True
            spacing 8
            text ("Read-only  ·  {} watches".format(len(inspector.favorites))):
                style "renpy_inspector_hint"
                yalign 0.5
                xmaximum (inner_width - 90)
            textbutton "Refresh":
                style "renpy_inspector_action_button"
                action Function(inspector.refresh)
