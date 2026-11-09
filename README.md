# Ren'Py Inspector

An early **read-only, in-game inspector** for existing Ren'Py desktop games.

> **Status: v0.4 dual-engine MVP, prerelease.** Python unit tests and Ren'Py SDK lint cover core behaviour and script parsing. Actual overlay input, save/load/rollback and performance **still require interactive engine smoke tests** before claiming compatibility. See [docs/COMPATIBILITY.md](docs/COMPATIBILITY.md) and [PLAN.md](PLAN.md).

## Ren'Py 7 / 8 compatibility (v0.4.0)

**One repository and one shared codebase.** The inspector's `game/renpy_inspector/`
modules now run on Python 2.7 and Python 3. Version-dependent operations live in
`compat.py`: string/integer types, case folding, lazy dictionary keys, timing,
and atomic replacement of the inspector-only settings JSON.

Releases provide **two engine-labelled ZIPs** from identical installable source:

- `renpy-inspector-v0.4.N-renpy7.zip` for Ren'Py 7.4.11 / 7.8.7 (Python 2.7)
- `renpy-inspector-v0.4.N-renpy8.zip` for Ren'Py 8.4.1 / 8.5.3 (Python 3)

Each ZIP contains a `COMPATIBILITY.txt` identifying its intended engine, plus the
same `game/` drop-in files. Extract **one** engine package into the root of your
game installation (where `game/` already exists). Do not overlay both packages.
The inspector preferences JSON schema remains version 1 and existing favourites
are preserved. Switching Python runtime versions may still require a game's
own Ren'Py upgrade/migration; the inspector does not migrate host game saves.

CI must pass Python 2.7 compilation/tests, Python 3 regression tests, and SDK
lint on 7.4.11, 7.8.7, 8.4.1 and 8.5.3 before the main-branch automated
prerelease is published. This **does not** constitute successful interactive
save/load/rollback or FPS testing on those engines.

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
- One shared timer while the drawer is open. Configure polling under **Settings → Polling interval**: Off/manual (0), 100, 250 (default), 500 or 1000 ms. The API also accepts arbitrary integers from 50 to 60,000 ms.
- Manual refresh and path re-resolution after object replacement or loading a save.
- Pin any supported row with ☆, view/remove pins on the **Favourites** tab; pinned values remain watched even while viewing a different scope. Missing paths remain pinned and reconnect when values reappear.
- Persist favourite paths, polling interval and drawer width independently of gameplay state using a small atomic JSON settings file at `config.savedir/renpy-inspector-settings.json`.
- Increase/decrease the drawer width, constrained to 320–760 px and the viewport.
- **Search** by name or full path without expanding the tree first. Enter a query and press **Find** or Enter; select a result to expand its parent branches. Search scans at most 2,400 values and returns up to 50 matches within six levels and a 200-child-per-branch cap. Search previews follow changing values on the existing poll; discovery itself only runs when submitted.
- **Named stores:** automatically discover up to eight direct `store.*` module namespaces; register trusted custom roots through `renpy_inspector.register_named_store(name, provider)` in an init Python block. Named-store scope selection and favourite paths persist.
- **Overview:** game name, Ren'Py version, selected scope, favourites, poll interval, last poll duration.
- **Scripts:** current script file/line and return-stack count/label names using available Ren'Py APIs. Return destinations are **not** the current label or debugging stack.
- No arbitrary eval, property calls, game-value writes, telemetry, or network connections. Writes are limited to the inspector's own JSON settings.

## Native tree view UI (v0.4.1)

The drawer uses a native Ren'Py tree with indentation guides, expandable arrows,
a two-line name/type-and-value layout and a pinned-star control. This is not
Material UI / React: it imitates the navigation pattern without embedding a
browser or adding dependencies, so the same files work on Ren'Py 7 and 8.

**To load more variables:** Scroll to the end of a scope or expanded branch and
select **+ Load next 200 entries**. Keep selecting it to reveal additional
batches, up to 1,000 entries per branch. This expands only that branch and
preserves previously expanded children. Collapse other branches if you reach
the global 1,200-row view limit. Search does **not** scan additional pages:
search results remain separately bounded to 2,400 visits and 50 matches.

**Polling controls moved to Settings.** The footer remains visible with
read-only/watch status and a manual Refresh button. In a Ren'Py 7 host game,
confirm navigation text size, indent guides, row clipping and footer position
against multiple resolutions; automated SDK lint does not prove visual fidelity.


## External Ant Design inspector (v0.6.0 proof of concept)

The existing F8 in-game drawer remains available. For a larger, separate
developer workspace, enable **Settings → External inspector (Ant Design) →
Start local server → Open browser**. The server is opt-in, loopback-only
(`127.0.0.1`), session-authenticated, and read-only. It serves bounded
game-state snapshots to a packaged React + Ant Design interface; the game
never evaluates expressions supplied by the browser.

The release ZIP embeds the compiled browser under
`game/renpy_inspector_web/`, so **players do not need Node.js**.
Developers build the React application with `cd web && npm install &&
npm run build`. The new CI job verifies frontend tests and compiles the
application before release publication. Python 2.7/3 regression tests and
Ren'Py SDK lint remain required.

