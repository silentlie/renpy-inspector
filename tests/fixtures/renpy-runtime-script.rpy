# Only copied into a disposable SDK test project. Never shipped in installers.
define config.name = "Ren'Py Inspector Runtime E2E"
define config.main_menu = False
define config.developer = False
define config.save_directory = "renpy-inspector-runtime-e2e"

default e2e_value = 1
default e2e_container = {"hp": 10, "items": ["key", "map"]}
default persistent.e2e_test_flag = True

# Use engine-provided actions so F5/F9 exercise real save/load mechanics.
# These shortcuts are fixture-only, NOT installed in users' games.
init python:
    import os
    import webbrowser

    # Instrument only this disposable test game. The genuine F8 handler
    # still executes InspectorBridge.launch_or_open() and open_browser().
    # Capturing webbrowser.open avoids flaky desktop association setup in CI.
    def e2e_record_browser(url, new=0, autoraise=True):
        destination = os.environ.get("RENPY_E2E_URL_FILE")
        if destination:
            with open(destination, "a") as capture:
                capture.write(url + "\n")
        return True

    def e2e_record_key():
        destination = os.environ.get("RENPY_E2E_URL_FILE")
        if destination:
            with open(destination + ".key", "a") as capture:
                capture.write("F10\n")

    webbrowser.open = e2e_record_browser
    if "e2e_shortcuts" not in config.overlay_screens:
        config.overlay_screens.append("e2e_shortcuts")

screen e2e_shortcuts():
    key "K_F10" action Function(e2e_record_key)
    key "K_F5" action FileSave("e2e-smoke", confirm=False)
    key "K_F9" action FileLoad("e2e-smoke", confirm=False)

label start:
    # This minimal fixture has no generated GUI/overlay stack from the launcher.
    # Explicitly render the actual inspector screen and fixture control screen
    # during the game interaction, using the same native key actions.
    show screen renpy_inspector_overlay
    show screen e2e_shortcuts
    "E2E initial phase. F8 starts the inspector, F5 saves."
    $ e2e_value = 2
    "E2E changed phase. PageUp triggers real Ren'Py rollback."
    $ e2e_value = 3
    "E2E later phase. F9 loads the saved state."
    jump e2e_hold

label e2e_hold:
    "E2E hold. The runtime remains active while browser requests run."
    jump e2e_hold
