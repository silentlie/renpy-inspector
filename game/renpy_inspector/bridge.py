"""Opt-in, authenticated loopback bridge for the Ant Design inspector UI.

HTTP workers never inspect or mutate gameplay objects. Game state is read and,
only when trusted game init explicitly enables primitive editing, mutated by
Ren'Py's interaction-thread tick. Filesystem writes remain limited to the
bounded, authenticated inspector-preferences file.
"""
from __future__ import unicode_literals

import binascii
import mimetypes
import os
import threading
import time
import webbrowser
import json

try:
    from BaseHTTPServer import HTTPServer, BaseHTTPRequestHandler
    from SocketServer import ThreadingMixIn
    from urlparse import urlsplit, parse_qs
except ImportError:
    from http.server import HTTPServer, BaseHTTPRequestHandler
    from socketserver import ThreadingMixIn
    from urllib.parse import urlsplit, parse_qs

from .bridge_snapshot import PROTOCOL, encode_snapshot
from .bridge_paging import (build_tree_page, build_lazy_snapshot,
                            build_tree_value, build_full_value, validate_tree_request)
from .bridge_search import (build_search_results, build_reveal_chain,
                            validate_search_request)
from .bridge_scripts import (list_labels, source_excerpt, search_source_text,
                             validate_label_request, validate_source_request,
                             validate_source_search_request)
from .browser_favourites import (BrowserFavouritesStore,
                                 MAX_PREFERENCE_BYTES, validate_favourites)
from .compat import monotonic_time
from .runtime_history import RuntimeTimeline
from .edit_values import (MAX_EDIT_REQUEST_BYTES, validate_edit_request,
                          inspect_edit_target, apply_primitive_edit,
                          EditConflict, EditLocked, EditUnsupported)
from .edit_history import (PrimitiveEditHistory, MAX_HISTORY_REQUEST_BYTES,
                           validate_edit_history_request)
from .variable_locks import (VariableLocks, MAX_VARIABLE_LOCK_REQUEST_BYTES,
                             VariableLockLimit, VariableLockMissing,
                             validate_variable_lock_request)

LOOPBACK = '127.0.0.1'
DEFAULT_UI_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), '..',
                                               'renpy_inspector_web'))
ALLOWED_DEV_ORIGINS = ('http://127.0.0.1:5173', 'http://localhost:5173')


class _Server(ThreadingMixIn, HTTPServer):
    daemon_threads = True
    allow_reuse_address = True
    request_queue_size = 8


