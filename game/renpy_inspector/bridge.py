"""Opt-in, authenticated loopback bridge for the Ant Design inspector UI.

The HTTP thread ONLY serves pre-serialized bytes. Game state is inspected by
publish(), which must be called by the Ren'Py interaction thread. The bridge
has no write/eval endpoints and never connects to a remote host.
"""
from __future__ import unicode_literals

import binascii
import mimetypes
import os
import threading
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

from .bridge_snapshot import PROTOCOL, build_snapshot, encode_snapshot
from .bridge_paging import build_tree_page, validate_tree_request
from .compat import monotonic_time

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
            self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
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
        if urlsplit(self.path).path in ('/api/v1/snapshot', '/api/v1/children') and origin in ALLOWED_DEV_ORIGINS:
            self._send(204, origin=origin)
        else:
            self._send(404)

    def do_POST(self):
        self._send(405)

    def do_GET(self):
        if not self._allowed_origin():
            self._send(403)
            return
        origin = self.headers.get('Origin')
        path = urlsplit(self.path).path
        if path in ('/api/v1/snapshot', '/api/v1/children'):
            token = self.headers.get('X-Inspector-Token')
            if not token or token != self.server.bridge.token:
                self._send(401, b'Unauthorized', origin=origin)
                return
            if path == '/api/v1/snapshot':
                with self.server.bridge.lock:
                    data = self.server.bridge.cached_bytes
                self._send(200, data, 'application/json; charset=utf-8', origin=origin)
                return
            if len(self.path) > 4096:
                self._send(400, b'Invalid tree request', origin=origin)
                return
            try:
                fields = parse_qs(urlsplit(self.path).query, keep_blank_values=True)
                if set(fields) != set(('scope', 'path', 'offset', 'size')):
                    raise ValueError('unexpected fields')
                if any(len(values) != 1 for values in fields.values()):
                    raise ValueError('duplicate fields')
                raw_path = json.loads(fields['path'][0])
                offset = int(fields['offset'][0]) if fields['offset'][0].isdigit() else -1
                size = int(fields['size'][0]) if fields['size'][0].isdigit() else -1
                arguments = validate_tree_request(fields['scope'][0], raw_path, offset, size)
            except (ValueError, TypeError, KeyError):
                self._send(400, b'Invalid tree request', origin=origin)
                return
            bridge = self.server.bridge
            job = bridge.enqueue_tree_page(arguments)
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
        self.error = ''
        self.generation = 0
        self.pending_pages = []
        self.last_publish = 0.0
        self.cached_bytes = encode_snapshot({'protocol': PROTOCOL, 'generation': 0, 'captured_at': None,
                                             'scopes': {'store': [], 'persistent': []},
                                             'counts': {}, 'truncated': {}, 'game': {}})

    def configure_game_directory(self, directory):
        """Use Ren'Py's actual game/ location, not an import cache path.

        Loading a Python package from a game archive or alternate sys.path
        can make __file__ unsuitable for discovering sibling web assets.
        """
        if directory:
            self.ui_dir = os.path.join(directory, 'renpy_inspector_web')

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

    def enqueue_tree_page(self, arguments):
        """HTTP thread: store primitive values only, never inspect gameplay."""
        with self.lock:
            if not self.running or len(self.pending_pages) >= 8:
                return None
            job = {'args': arguments, 'generation': self.generation,
                   'event': threading.Event(), 'response': None,
                   'cancelled': False}
            self.pending_pages.append(job)
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
            try:
                with self.lock:
                    valid = job['generation'] == self.generation and self.running
                if not valid:
                    status, result = 409, {'error': 'Game state changed'}
                else:
                    result = build_tree_page(self.inspector._providers, *job['args'])
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
                    job['event'].set()
        if monotonic_time() - self.last_publish >= 1.5:
            self.publish()

    def invalidate(self):
        """Discard pages and old snapshots after save-load or session reset."""
        with self.lock:
            self.generation += 1
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
                'counts': {}, 'truncated': {}, 'game': {}})

    def publish(self):
        """Read game values ONLY on the Ren'Py interaction thread."""
        if not self.running:
            return
        try:
            info = (self.inspector._context_info()
                    if self.inspector._context_provider else {})
            data = build_snapshot(self.inspector._providers, game_info=info)
            with self.lock:
                data['generation'] = self.generation
                self.cached_bytes = encode_snapshot(data)
            self.last_publish = monotonic_time()
            self.error = ''
        except Exception as exc:
            # An inspection error must not interrupt gameplay.
            self.invalidate()
            self.error = 'Snapshot unavailable: ' + type(exc).__name__