**Important:** External browser favourites are per-browser/per-local-origin
and can reset if the server's port changes. The bridge exposes only the
default Store/Persistent roots, up to 450 nodes, 80 children per branch and
four levels per snapshot. It publishes every ~1.5 seconds when the Ren'Py
overlay is active. See [External GUI guide](docs/EXTERNAL_GUI.md) for
security, limitations, installation and manual acceptance tests.
The browser-based inspector has **not** undergone an interactive Ren'Py
7/8 smoke test and remains experimental.

## Limits and caveats

- **Not an engine-verified release.** CI SDK lint checks syntax/init, but actual overlay behaviour, save/rollback compatibility, scrolling, input conflicts, and FPS need validation in real desktop games. See [compatibility checklist](docs/COMPATIBILITY.md).
- Store filtering hides private names and imported modules/classes/functions. Object attributes beginning `_` are hidden. Dictionary keys other than `str`, `int`, `bool` and `None` are not displayed; set entries, slots and custom mapping types are not expanded.
- The tree loads up to 200 children initially, with a **Load next 200 entries** control at the end of truncated branches. You can reveal up to 1,000 entries per branch (1,200 rows total, 12 levels). Large dictionaries sample a bounded prefix and may omit later or unsupported keys. Search has separate limits.
- Collapsed values are not deeply watched. Expand a branch to watch its children; in-place changes to unsupported types may not be detectable.
- The overlay is hidden whenever Ren'Py suppresses overlays; the shortcut is deliberately unobtrusive and may conflict with a game's existing F8 binding or a custom screen.
- Favourites are limited to 100 root-relative paths of at most 12 segments. Only ordinary attributes, indices and dictionary keys of type string/int/bool/None can be pinned. Index pins follow positions, not original list elements.
- If the Ren'Py save directory is read-only/unavailable, settings still work in memory and a nonfatal warning appears; persistent settings are not guaranteed.
- Search is **submit-to-search**, not a background index or live per-keystroke search. It scans a bounded prefix of each collection and may not find every match in a large or deep game. Click-to-reveal expands ancestors but does not automatically scroll to the target row.
- Named-store discovery inspects only direct `store.*` modules visible in the default store, scanning at most the first 1,000 fields; customised or nested namespaces may require explicit registration. At most eight names are offered.
- The Scripts panel shows only available statement location and return destinations, not a full debugger. Advanced appearance and code navigation remain future work.
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

Optional Python-only benchmarks: `python tests/benchmarks/bench_core.py` and `python tests/benchmarks/bench_search.py` (100/1,000/10,000 logical entries; neither measures Ren'Py rendering).

To register a store when auto-discovery isn't suitable, use an `init` block in a game you control:

```renpy
init 1 python:
    renpy_inspector.register_named_store("characters", lambda: renpy.store.characters)
```

**Search and script panels are read-only.** UI search only evaluates member names and safe previews; it does not run Python expressions.

## Automated GitHub releases

Every merge into `main` triggers [Release drop-in mod](.github/workflows/release.yml) (a direct push also triggers it). After unit tests pass, it builds a deterministic ZIP containing only the installable `game/` sources and attaches the ZIP and SHA-256 checksum to a GitHub **prerelease**. The first v0.4 tag is `v0.4.0`, with subsequent merges incrementing the patch number (`v0.4.1`, etc.). Retry of the same commit reuses its tag. SDK lint runs separately in [test.yml](.github/workflows/test.yml), so the release job alone does not establish engine compatibility.

Find generated ZIPs under [GitHub Releases](https://github.com/silentlie/renpy-inspector/releases). Extract the ZIP into the game's **installation root**, which contains its `game/` directory. Alternatively, copy the ZIP's `game/` contents into that directory. Verify the checksum with `sha256sum -c renpy-inspector-v0.4.N-renpy7.zip.sha256` (or the `renpy8` counterpart)` (substituting the release number).

Re-running a successful release job re-uploads the assets to the same tag. The workflow requires the repository's GitHub Actions `GITHUB_TOKEN` to have permission to write repository contents (granted in the workflow and subject to repository/organisation policy). **These are prereleases because Ren'Py engine smoke testing and save/rollback compatibility validation are still outstanding.** Do not treat an automated release as engine certification.

## Architecture

- `inspection.py`: dependency-free, bounded reads and safe previews.
- `controller.py`: lazy nodes, independent favourite watches, path re-resolution, change detection and scope lifecycle.
- `favorites.py`: typed, serializable root-relative paths.
- `settings.py`: validated, atomic JSON settings outside gameplay saves.
- `search.py`: bounded, cycle-safe traversal and immutable result paths.
- `runtime.py`: conservative Ren'Py script-location and return-stack adapter.
- `renpy_inspector.rpy`: registration, live roots and after-load cache invalidation.
- `renpy_inspector_screens.rpy`: cached row rendering via one `vpgrid`, UI actions and one timer.
- `renpy_inspector_styles.rpy`: style overrides confined to the inspector.

The inspector is strictly read-only with respect to gameplay. It does not mutate game variables or Ren'Py persistent fields; it writes only its own JSON settings. Save/load and in-engine compatibility still need interactive confirmation.

### Python 2.7 core checks

Run `python2 -m compileall -q game/renpy_inspector` followed by
`python2 -m unittest discover -s tests_py2 -v`. On CI the legacy interpreter
comes from a version-pinned Python 2.7 Docker image. The modern build tool and
Python 3 test suite need not themselves run under Python 2.7.
