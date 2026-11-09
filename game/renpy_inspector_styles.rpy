# All inspector controls are namespaced; host-game default textbutton styles do not leak.
init -90:
    style renpy_inspector_drawer is frame:
        background Solid("#111a2bf7")
        xpadding 12
        ypadding 10

    style renpy_inspector_title is text:
        size 19
        color "#f4f7fd"
        bold True

    style renpy_inspector_section_title is text:
        size 15
        color "#e5edf9"
        bold True

    style renpy_inspector_hint is text:
        size 12
        color "#9fb2cc"

    style renpy_inspector_type is text:
        size 12
        color "#78bfd8"

    style renpy_inspector_value is text:
        size 11
        color "#98bbd5"

    style renpy_inspector_tree_name is text:
        size 13
        color "#f0f4fc"

    style renpy_inspector_tree_name_button is button:
        xpadding 0
        ypadding 0
        background None
        hover_background Solid("#263e5c")

    style renpy_inspector_tree_name_button_text is text:
        size 13
        color "#f0f4fc"
        hover_color "#ffffff"

    style renpy_inspector_tree_row is frame:
        background Solid("#152236")
        xpadding 3
        ypadding 1

    style renpy_inspector_tree_leaf is text:
        size 15
        color "#6785a7"
        yalign 0.5

    style renpy_inspector_load_more_button is button:
        background None
        hover_background Solid("#2c4869")
        xpadding 5
        ypadding 7

    style renpy_inspector_load_more_button_text is text:
        size 12
        bold True
        color "#82c8ed"
        hover_color "#ffffff"

    style renpy_inspector_body is frame:
        background Solid("#10192a")
        xpadding 2
        ypadding 2

    style renpy_inspector_footer is frame:
        background Solid("#1b2940")
        xpadding 5
        ypadding 4

    style renpy_inspector_nav_button is button:
        background Solid("#1a2940")
        hover_background Solid("#2a4564")
        selected_background Solid("#365d81")
        xpadding 5
        ypadding 5

    style renpy_inspector_nav_button_text is text:
        size 12
        color "#c6d4e5"
        hover_color "#ffffff"
        selected_color "#ffffff"

    style renpy_inspector_scope_button is button:
        background None
        hover_background Solid("#253b57")
        selected_background Solid("#314f71")
        xpadding 5
        ypadding 4

    style renpy_inspector_scope_button_text is text:
        size 12
        color "#adc1d9"
        hover_color "#ffffff"
        selected_color "#ffffff"

    style renpy_inspector_action_button is button:
        background Solid("#2c4563")
        hover_background Solid("#40688e")
        xpadding 8
        ypadding 5

    style renpy_inspector_action_button_text is text:
        size 12
        color "#f4f7fc"
        hover_color "#ffffff"

    style renpy_inspector_close_button is button:
        background None
        hover_background Solid("#3a4558")
        xpadding 7
        ypadding 2

    style renpy_inspector_close_button_text is text:
        size 19
        color "#c9d5e8"
        hover_color "#ffffff"

    style renpy_inspector_icon_button is button:
        background None
        hover_background Solid("#294362")
        xpadding 3
        ypadding 2

    style renpy_inspector_icon_button_text is text:
        size 15
        color "#c2d4e8"
        hover_color "#ffffff"

    style renpy_inspector_interval_button is button:
        background Solid("#223650")
        hover_background Solid("#395777")
        selected_background Solid("#416a91")
        xpadding 6
        ypadding 4

    style renpy_inspector_interval_button_text is text:
        size 11
        color "#d8e6f5"
        hover_color "#ffffff"
        selected_color "#ffffff"

    style renpy_inspector_search_field is frame:
        background Solid("#0b1323")
        xpadding 6
        ypadding 4

    style renpy_inspector_search_input is input:
        size 13
        color "#f5f7fc"

    style renpy_inspector_tab_button is button:
        background Solid("#263e5a")
        hover_background Solid("#3b5e80")
        xpadding 10
        ypadding 9

    style renpy_inspector_tab_button_text is text:
        size 13
        color "#f0f5fc"
