# Ren'Py runtime compatibility matrix

## Automated checks for v0.4.0

One shared game-source tree supports both Python 2.7 and Python 3 using
`game/renpy_inspector/compat.py`. There are no duplicated engine branches.
Each tagged release builds engine-labelled `-renpy7.zip` and `-renpy8.zip`
archives from identical installable source, with SHA-256 checksums.

Pull requests run Python 3.9/3.13 tests, a standalone Python 2.7 Docker job
which **compiles the whole game Python package and runs its own regression
suite**, and official SDK lint on all four versions listed below. The release
workflow repeats the complete validation workflow on the merge commit before
publishing both packages.

| Ren'Py SDK | Interpreter | SDK lint | Interactive/save-load test |
|---|---|---|---|
| 7.4.11 | Python 2.7 | CI configured; verify PR run | Not yet verified |
| 7.8.7 | Python 2.7 | CI configured; verify PR run | Not yet verified |
| 8.4.1 | Python 3 | CI configured; verify PR run | Not yet verified |
| 8.5.3 | Python 3 | CI configured; verify PR run | Not yet verified |

SDK lint tests script parsing and initialization, not input or actual gameplay.
The Python 2.7 regression suite verifies the inspection core and settings on
that runtime, but it is not embedded in the Ren'Py interpreter or renderer.

## Interactive checks still required

Create the fixture with
`python scripts/prepare_fixture.py /tmp/renpy-inspector-fixture`, then start it
in each SDK. Record OS, resolution, test actions, logs and measured FPS.

- F8 and the Inspect tab open/close the overlay without blocking gameplay.
  Test Overview, Variables, Scripts and Settings at multiple resolutions.
- Search for nested variables; click to reveal; expand, pin and track values.
- Inspect discovered `characters.affection` named store and a registered root.
- Display current script file/line, return-stack depth and engine version.
- Toggle 0 ms manual polling and normal 250 ms polling; ensure one timer only.
- Restart the game; verify favourites, named-scope selection and width persist.
- Save with drawer open; load and rollback; confirm no stale references or
  inspector data accidentally inserted into game saves.
- Replace watched dictionaries and modules; verify watched paths reconnect.
- Test Unicode dictionary keys, lists, cycles, very large dictionaries and
  case-insensitive search on both Python 2 and Python 3.
- Uninstall only inspector files; verify pre-existing host saves still load.
- Measure UI responsiveness, idle/active FPS, memory and long-running polling
  relative to the same game with the mod removed.

**Do not claim fully validated game compatibility or stable release until these
interactive checks are documented.** Standalone benchmarks and SDK lint cannot
replace engine-level runtime verification.