class _Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.0'

    def log_message(self, format, *args):
        # No game values, credentials or request paths in HTTP logs.
        return

    def _send(self, code, body=b'', mime='text/plain; charset=utf-8', origin=None):
        self.send_response(code)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self' data:; connect-src 'self' http://127.0.0.1:5173")
        if origin in ALLOWED_DEV_ORIGINS:
            self.send_header('Access-Control-Allow-Origin', origin)
            self.send_header('Vary', 'Origin')
            self.send_header('Access-Control-Allow-Headers', 'X-Inspector-Token')
            self.send_header('Access-Control-Allow-Methods', 'GET, PUT, OPTIONS')
        self.end_headers()
        if body:
            self.wfile.write(body)

    def _allowed_origin(self):
        origin = self.headers.get('Origin')
        local = 'http://{}:{}'.format(LOOPBACK, self.server.server_port)
        if origin is not None and origin not in ALLOWED_DEV_ORIGINS + (local,):
            return False
        # Reject DNS rebinding and foreign Host headers even on loopback.
        return self.headers.get('Host') == '{}:{}'.format(LOOPBACK, self.server.server_port)

    def do_OPTIONS(self):
        if not self._allowed_origin():
            self._send(403)
            return
        origin = self.headers.get('Origin')
        if urlsplit(self.path).path in (
                '/api/v1/snapshot', '/api/v1/children', '/api/v1/value',
                '/api/v1/favourites', '/api/v1/search', '/api/v1/reveal',
                '/api/v1/full-value', '/api/v1/scripts', '/api/v1/source',
                '/api/v1/source-search', '/api/v1/edit-target',
                '/api/v1/edit', '/api/v1/edit-history',
                '/api/v1/locks') and origin in ALLOWED_DEV_ORIGINS:
            self._send(204, origin=origin)
        else:
            self._send(404)

    def do_POST(self):
        self._send(405)

    def _write_edit(self, origin):
        """Authenticated HTTP payload validation; no gameplay access here."""
        bridge = self.server.bridge
        if not self.headers.get('X-Inspector-Token') or self.headers.get('X-Inspector-Token') != bridge.token:
            self._send(401, b'Unauthorized', origin=origin)
            return
        with bridge.lock:
            if not bridge.editing_enabled:
                self._send(403, b'Primitive editing is not enabled in game config', origin=origin)
                return
        try:
            raw_size = self.headers.get('Content-Length', '')
            if not raw_size.isdigit():
                raise ValueError('missing request size')
            size = int(raw_size)
            if size < 1 or size > MAX_EDIT_REQUEST_BYTES:
                raise ValueError('edit request exceeds size limit')
            if self.headers.get('Content-Type', '').split(';')[0].strip().lower() != 'application/json':
                raise ValueError('editing requires JSON')
            payload = json.loads(self.rfile.read(size).decode('utf-8'))
            arguments = validate_edit_request(payload)
        except (ValueError, TypeError, KeyError, UnicodeError, OverflowError):
            self._send(400, b'Invalid primitive edit', origin=origin)
            return
        job = bridge.enqueue_tree_page(arguments, kind='edit')
        if job is None:
            self._send(429, b'Inspector queue is busy', origin=origin)
            return
        if not job['event'].wait(3.0):
            bridge.cancel_tree_page(job)
            self._send(503, b'Game interaction paused; verify the current value before retrying', origin=origin)
            return
        status, response = job['response']
        self._send(status, response, 'application/json; charset=utf-8', origin=origin)

    def _write_edit_history(self, origin):
        # Queue a bounded undo/redo action; never inspect game state here.
        bridge = self.server.bridge
        if not self.headers.get('X-Inspector-Token') or self.headers.get('X-Inspector-Token') != bridge.token:
            self._send(401, b'Unauthorized', origin=origin)
            return
        with bridge.lock:
            if not bridge.editing_enabled:
                self._send(403, b'Primitive editing is not enabled in game config', origin=origin)
                return
        try:
            raw_size = self.headers.get('Content-Length', '')
            if not raw_size.isdigit():
                raise ValueError('missing request size')
            size = int(raw_size)
            if size < 1 or size > MAX_HISTORY_REQUEST_BYTES:
                raise ValueError('edit history request exceeds size limit')
            if self.headers.get('Content-Type', '').split(';')[0].strip().lower() != 'application/json':
                raise ValueError('edit history actions require JSON')
            payload = json.loads(self.rfile.read(size).decode('utf-8'))
            arguments = validate_edit_history_request(payload)
        except (ValueError, TypeError, KeyError, UnicodeError, OverflowError):
            self._send(400, b'Invalid edit history action', origin=origin)
            return
        job = bridge.enqueue_tree_page(arguments, kind='edit_history')
        if job is None:
            self._send(429, b'Inspector queue is busy', origin=origin)
            return
        if not job['event'].wait(3.0):
            bridge.cancel_tree_page(job)
            self._send(503, b'Game interaction paused; inspect current state before retrying', origin=origin)
            return
        status, response = job['response']
        self._send(status, response, 'application/json; charset=utf-8', origin=origin)

    def _write_variable_lock(self, origin):
        """Queue an exact-path lock action; HTTP workers never inspect Store."""
        bridge = self.server.bridge
        if not self.headers.get('X-Inspector-Token') or self.headers.get('X-Inspector-Token') != bridge.token:
            self._send(401, b'Unauthorized', origin=origin)
            return
        with bridge.lock:
            if not bridge.editing_enabled:
                self._send(403, b'Primitive editing is not enabled in game config', origin=origin)
                return
        try:
            raw_size = self.headers.get('Content-Length', '')
            if not raw_size.isdigit():
                raise ValueError('missing request size')
            size = int(raw_size)
            if size < 1 or size > MAX_VARIABLE_LOCK_REQUEST_BYTES:
                raise ValueError('variable lock request exceeds size limit')
            if self.headers.get('Content-Type', '').split(';')[0].strip().lower() != 'application/json':
                raise ValueError('variable locks require JSON')
            payload = json.loads(self.rfile.read(size).decode('utf-8'))
            arguments = validate_variable_lock_request(payload)
        except (ValueError, TypeError, KeyError, UnicodeError, OverflowError):
            self._send(400, b'Invalid variable lock request', origin=origin)
            return
        job = bridge.enqueue_tree_page(arguments, kind='lock')
        if job is None:
            self._send(429, b'Inspector queue is busy', origin=origin)
            return
        if not job['event'].wait(3.0):
            bridge.cancel_tree_page(job)
            self._send(503, b'Game interaction paused; inspect current lock state before retrying', origin=origin)
            return
        status, response = job['response']
        self._send(status, response, 'application/json; charset=utf-8', origin=origin)

    def do_PUT(self):
        """Inspector preferences OR game-config-enabled primitive writes."""
        if not self._allowed_origin():
            self._send(403)
            return
        origin = self.headers.get('Origin')
        if urlsplit(self.path).path == '/api/v1/edit':
            self._write_edit(origin)
            return
        if urlsplit(self.path).path == '/api/v1/edit-history':
            self._write_edit_history(origin)
            return
        if urlsplit(self.path).path == '/api/v1/locks':
            self._write_variable_lock(origin)
            return
        if urlsplit(self.path).path != '/api/v1/favourites':
            self._send(405, origin=origin)
            return
        bridge = self.server.bridge
        if not self.headers.get('X-Inspector-Token') or self.headers.get('X-Inspector-Token') != bridge.token:
            self._send(401, b'Unauthorized', origin=origin)
            return
        if bridge.favourites_store is None:
            self._send(503, b'No inspector save directory', origin=origin)
            return
        try:
            length_string = self.headers.get('Content-Length', '')
            if not length_string.isdigit():
                raise ValueError('missing content length')
            size = int(length_string)
            if not 1 <= size <= MAX_PREFERENCE_BYTES:
                raise ValueError('invalid preference size')
            if self.headers.get('Content-Type', '').split(';')[0].strip().lower() != 'application/json':
                raise ValueError('invalid preference type')
            payload = json.loads(self.rfile.read(size).decode('utf-8'))
            if not isinstance(payload, dict) or set(payload) != set(('version', 'favourites')) or payload['version'] != 1:
                raise ValueError('invalid preference payload')
            validated = validate_favourites(payload['favourites'])
        except (ValueError, TypeError, UnicodeError, OverflowError):
            self._send(400, b'Invalid favourites', origin=origin)
            return
        try:
            result = bridge.favourites_store.save(validated)
        except (OSError, IOError, ValueError):
            self._send(503, b'Cannot save inspector preferences', origin=origin)
            return
        self._send(200, encode_snapshot(result), 'application/json; charset=utf-8', origin=origin)

    def do_GET(self):
        if not self._allowed_origin():
            self._send(403)
            return
        origin = self.headers.get('Origin')
        path = urlsplit(self.path).path
        if path in ('/api/v1/snapshot', '/api/v1/children', '/api/v1/value',
                    '/api/v1/favourites', '/api/v1/search', '/api/v1/reveal',
                    '/api/v1/full-value', '/api/v1/scripts', '/api/v1/source',
                    '/api/v1/source-search', '/api/v1/edit-target'):
            token = self.headers.get('X-Inspector-Token')
            if not token or token != self.server.bridge.token:
                self._send(401, b'Unauthorized', origin=origin)
                return
            if path == '/api/v1/snapshot':
                with self.server.bridge.lock:
                    data = self.server.bridge.cached_bytes
                self._send(200, data, 'application/json; charset=utf-8', origin=origin)
                return
            if path == '/api/v1/favourites':
                store = self.server.bridge.favourites_store
                if store is None:
                    self._send(503, b'No inspector save directory', origin=origin)
                    return
                self._send(200, encode_snapshot(store.load()),
                           'application/json; charset=utf-8', origin=origin)
                return
            if len(self.path) > 4096:
                self._send(400, b'Invalid tree request', origin=origin)
                return
            try:
                fields = parse_qs(urlsplit(self.path).query, keep_blank_values=True)
                if path == '/api/v1/children':
                    expected_fields = ('scope', 'path', 'offset', 'size')
                elif path == '/api/v1/search':
                    expected_fields = ('scope', 'q')
                elif path == '/api/v1/scripts':
                    expected_fields = ('q', 'offset', 'size')
                elif path == '/api/v1/source':
                    expected_fields = ('file', 'line')
                elif path == '/api/v1/source-search':
                    expected_fields = ('q', 'cursor', 'size')
                else:
                    expected_fields = ('scope', 'path')
                if set(fields) != set(expected_fields):
                    raise ValueError('unexpected fields')
                if any(len(values) != 1 for values in fields.values()):
                    raise ValueError('duplicate fields')
                if path == '/api/v1/search':
                    arguments = validate_search_request(
                        fields['scope'][0], fields['q'][0])
                    job_kind = 'search'
                elif path == '/api/v1/scripts':
                    offset = int(fields['offset'][0]) if fields['offset'][0].isdigit() else -1
                    size = int(fields['size'][0]) if fields['size'][0].isdigit() else -1
                    arguments = validate_label_request(fields['q'][0], offset, size)
                    job_kind = 'scripts'
                elif path == '/api/v1/source':
                    line = int(fields['line'][0]) if fields['line'][0].isdigit() else -1
                    arguments = validate_source_request(fields['file'][0], line)
                    job_kind = 'source'
                elif path == '/api/v1/source-search':
                    size = int(fields['size'][0]) if fields['size'][0].isdigit() else -1
                    query, file_index, line_index, size = validate_source_search_request(
                        fields['q'][0], fields['cursor'][0], size)
                    arguments = (query, '{}:{}'.format(file_index, line_index), size)
                    job_kind = 'source_search'
                else:
                    raw_path = json.loads(fields['path'][0])
                if path == '/api/v1/children':
                    offset = int(fields['offset'][0]) if fields['offset'][0].isdigit() else -1
                    size = int(fields['size'][0]) if fields['size'][0].isdigit() else -1
                    arguments = validate_tree_request(fields['scope'][0], raw_path, offset, size)
                    job_kind = 'page'
                elif path in ('/api/v1/value', '/api/v1/reveal', '/api/v1/full-value', '/api/v1/edit-target'):
                    scope, path_parts, unused_offset, unused_size = validate_tree_request(
                        fields['scope'][0], raw_path, 0, 1)
                    if not path_parts:
                        raise ValueError('inspection needs a path')
                    arguments = (scope, path_parts)
                    job_kind = ('value' if path == '/api/v1/value' else
                                'reveal' if path == '/api/v1/reveal' else
                                'edit_target' if path == '/api/v1/edit-target' else 'full_value')
            except (ValueError, TypeError, KeyError):
                self._send(400, b'Invalid tree request', origin=origin)
                return
            bridge = self.server.bridge
            if job_kind == 'edit_target' and not bridge.editing_enabled:
                self._send(403, b'Editing disabled', origin=origin)
                return
            job = bridge.enqueue_tree_page(arguments, kind=job_kind)
            if job is None:
                self._send(429, b'Inspector queue is busy', origin=origin)
                return
            if not job['event'].wait(3.0):
                bridge.cancel_tree_page(job)
                self._send(503, b'Game interaction paused; retry', origin=origin)
                return
            status, response = job['response']
            self._send(status, response,
                       'application/json; charset=utf-8', origin=origin)
            return
        if path == '/':
            name = 'index.html'
        elif path.startswith('/assets/') and '..' not in path.split('/'):
            name = path[1:]
        else:
            self._send(404)
            return
        root = self.server.bridge.ui_dir
        file_path = os.path.realpath(os.path.join(root, name))
        if not file_path.startswith(os.path.realpath(root) + os.sep):
            self._send(404)
            return
        try:
            if os.path.getsize(file_path) > 4 * 1024 * 1024:
                raise IOError('asset too large')
            with open(file_path, 'rb') as f:
                data = f.read()
        except (IOError, OSError):
            self._send(404)
            return
        mime = mimetypes.guess_type(file_path)[0] or 'application/octet-stream'
        if mime.startswith('text/') or mime in ('application/javascript', 'application/json'):
            mime += '; charset=utf-8'
        self._send(200, data, mime, origin=origin)


