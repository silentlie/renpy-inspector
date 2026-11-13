"""Opt-in, authenticated loopback bridge for the Ant Design inspector UI.

HTTP workers never read gameplay objects. Game state is inspected only by
Ren'Py's interaction-thread tick/publish. The only preference write permitted
is an authenticated, bounded inspector-only JSON file, never game state.
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
                '/api/v1/source-search') and origin in ALLOWED_DEV_ORIGINS:
            self._send(204, origin=origin)
        else:
            self._send(404)

    def do_POST(self):
        self._send(405)

    def do_PUT(self):
        """The ONLY HTTP write is to inspector-owned favourites metadata."""
        if not self._allowed_origin():
            self._send(403)
            return
        origin = self.headers.get('Origin')
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
                    '/api/v1/source-search'):
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
                elif path in ('/api/v1/value', '/api/v1/reveal', '/api/v1/full-value'):
                    scope, path_parts, unused_offset, unused_size = validate_tree_request(
                        fields['scope'][0], raw_path, 0, 1)
                    if not path_parts:
                        raise ValueError('inspection needs a path')
                    arguments = (scope, path_parts)
                    job_kind = ('value' if path == '/api/v1/value' else
                                'reveal' if path == '/api/v1/reveal' else 'full_value')
            except (ValueError, TypeError, KeyError):
                self._send(400, b'Invalid tree request', origin=origin)
                return
            bridge = self.server.bridge
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
        self.script_runtime = None
        self.script_game_dir = None
        self.error = ''
        self.generation = 0
        self.runtime_history = RuntimeTimeline()
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
                                             'runtime': self.runtime_history.snapshot()})

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
            if kind not in ('page', 'value', 'full_value', 'search', 'reveal', 'scripts', 'source', 'source_search'):
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
        """Ren'Py interaction thread: at most two page jobs per 250ms tick."""
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
                    status, result = 409, {'error': 'Game state changed'}
                else:
                    if job['kind'] == 'full_value':
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
                    status = 200
            except (ValueError, KeyError, TypeError):
                status, result = 404, {'error': 'Tree path unavailable'}
            except Exception:
                status, result = 500, {'error': 'Read-only inspection failed'}
            with self.lock:
                if job['generation'] != self.generation:
                    status, result = 409, {'error': 'Game state changed'}
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
            scan_ms = round(max(0.0, monotonic_time() - started) * 1000.0, 2)
            with self.lock:
                data['generation'] = self.generation
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
