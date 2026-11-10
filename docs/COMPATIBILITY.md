# Ren'Py Inspector: engine compatibility

The PR #8 external-only build keeps one Python 2.7/3-compatible inspection package for Ren'Py 7 and 8, with a separate React + Ant Design browser interface.

| SDK | Interpreter | Automated validation | Manual in-game check |
| --- | --- | --- | --- |
| Ren'Py 7.4.11 | Python 2.7 | CI lint and standalone tests | Still required |
| Ren'Py 7.8.7 | Python 2.7 | CI lint and standalone tests | Still required |
| Ren'Py 8.4.1 | Python 3 | CI lint and standalone tests | Still required |
| Ren'Py 8.5.3 | Python 3 | CI lint and standalone tests | Still required |

The native implementation is now a **displayless overlay screen** handling F8 and a snapshot timer. It contains no drawer, tree, tabs, settings or other in-game inspector widgets.

## Interactive acceptance criteria

1. With inspector files installed but no bridge active, gameplay and normal save/load work. The server must not auto-start during init.
2. F8 starts the localhost bridge, opens the browser and does not show a native inspector GUI.
3. A second F8 press opens the **same session URL**, with the same port/token.
4. Actual browser game state matches the current scene, updates through the 1.5-second Ren'Py interaction-thread timer, and remains read-only.
5. Browser close/reopen works; the server remains alive while the game continues.
6. The server fails safely if Ant Design assets or a default browser are unavailable. Transient errors should not block gameplay.
7. Save/load/rollback invalidates stale snapshots and does not serialize inspector state into gameplay saves.
8. Test F8 with menus, modal dialogues, hidden overlays and customised game keymaps. F8 may be intercepted by host games; record exceptions.
9. Validate no HTTP writes/eval, token/session isolation, loopback-only binding, and bounded inspection.
10. Benchmark game FPS, memory use, and responsiveness without inspector, inspector installed/idle, and inspector/browser active.
11. Test uninstall/upgrade after previous native drawer releases. The styles file is overwritten with an empty stub and the old drawer screen is replaced; remove independently installed experimental GUI files.

SDK lint verifies syntax/init, not actual browser launch, F8 handling or save/rollback behaviour. Do not claim universal engine or game compatibility without interactive evidence.
