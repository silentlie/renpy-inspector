# Ren'Py Inspector

An early **read-only, in-game inspector** for existing Ren'Py desktop games.

> **Status: v0.2 read-only MVP, prerelease.** The Python inspection core is unit-tested; CI runs Ren'Py SDK lint on 8.4.1 and 8.5.3. Native overlay input, saves and rollback **still require interactive engine smoke tests** before claiming compatibility. See [docs/COMPATIBILITY.md](docs/COMPATIBILITY.md) and [PLAN.md](PLAN.md).

## Install

1. Back up the game's `game/` folder and saves. Do not alter the game's original `.rpy` files.
2. Copy the three `.rpy` files and the complete `game/renpy_inspector/` package into the game's `game/` directory, preserving the same paths:

   ```text
   game/
   ├── renpy_inspector.rpy
   ├── renpy_inspector_screens.rpy
   ├── renpy_inspector_styles.rpy
   └── renpy_inspector/
       ├── __init__.py
       ├── controller.py
       ├── inspection.py
       ├── favorites.py
       └── settings.py
   ```

3. Launch the game with a Ren'Py 8.x desktop runtime for testing. **Press F8** or click the right-edge **Inspect** tab. The read-only drawer appears over gameplay. Engine compatibility has not yet been established.
4. To uninstall, delete only the files shown above, not any pre-existing files in the host game. The optional `renpy-inspector-settings.json` file in the Ren'Py save directory can also be deleted; this is **not** a gameplay save. Keep your original backup until you have tested saves both with and without the mod.

Installing third-party `.rpy` code can be incompatible with modified/locked-down games. This mod is intended for games you are authorised to modify or inspect.

## MVP features

- Native right-side drawer with the default `store` and `persistent` namespaces.
- Expand/collapse built-in dictionaries, lists, tuples and ordinary instance `__dict__` fields, one level at a time.
- Type names and short previews, a cycle marker and a marker when child enumeration is capped.
- One shared timer while the drawer is open. Choose manual-only (0), 100, 250 (default), 500 or 1000 ms. The API also accepts arbitrary integers from 50 to 60,000 ms.
- Manual refresh and path re-resolution after object replacement or loading a save.
- Pin any supported row with ☆, view/remove pins on the **Favourites** tab; pinned values remain watched even while viewing a different scope. Missing paths remain pinned and reconnect when values reappear.
- Persist favourite paths, polling interval and drawer width independently of gameplay state using a small atomic JSON settings file at `config.savedir/renpy-inspector-settings.json`.
- Increase/decrease the drawer width, constrained to 320–760 px and the viewport.
- No arbitrary eval, property calls, game-value writes, telemetry, or network connections. Writes are limited to the inspector's own JSON settings.

## Limits and caveats

- **Not an engine-verified release.** CI SDK lint checks syntax/init, but actual overlay behaviour, save/rollback compatibility, scrolling, input conflicts, and FPS need validation in real desktop games. See [compatibility checklist](docs/COMPATIBILITY.md).
- Store filtering hides private names and imported modules/classes/functions. Object attributes beginning `_` are hidden. Dictionary keys other than `str`, `int`, `bool` and `None` are not displayed; set entries, slots and custom mapping types are not expanded.
- Each node shows at most 200 children; a maximum of 1,200 visible rows and 12 levels is enforced to limit frame-time spikes. Large dictionaries sample only a bounded key prefix and may omit relevant later keys.
- Collapsed values are not deeply watched. Expand a branch to watch its children; in-place changes to unsupported types may not be detectable.
- The overlay is hidden whenever Ren'Py suppresses overlays; the shortcut is deliberately unobtrusive and may conflict with a game's existing F8 binding or a custom screen.
- Favourites are limited to 100 root-relative paths of at most 12 segments. Only ordinary attributes, indices and dictionary keys of type string/int/bool/None can be pinned. Index pins follow positions, not original list elements.
- If the Ren'Py save directory is read-only/unavailable, settings still work in memory and a nonfatal warning appears; persistent settings are not guaranteed.
- Named stores, search, multi-tab overview and advanced appearance remain future work.
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

Create a standalone fixture with `python scripts/prepare_fixture.py /tmp/inspector-fixture` and run SDK lint using `./renpy.sh /tmp/inspector-fixture lint --error-code` from the SDK directory. The CI matrix uses the official Ren'Py 8.4.1 and 8.5.3 SDKs. **Lint is not an interactive smoke test.** Record manual tests and evidence in [docs/COMPATIBILITY.md](docs/COMPATIBILITY.md) before declaring a stable release.

Optional core-only timing: `python tests/benchmarks/bench_core.py` (100/1,000/10,000 logical entries, without Ren'Py rendering).

## Automated GitHub releases

Every merge into `main` triggers [Release drop-in mod](.github/workflows/release.yml) (a direct push also triggers it). After unit tests pass, it builds a deterministic ZIP containing only the installable `game/` sources and attaches the ZIP and SHA-256 checksum to a GitHub **prerelease**. The first v0.2 tag is `v0.2.0`, with subsequent merges incrementing the patch number (`v0.2.1`, etc.). Retry of the same commit reuses its tag. SDK lint runs separately in [test.yml](.github/workflows/test.yml), so the release job alone does not establish engine compatibility.

Find generated ZIPs under [GitHub Releases](https://github.com/silentlie/renpy-inspector/releases). Extract the ZIP into the game's **installation root**, which contains its `game/` directory. Alternatively, copy the ZIP's `game/` contents into that directory. Verify the checksum with `sha256sum -c renpy-inspector-v0.2.N.zip.sha256` (substituting the release number).

Re-running a successful release job re-uploads the assets to the same tag. The workflow requires the repository's GitHub Actions `GITHUB_TOKEN` to have permission to write repository contents (granted in the workflow and subject to repository/organisation policy). **These are prereleases because Ren'Py engine smoke testing and save/rollback compatibility validation are still outstanding.** Do not treat an automated release as engine certification.

## Architecture

- `inspection.py`: dependency-free, bounded reads and safe previews.
- `controller.py`: lazy nodes, independent favourite watches, path re-resolution, change detection and scope lifecycle.
- `favorites.py`: typed, serializable root-relative paths.
- `settings.py`: validated, atomic JSON settings outside gameplay saves.
- `renpy_inspector.rpy`: registration, live roots and after-load cache invalidation.
- `renpy_inspector_screens.rpy`: cached row rendering via one `vpgrid`, UI actions and one timer.
- `renpy_inspector_styles.rpy`: style overrides confined to the inspector.

The inspector is strictly read-only with respect to gameplay. It does not mutate game variables or Ren'Py persistent fields; it writes only its own JSON settings. Save/load and in-engine compatibility still need interactive confirmation.
