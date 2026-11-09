# Ren'Py runtime compatibility matrix

## Automated checks

The Python suite checks lazy inspection, pinned paths, bounded search, named-store discovery, script context, restored/replaced roots, polling isolation, settings safety, ZIP integrity and fixture assembly. The CI SDK matrix runs **Ren'Py lint** against the assembled fixture on official 8.4.1 and 8.5.3 SDKs. Lint detects script parsing / init issues, not runtime overlay behaviour.

## Interactive checks still required

Use `python scripts/prepare_fixture.py /tmp/renpy-inspector-fixture` to construct a clean project from tracked sources. With each SDK, run `./renpy.sh /tmp/renpy-inspector-fixture run` and verify:

- F8 and the Inspect tab open/close the overlay without blocking normal game input. Switch Overview, Variables, Scripts and Settings tabs.
- Search for `hp` or `player_stats` from the Variables panel, click a result to reveal it, expand `player_stats`, pin `hp`, switch to Persistent, and see its value update when the story changes.
- Switch to Named, inspect `characters.affection`, pin its `alice` value and verify favourites remain live across scopes.
- Inspect Overview and Scripts; verify game name, engine version, statement file/line and return-stack context when available.
- Set manual-only mode and confirm no timer-driven changes; restore 250 ms and observe changes.
- Remove a pin, restart the game, and confirm preferences persist in `config.savedir/renpy-inspector-settings.json`.
- Save with the drawer open, change `player_stats`, load, and verify there are no stale cached references.
- Roll back the change and verify the pinned value matches restored gameplay state.
- Replace the `player_stats` dictionary, confirm its favourite path follows the replacement.
- Use a narrower resolution and mouse wheel; ensure the viewport doesn't break story UI.
- Remove only the mod files and confirm original saves load in the unmodified fixture.
- Profile idle/active FPS and memory relative to the same game without the mod. Include a 10,000-element collection; measure search latency separately from rendering.

| Ren'Py version | Python unit suite | SDK lint | Interactive/save-load test |
|---|---|---|---|
| 8.4.1 | Independent of SDK | Passed in PR #3 (Ren'Py SDK lint) | Not yet verified |
| 8.5.3 | Independent of SDK | Passed in PR #3 (Ren'Py SDK lint) | Not yet verified |

**Do not claim engine compatibility or stable release until interactive checks above are recorded.** Core benchmarks are not a substitute for gameplay FPS/memory tests. v0.3 prerelease status remains appropriate until then.
