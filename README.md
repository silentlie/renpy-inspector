# Ren'Py Inspector

An early **read-only, in-game inspector** for existing Ren'Py desktop games.

> **Status: first MVP / unverified engine integration.** The Python inspection core is unit-tested independently. The native Screen Language overlay still needs a smoke test using the Ren'Py 8.4 and 8.5 SDKs before any compatibility claim. See [PLAN.md](PLAN.md) for the broader roadmap.

## Install

1. Back up the game's `game/` folder and saves. Do not alter the game's original `.rpy` files.
2. Copy **all three** files under this repository's `game/` directory and the complete `game/renpy_inspector/` package into the game's `game/` directory, preserving the same paths:

   ```text
   game/
   ├── renpy_inspector.rpy
   ├── renpy_inspector_screens.rpy
   ├── renpy_inspector_styles.rpy
   └── renpy_inspector/
       ├── __init__.py
       ├── controller.py
       └── inspection.py
   ```

3. Launch the game with a compatible Ren'Py 8.x desktop runtime. **Press F8** or click the right-edge **Inspect** tab. The read-only drawer appears over gameplay.
4. To uninstall, delete only the files shown above, not any pre-existing files in the host game. Keep your original backup until you have tested saves both with and without the mod.

Installing third-party `.rpy` code can be incompatible with modified/locked-down games. This mod is intended for games you are authorised to modify or inspect.

## MVP features

- Native right-side drawer with the default `store` and `persistent` namespaces.
- Expand/collapse built-in dictionaries, lists, tuples and ordinary instance `__dict__` fields, one level at a time.
- Type names and short previews, a cycle marker and a marker when child enumeration is capped.
- One shared timer while the drawer is open. Choose manual-only (0), 100, 250 (default), 500 or 1000 ms. The API also accepts arbitrary integers from 50 to 60,000 ms.
- Manual refresh and path re-resolution after object replacement or loading a save.
- No arbitrary eval, property calls, game-value writes, network connection, or file writes.

## Limits and caveats

- **Not an engine-verified release.** The Screen Language files and hooks need validation in a real Ren'Py 8.x fixture game before distributing to players. No save/rollback and UI benchmark evidence yet.
- Store filtering hides private names and imported modules/classes/functions. Object attributes beginning `_` are hidden. Dictionary keys other than `str`, `int`, `bool` and `None` are not displayed; set entries, slots and custom mapping types are not expanded.
- Each node shows at most 200 children; a maximum of 1,200 visible rows and 12 levels is enforced to limit frame-time spikes. Large dictionaries sample only a bounded key prefix and may omit relevant later keys.
- Collapsed values are not deeply watched. Expand a branch to watch its children; in-place changes to unsupported types may not be detectable.
- The overlay is hidden whenever Ren'Py suppresses overlays; the shortcut is deliberately unobtrusive and may conflict with a game's existing F8 binding or a custom screen.
- Inspector settings live in module memory only and reset on relaunch. Persisted favourites, named stores, search, multi-tab overview, and flexible appearance belong to subsequent milestones.
- Python introspection is *conservative*, not guaranteed side-effect-free for arbitrary hostile extension objects. The normal use case is well-behaved game data.

## Development and validation

Run tests without Ren'Py or additional Python packages:

```sh
python -m unittest discover -s tests -v
```

For an engine smoke test, create a fresh Ren'Py 8.4/8.5 sample game, copy the drop-in files, and use this minimal scene in a **new fixture game**:

```renpy

default player_stats = {"hp": 10, "items": ["key"]}

label start:
    "Open the inspector with F8 and expand player_stats."
    $ player_stats["hp"] = 9
    "Health changed."
    $ player_stats["items"].append("map")
    "Inventory changed."
    return
```

Confirm visibility, scrolling, polling on/off, no duplicate timer, save/load/rollback, clean uninstall and whether F8 interferes with game input. Track test results against [PLAN.md](PLAN.md) before publishing a release.

## Architecture

- `inspection.py`: dependency-free, bounded reads and safe previews.
- `controller.py`: lazy nodes, path re-resolution, change detection and scope lifecycle.
- `renpy_inspector.rpy`: registration, live roots and after-load cache invalidation.
- `renpy_inspector_screens.rpy`: cached row rendering via one `vpgrid`, UI actions and one timer.
- `renpy_inspector_styles.rpy`: style overrides confined to the inspector.

The inspector is strictly read-only. It does not mutate gameplay values, but full isolation from save/load and host-game integration requires the planned Ren'Py runtime tests.
