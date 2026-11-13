# Release and upgrade acceptance (PR #17, v0.7.0)

This remains a **prerelease**. Passing tests, packaging checks and SDK lint
does not certify that F8, rollback or rendering works in every Ren'Py game.
There is no FPS threshold or requirement to build another benchmark if no
performance regression is visible.

## Automated checks (run before publishing)

1. Python 2.7 compatibility tests; Python 3.9/3.13 unit tests.
2. Official SDK lint on Ren'Py 7.4.11, 7.8.7, 8.4.1, and 8.5.3.
3. Ant Design UI unit tests and a production Vite build.
4. Build both engine-labelled ZIP files, calculate SHA256 checksums, then
   verify **each** checksum, a closed source manifest, safe archive members,
   source and web bundle completeness, correct engine labels, and identical
   installable payloads in the two engine ZIPs.
5. Release workflow repeats the same checks **after building from main**
   before it publishes prerelease assets.

To verify downloaded archives from a source checkout:

```sh
python scripts/verify_release.py \
  dist/renpy-inspector-v0.7.8-renpy7.zip \
  dist/renpy-inspector-v0.7.8-renpy8.zip
```

Keep each `.zip.sha256` file alongside its corresponding ZIP. Different
checksum, missing compiled JS/CSS, an added legacy screen, duplicate member,
unexpected path, or differing engine payload must fail closed.

The build deliberately includes only `scripts/build_release.py`'s declared
`REQUIRED_FILES` and the compiled browser assets. An additional
`renpy_inspector*.rpy` or package `.py` file fails until explicitly reviewed
and added to the manifest or removed. Do not copy tooling or old experimental
native-screen modules into the release archive.

## Manual game installation and upgrade

1. Back up the **whole** game directory and existing save directory first.
   Choose a game you have permission to inspect or a disposable test project.
2. Obtain `renpy-inspector-v0.7.8-renpy7.zip` or
   `renpy-inspector-v0.7.8-renpy8.zip` from the PR preview. If downloaded
   from GitHub Actions, extract the **outer artifact ZIP** before selecting
   the one correct engine installer.
3. Extract that **inner** archive into the installation root (the directory
   already containing `game/`). Never extract into `game/` itself.
4. If upgrading an older in-game inspector, make sure its old
   `renpy_inspector_tree.rpy` and other experimental inspector GUI scripts
   have not been left in `game/`. The new `renpy_inspector_screens.rpy`
   is F8-only and the `renpy_inspector_styles.rpy` is an empty stub.
   Leave unrelated game code untouched.
5. From a checked-out repository, run the **read-only** install checker:

   ```sh
   python scripts/check_install.py "/path/to/your-game-installation"
   ```

   It checks the correct root nesting, required Python/Ren'Py sources, the
   Vite JS/CSS references, legacy extra screens, and orphan `.rpyc`
   remnants. It never deletes files or touches save data. Resolve any
   warnings after checking the original game's contents; do not delete
   bytecode blindly.
6. Start the game and press **F8**. Only the external browser should open;
   there is no native inspector panel. Pressing F8 again must reuse the same
   local session, and closing the browser must not kill the game.
7. On one actual Ren'Py 7 and one Ren'Py 8 game, verify live root and nested
   values, paging, deep favourite paths, global popup search/reveal,
   current script navigation, and read-only behavior.
8. Save a game, change variables, load, then rollback two steps. Values and
   Compare should discard old-generation state; favourites must survive as
   paths and reconnect or show missing status. Test an overlay/menu where the
   inspector may not receive interaction ticks.
9. Try a game distributing only `.rpyc`: label navigation may work, while
   missing `.rpy` source excerpts should produce an unavailable state.
10. Exit the game and confirm the localhost service ends. Compare an ordinary
    play session with the inspector idle and active; record any repeatable
    stutter, crash, freeze or elevated queue rejections. Do not chase FPS
    above monitor refresh rate without an observed problem.

## Release gate

- **Automated:** all jobs green on the exact PR head, both verified preview
  archives present; release workflow reruns and verifies the merge commit.
- **Manual:** no reproducible correctness regression in F8, live reads,
  browser, save/load/rollback, or upgrade layout in real Ren'Py 7/8 games.
- **Unknowns:** platform/browser key-binding conflicts, customised game
  overlays and frame-time behaviour outside the tested games remain documented.
- **Publication:** use prerelease badges and note experimental compatibility;
  do not claim production certification solely from SDK lint.

If the project deliberately proceeds with partial manual coverage, record
that gap explicitly rather than pretending automated lint tested gameplay.
