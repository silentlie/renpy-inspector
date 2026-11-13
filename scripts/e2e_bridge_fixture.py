"""Deterministic real-HTTP bridge fixture for Playwright browser E2E.

This runs the actual authenticated InspectorBridge server and its game-thread
tick loop against synthetic providers. It is NOT the Ren'Py engine: F8,
overlay timing and save/rollback engine callbacks require separate smoke tests.

Commands come from this child process's stdin, NEVER through inspector HTTP.
The bridge is read-only by default; a test-only process flag explicitly opts
in to the separate primitive-edit E2E case.
"""
from __future__ import print_function

import json
import os
import queue
import sys
import tempfile
import threading
import time
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'game'))

from renpy_inspector.bridge import InspectorBridge
from renpy_inspector.controller import Inspector


class MockLabel(object):
    def __init__(self, line):
        self.filename = 'script.rpy'
        self.linenumber = line


class MockScript(object):
    def lookup(self, name):
        return MockLabel(1 if name == 'start' else 4)


class MockRenpy(object):
    def __init__(self):
        self.game = type('Game', (), {'script': MockScript()})()

    def get_all_labels(self):
        return ['start', 'chapter_two', '_internal']


def emit(data):
    print(json.dumps(data, separators=(',', ':')), flush=True)


def main():
    with tempfile.TemporaryDirectory(prefix='renpy-inspector-e2e-') as temp:
        store = ModuleType('store')
        store.score = 2
        store.memo = 'A' * 110 + 'before'
        store.story_text = 'Line one\nLine two: \u2603'
        store.large_text = 'L' * 17000
        store.player_stats = {'hp': 10, 'inventory': ['key', 'map']}
        store.player_stats[3] = 'numbered key'
        store.player_stats['snow ☃'] = 'unicode key'
        store.inventory = list(range(170))
        store.set_flags = set(['open', 'closed', 42, True, None])
        store.frozen_flags = frozenset(['blue', 'red'])
        store.mixed_set = set(['visible', object()])
        persistent = {'test_flag': True}
        runtime_line = {'line': 1}
        controller = Inspector()
        controller.bind(
            lambda: store, lambda: persistent,
            context_provider=lambda: {
                'game': 'Playwright Fixture', 'version': '8.5.3 (synthetic)',
                'filename': 'game/script.rpy', 'line': runtime_line['line'],
                'rollback_active': False,
            })
        bridge = InspectorBridge(controller, str(ROOT / 'web' / 'dist'))
        bridge.configure_favourites_directory(temp)
        # Test-only developer opt-in from the fixture's trusted process,
        # never from a browser request or gameplay value.
        bridge.configure_variable_editing(
            os.environ.get('RENPY_INSPECTOR_E2E_ENABLE_EDITS') == '1')
        scriptdir = Path(temp) / 'game'
        scriptdir.mkdir()
        (scriptdir / 'script.rpy').write_text(
            'label start:\n    "A game fixture"\n'
            '    $ score = 2\n\nlabel chapter_two:\n'
            '    "Next scene: score should be visible"\n', encoding='utf-8')
        (scriptdir / 'references.rpy').write_text(
            'label secondary:\n    # score is referenced here\n'
            '    $ player_stats["hp"] = score\n', encoding='utf-8')
        bridge.configure_script_runtime(MockRenpy(), str(scriptdir))
        bridge.start()
        if not bridge.running:
            emit({'error': bridge.error})
            sys.exit(1)
        commands = queue.Queue()

        def listen():
            for line in sys.stdin:
                try:
                    commands.put(json.loads(line))
                except (ValueError, TypeError):
                    pass
            commands.put({'action': 'exit', 'id': 0})

        worker = threading.Thread(target=listen, daemon=True)
        worker.start()
        emit({'ready': bridge.url})
        try:
            while True:
                try:
                    command = commands.get_nowait()
                except queue.Empty:
                    command = None
                if command is not None:
                    action = command.get('action')
                    if action == 'exit':
                        emit({'ack': command.get('id'), 'stopped': True})
                        break
                    if action == 'set_score':
                        store.score = int(command['value'])
                    elif action == 'set_runtime_line':
                        runtime_line['line'] = max(1, min(10000, int(command['line'])))
                        bridge.publish()
                    elif action == 'change_memo':
                        store.memo = 'A' * 110 + str(command['value'])
                    elif action == 'remove_set_member':
                        store.set_flags.discard('open')
                    elif action == 'restore_set_member':
                        store.set_flags.add('open')
                        bridge.publish()
                    elif action == 'shrink_inventory':
                        store.inventory = list(range(12))
                        bridge.publish()
                    elif action == 'replace_stats':
                        store.player_stats = 7
                        bridge.publish()
                    elif action == 'restore_game':
                        store.score = 2
                        store.memo = 'A' * 110 + 'before'
                        store.set_flags = set(['open', 'closed', 42, True, None])
                        store.frozen_flags = frozenset(['blue', 'red'])
                        store.mixed_set = set(['visible', object()])
                        store.player_stats = {'hp': 10, 'inventory': ['key', 'map']}
                        store.inventory = list(range(170))
                        bridge.invalidate()
                        controller.reset()
                        bridge.publish()
                    elif action == 'bump_hp':
                        store.player_stats['hp'] = int(command['value'])
                        bridge.publish()
                    else:
                        emit({'ack': command.get('id'), 'error': 'unknown action'})
                        continue
                    emit({'ack': command.get('id'), 'generation': bridge.generation})
                bridge.tick()
                time.sleep(0.05)
        finally:
            bridge.stop()


if __name__ == '__main__':
    main()