class InspectorBridge(object):
    """Opt-in service with a per-start secret and immutable snapshot cache."""
    def __init__(self, inspector, ui_dir=None):
        self.inspector = inspector
        self.ui_dir = ui_dir or DEFAULT_UI_DIR
        self.lock = threading.RLock()
        self.server = None
        self.thread = None
        self.token = None
        self.favourites_store = None
        # Must be explicitly enabled in trusted game init code, never by HTTP.
        self.editing_enabled = False
        self.edit_history = PrimitiveEditHistory()
        self.variable_locks = VariableLocks()
        self.script_runtime = None
        self.script_game_dir = None
        self.error = ''
        self.generation = 0
        self.runtime_history = RuntimeTimeline()
        self._legacy_rollback_active = False
        self.pending_pages = []
        self.last_publish = 0.0
        # Primitive counters only. Diagnostics never retain inspected objects.
        self.queue_peak = 0
        self.queue_rejected = 0
        self.requests_completed = 0
        self.last_request_ms = None
        self.last_queue_wait_ms = None
        self.cached_bytes = encode_snapshot({'protocol': PROTOCOL, 'generation': 0, 'captured_at': None,
                                             'scopes': {'store': [], 'persistent': []},
                                             'counts': {}, 'truncated': {},
                                             'root_pages': {}, 'game': {},
                                             'capabilities': {'primitive_edits': False},
                                             'edit_history': self.edit_history.snapshot(0),
                                             'locks': self.variable_locks.snapshot(),
                                             'runtime': self.runtime_history.snapshot()})

    def configure_variable_editing(self, enabled=False):
        """Trusted game init opt-in. Never reachable through a browser API."""
        if type(enabled) is not bool:
            raise ValueError('editing opt-in must be a boolean')
        with self.lock:
            self.editing_enabled = enabled
            if not enabled:
                self.edit_history.reset('editing_disabled')
                self.variable_locks.reset('editing_disabled')
        # Advertise current capability on the next game-thread snapshot.

    def configure_game_directory(self, directory):
        """Use Ren'Py's actual game/ location, not an import cache path.

        Loading a Python package from a game archive or alternate sys.path
        can make __file__ unsuitable for discovering sibling web assets.
        """
        if directory:
            self.ui_dir = os.path.join(directory, 'renpy_inspector_web')

    def configure_favourites_directory(self, savedir):
        """Called during game init; no gameplay state is stored in preferences."""
        self.favourites_store = BrowserFavouritesStore(savedir) if savedir else None

    def configure_script_runtime(self, renpy_api, game_dir):
        """Bind trusted engine APIs and the game-owned source directory."""
        self.script_runtime = renpy_api
        self.script_game_dir = game_dir

    @property
    def running(self):
        return self.server is not None

    @property
    def url(self):
        if not self.running:
            return ''
        return 'http://{}:{}/#token={}'.format(LOOPBACK, self.server.server_port, self.token)

    def start(self):
        """Must be called from a user action, not automatically at game init."""
        if self.running:
            return
        if not os.path.isfile(os.path.join(self.ui_dir, 'index.html')):
            self.error = ('Ant Design files missing: game/renpy_inspector_web/index.html. '
                          'Extract the inner Ren\'Py 7/8 installer ZIP into the '
                          'game installation root, not into game/ or the outer CI ZIP.')
            return
        try:
            server = _Server((LOOPBACK, 0), _Handler)
            server.bridge = self
            token = binascii.hexlify(os.urandom(32))
            if not isinstance(token, str):
                token = token.decode('ascii')
            self.token = token
            self.server = server
            self.thread = threading.Thread(target=server.serve_forever,
                                           kwargs={'poll_interval': 0.1})
            self.thread.daemon = True
            self.thread.start()
            self.error = ''
            self.runtime_history = RuntimeTimeline()
            self.edit_history.reset('bridge_started')
            self.variable_locks.reset('bridge_started')
            self._legacy_rollback_active = False
            self.publish()
        except (IOError, OSError, RuntimeError) as exc:
            self.error = 'External UI unavailable: ' + type(exc).__name__
            self.stop()

    def stop(self):
        self.cancel_all_tree_pages()
        server = self.server
        self.server = None
        self.token = None
        if server is not None:
            # shutdown() blocks if serve_forever() never started.
            if self.thread is not None and self.thread.is_alive():
                server.shutdown()
            server.server_close()
        self.thread = None
        self.invalidate()

    def open_browser(self):
        """Reopen the current authenticated local browser workspace."""
        if not self.running:
            return False
        try:
            opened = webbrowser.open(self.url, new=1)
            if not opened:
                self.error = 'Could not open browser automatically; check default browser.'
                return False
            self.error = ''
            return True
        except Exception:
            self.error = 'Could not open browser automatically; check default browser.'
            return False

    def launch_or_open(self):
        """F8 entrypoint: opt-in start once, then open the existing session.

        Invoked as a Ren'Py Function action on the interaction thread.
        Keeps the existing port/token when the server is already running.
        """
        if not self.running:
            self.start()
        if not self.running:
            return False
        return self.open_browser()

    def _publish_lock_metadata(self):
        """Refresh shared lock/history metadata without rescanning Store roots."""
        with self.lock:
            try:
                data = json.loads(self.cached_bytes.decode('utf-8'))
            except (ValueError, TypeError, UnicodeError):
                data = {'protocol': PROTOCOL, 'generation': self.generation,
                        'scopes': {'store': [], 'persistent': []}}
            data['generation'] = self.generation
            data['locks'] = self.variable_locks.snapshot()
            data['edit_history'] = self.edit_history.snapshot(self.generation)
            self.cached_bytes = encode_snapshot(data)

    def _current_lock_state(self, scope, path):
        """Observe one exact path before an Inspector write or reversal."""
        target = inspect_edit_target(self.inspector._providers, scope, path)
        previous_revision = self.variable_locks.revision
        state = self.variable_locks.observe(scope, path, target, time.time())
        if self.variable_locks.revision != previous_revision:
            self._publish_lock_metadata()
        return state

    def _check_variable_locks(self):
        """Check a small rotating batch so monitoring stays within a fixed budget."""
        for scope, path in self.variable_locks.next_check_batch():
            target = inspect_edit_target(self.inspector._providers, scope, path)
            self.variable_locks.observe(scope, path, target, time.time())

    def cancel_all_tree_pages(self):
        with self.lock:
            queued, self.pending_pages = self.pending_pages, []
            for job in queued:
                job['cancelled'] = True
                job['response'] = (409, encode_snapshot({'error': 'Game state changed'}))
                job['event'].set()

    def enqueue_tree_page(self, arguments, kind='page'):
        """HTTP thread: queue primitive paths; never inspect gameplay."""
        with self.lock:
            if not self.running:
                return None
            if len(self.pending_pages) >= 8:
                self.queue_rejected += 1
                return None
            if kind not in ('page', 'value', 'full_value', 'search', 'reveal', 'scripts', 'source', 'source_search', 'edit_target', 'edit', 'edit_history', 'lock'):
                return None
            job = {'kind': kind, 'args': arguments, 'generation': self.generation,
                   'event': threading.Event(), 'response': None,
                   'cancelled': False, 'enqueued_at': monotonic_time()}
            self.pending_pages.append(job)
            self.queue_peak = max(self.queue_peak, len(self.pending_pages))
            return job

    def cancel_tree_page(self, job):
        with self.lock:
            job['cancelled'] = True
            if job in self.pending_pages:
                self.pending_pages.remove(job)

    def tick(self):
        """Ren'Py interaction thread: service at most two queued jobs per tick."""
        if not self.running:
            return
        with self.lock:
            jobs = self.pending_pages[:2]
            del self.pending_pages[:2]
        for job in jobs:
            if job['cancelled']:
                continue
            serviced_at = monotonic_time()
            try:
                with self.lock:
                    valid = job['generation'] == self.generation and self.running
                if not valid:
                    status, result = 409, {
                        'error': 'Game state changed', 'code': 'generation_changed'}
                else:
                    status = 200
                    if job['kind'] in ('edit_target', 'edit', 'edit_history', 'lock') and not self.editing_enabled:
                        status, result = 403, {'error': 'Primitive editing disabled'}
                    elif job['kind'] == 'edit_target':
                        result = inspect_edit_target(self.inspector._providers, *job['args'])
                        lock_state = self.variable_locks.observe(
                            job['args'][0], job['args'][1], result, time.time())
                        result['locked'] = lock_state['locked']
                        result['lock_stale'] = lock_state['stale']
                        result['lock_stale_reason'] = lock_state['stale_reason']
                        result['lock_revision'] = self.variable_locks.revision
                        if lock_state['stale']:
                            self._publish_lock_metadata()
                        result['captured_at'] = time.time()
                        status = 200
                    elif job['kind'] == 'edit':
                        scope, path, expected_generation, expected, typename, text = job['args']
                        if expected_generation != self.generation:
                            raise EditConflict('Game state generation changed', 'generation_changed')
                        lock_state = self._current_lock_state(scope, path)
                        if lock_state['locked']:
                            raise EditLocked(
                                'Variable is locked against inspector writes',
                                lock_state['stale'], lock_state['stale_reason'])
                        result = apply_primitive_edit(
                            self.inspector._providers, scope, path, expected, typename, text)
                        self.edit_history.record(
                            scope, path, typename, result['before'], result['after'], time.time())
                        # Invalidate stale reads and queued writes after successful mutation.
                        self.invalidate(reason='edit')
                        self.publish()
                        job['generation'] = self.generation
                        result['captured_at'] = time.time()
                        result['edit_history'] = self.edit_history.snapshot(self.generation)
                        status = 200
                    elif job['kind'] == 'edit_history':
                        action, expected_generation, entry_id = job['args']
                        if expected_generation != self.generation:
                            raise EditConflict('Game state generation changed', 'generation_changed')
                        result = self.edit_history.apply(
                            self.inspector._providers, action, entry_id,
                            self._current_lock_state)
                        self.invalidate(reason=action)
                        self.publish()
                        job['generation'] = self.generation
                        result['captured_at'] = time.time()
                        result['edit_history'] = self.edit_history.snapshot(self.generation)
                        status = 200
                    elif job['kind'] == 'lock':
                        action, scope, path, expected_generation = job['args']
                        if expected_generation != self.generation:
                            raise EditConflict('Game state generation changed', 'generation_changed')
                        target = None
                        if action in ('lock', 'refresh'):
                            target = inspect_edit_target(self.inspector._providers, scope, path)
                            self.variable_locks.observe(scope, path, target, time.time())
                            if not target.get('editable'):
                                raise EditUnsupported(
                                    'Only existing supported Store primitives can be locked or refreshed')
                        if action == 'lock':
                            changed = self.variable_locks.lock(
                                scope, path, time.time(), target['expected'], target['type'])
                        elif action == 'refresh':
                            try:
                                changed = self.variable_locks.refresh(
                                    scope, path, time.time(), target['expected'], target['type'])
                            except VariableLockMissing:
                                raise EditConflict(
                                    'No active lock exists to refresh', 'lock_missing')
                        else:
                            changed = self.variable_locks.unlock(scope, path, time.time())
                        self.publish()
                        lock_state = self.variable_locks.state(scope, path)
                        result = {
                            'protocol': 1, 'action': action,
                            'locked': lock_state['locked'],
                            'lock_stale': lock_state['stale'],
                            'lock_stale_reason': lock_state['stale_reason'],
                            'lock_revision': self.variable_locks.revision,
                            'changed': changed,
                            'locks': self.variable_locks.snapshot(),
                        }
                        if target is not None:
                            result['target'] = dict(target)
                            result['target']['generation'] = self.generation
                            result['target']['locked'] = lock_state['locked']
                            result['target']['lock_stale'] = lock_state['stale']
                            result['target']['lock_stale_reason'] = lock_state['stale_reason']
                            result['target']['lock_revision'] = self.variable_locks.revision
                        status = 200
                    elif job['kind'] == 'full_value':
                        result = build_full_value(self.inspector._providers, *job['args'])
                    elif job['kind'] == 'value':
                        result = build_tree_value(self.inspector._providers, *job['args'])
                    elif job['kind'] == 'search':
                        result = build_search_results(self.inspector._providers, *job['args'])
                    elif job['kind'] == 'reveal':
                        result = build_reveal_chain(self.inspector._providers, *job['args'])
                    elif job['kind'] == 'scripts':
                        result = list_labels(self.script_runtime, self.script_game_dir, *job['args'])
                    elif job['kind'] == 'source':
                        result = source_excerpt(self.script_game_dir, *job['args'])
                    elif job['kind'] == 'source_search':
                        result = search_source_text(self.script_game_dir, *job['args'])
                    else:
                        result = build_tree_page(self.inspector._providers, *job['args'])
                    # Timestamp when the game-thread read actually occurred.
                    # Clients use this to discard delayed overlapping samples.
                    result['captured_at'] = time.time()
            except EditLocked as reason:
                status = 423
                result = {
                    'error': 'Variable is locked against inspector writes',
                    'code': 'variable_locked',
                    'lock_stale': reason.stale,
                    'lock_stale_reason': reason.stale_reason,
                    'locks': self.variable_locks.snapshot(),
                }
                if job['kind'] == 'edit_history':
                    result['edit_history'] = self.edit_history.snapshot(self.generation)
                if job['kind'] == 'edit_history':
                    result['edit_history'] = self.edit_history.snapshot(self.generation)
            except EditConflict as reason:
                status = 409
                result = {'error': str(reason), 'code': reason.code}
                if job['kind'] == 'edit':
                    scope, path = job['args'][0], job['args'][1]
                    result['current_target'] = inspect_edit_target(
                        self.inspector._providers, scope, path)
                    lock_state = self.variable_locks.state(scope, path)
                    result['current_target'].update({
                        'generation': self.generation,
                        'locked': lock_state['locked'],
                        'lock_stale': lock_state['stale'],
                        'lock_stale_reason': lock_state['stale_reason'],
                        'lock_revision': self.variable_locks.revision,
                    })
                    result['locks'] = self.variable_locks.snapshot()
                if job['kind'] == 'edit_history':
                    result['edit_history'] = self.edit_history.snapshot(self.generation)
                if job['kind'] == 'edit_history':
                    result['edit_history'] = self.edit_history.snapshot(self.generation)
            except VariableLockLimit:
                status, result = 429, {'error': 'Variable lock capacity reached'}
            except EditUnsupported as reason:
                status, result = 422, {'error': str(reason), 'code': reason.code}
            except ValueError:
                status, result = (400 if job['kind'] in ('edit', 'lock') else 404), {
                    'error': 'Invalid edit or lock request' if job['kind'] in ('edit', 'lock') else 'Tree path unavailable'}
            except (KeyError, TypeError):
                status, result = 404, {'error': 'Tree path unavailable'}
            except Exception:
                status, result = 500, {'error': 'Read-only inspection failed'}
            with self.lock:
                if job['generation'] != self.generation:
                    status, result = 409, {
                        'error': 'Game state changed', 'code': 'generation_changed'}
                if not job['cancelled']:
                    result['generation'] = self.generation
                    try:
                        data = encode_snapshot(result)
                    except (ValueError, TypeError):
                        status, data = 413, encode_snapshot({'error': 'Page too large'})
                    job['response'] = (status, data)
                    self.requests_completed += 1
                    self.last_queue_wait_ms = round(max(
                        0.0, serviced_at - job['enqueued_at']) * 1000.0, 2)
                    self.last_request_ms = round(max(
                        0.0, monotonic_time() - serviced_at) * 1000.0, 2)
                    job['event'].set()
        if monotonic_time() - self.last_publish >= 1.5:
            self.publish()

    def invalidate(self, reason='unspecified'):
        """Invalidate caches; retain bounded, evidence-labelled callback history."""
        with self.lock:
            self.generation += 1
            if reason not in ('edit', 'undo', 'redo'):
                self.edit_history.reset(reason)
                self.variable_locks.reset(reason)
            if self.running:
                self.runtime_history.restoration(reason, self.generation, time.time())
            # Queue diagnostics reflect the current game-state epoch.
            self.queue_peak = 0
            self.queue_rejected = 0
            self.requests_completed = 0
            self.last_request_ms = None
            self.last_queue_wait_ms = None
            # The next interaction tick must capture the restored state,
            # rather than waiting for the previous 1.5-second poll deadline.
            self.last_publish = float('-inf')
            queued, self.pending_pages = self.pending_pages, []
            for job in queued:
                job['cancelled'] = True
                job['response'] = (409, encode_snapshot({'error': 'Game state changed',
                                          'generation': self.generation}))
                job['event'].set()
            self.cached_bytes = encode_snapshot({
                'protocol': PROTOCOL, 'generation': self.generation,
                'captured_at': None,
                'scopes': {'store': [], 'persistent': []},
                'counts': {}, 'truncated': {},
                'root_pages': {}, 'game': {},
                'capabilities': {'primitive_edits': self.editing_enabled},
                'edit_history': self.edit_history.snapshot(self.generation),
                'locks': self.variable_locks.snapshot(),
                'runtime': self.runtime_history.snapshot()})

    def publish(self):
        """Read game values ONLY on the Ren'Py interaction thread."""
        if not self.running:
            return
        try:
            started = monotonic_time()
            info = (self.inspector._context_info()
                    if self.inspector._context_provider else {})
            data = build_lazy_snapshot(self.inspector._providers, game_info=info)
            self._check_variable_locks()
            scan_ms = round(max(0.0, monotonic_time() - started) * 1000.0, 2)
            with self.lock:
                data['generation'] = self.generation
                data['capabilities'] = {'primitive_edits': self.editing_enabled}
                data['edit_history'] = self.edit_history.snapshot(self.generation)
                data['locks'] = self.variable_locks.snapshot()
                self.runtime_history.observe(info, self.generation, data['captured_at'])
                data['runtime'] = self.runtime_history.snapshot()
                # A snapshot of the queue, not exact real-time HTTP latency.
                # root_scan_ms excludes JSON encoding and HTTP transfer.
                data['diagnostics'] = {
                    'root_scan_ms': scan_ms,
                    'queue_pending': len(self.pending_pages),
                    'queue_peak': self.queue_peak,
                    'queue_capacity': 8,
                    'queue_rejected': self.queue_rejected,
                    'requests_completed': self.requests_completed,
                    'last_request_ms': self.last_request_ms,
                    'last_queue_wait_ms': self.last_queue_wait_ms,
                }
                self.cached_bytes = encode_snapshot(data)
            self.last_publish = monotonic_time()
            self.error = ''
        except Exception as exc:
            # An inspection error must not interrupt gameplay.
            self.invalidate()
            self.error = 'Snapshot unavailable: ' + type(exc).__name__
