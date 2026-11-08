# Namespaced styles to avoid changing the host game's default styles.
init -90:
    style renpy_inspector_drawer is frame:
        background Solid("#141b2af0")
        xpadding 14
        ypadding 16

    style renpy_inspector_title is text:
        size 23
        color "#f2f4fb"
        bold True

    style renpy_inspector_hint is text:
        size 13
        color "#b2bfd2"

    style renpy_inspector_type is text:
        size 12
        color "#80c8dc"
        yalign 0.5

    style renpy_inspector_value is text:
        size 13
        color "#e5eaf5"
        yalign 0.5

    style renpy_inspector_tab_button is button:
        background Solid("#213149de")
        hover_background Solid("#344f73")
        xpadding 9
        ypadding 12

    style renpy_inspector_row_button is button:
        xpadding 3
        ypadding 2
        background None
        hover_background Solid("#344f73")

    style renpy_inspector_row_button_text is text:
        size 13
        color "#ecf1fc"
        hover_color "#ffffff"

    style renpy_inspector_interval_button is button:
        xpadding 3
        ypadding 3
        background Solid("#24344d")
        hover_background Solid("#3b5677")
        selected_background Solid("#43709b")

    style renpy_inspector_interval_button_text is text:
        size 12
        color "#edf4ff"
