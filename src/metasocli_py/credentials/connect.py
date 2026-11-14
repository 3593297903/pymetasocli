import secrets
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs

from ..domain.errors import AppError
from .config import save_credential


def form_server(provider: str, ttl: float = 600) -> tuple[HTTPServer, str, dict]:
    token = secrets.token_urlsafe(32)
    state = {'saved': False, 'expires': time.monotonic() + ttl}
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def respond(self, status: int, body: bytes):
            self.send_response(status)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Security-Policy', "default-src 'none'; form-action 'self'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(body)

        def valid(self):
            host = f'127.0.0.1:{server.server_port}'
            return self.path == '/' + token and self.headers.get('Host') == host and time.monotonic() < state['expires'] and not state['saved']

        def do_GET(self):
            if not self.valid():
                self.respond(403, b'Expired or invalid setup request.')
                return
            self.respond(200, b'<meta charset="utf-8"><title>metasocli-py credentials</title><form method="post"><label>API key <input name="key" type="password" autocomplete="off" required maxlength="4096"></label><button>Save encrypted credential</button></form>')

        def do_POST(self):
            if not self.valid() or self.headers.get('Origin') != f'http://127.0.0.1:{server.server_port}' or self.headers.get('Content-Type', '').split(';')[0] != 'application/x-www-form-urlencoded':
                # Drain only a bounded small body before closing, avoiding a TCP
                # reset that can discard the rejection response on Windows.
                length = self.headers.get('Content-Length', '')
                if length.isdigit() and 0 < int(length) <= 16384:
                    self.connection.settimeout(1)
                    try:
                        self.rfile.read(int(length))
                    except OSError:
                        pass
                self.respond(403, b'Invalid setup origin.')
                return
            length = self.headers.get('Content-Length', '')
            if not length.isdigit() or not 0 < int(length) <= 16384:
                self.respond(413, b'Invalid request size.')
                return
            try:
                self.connection.settimeout(5)
                raw = self.rfile.read(int(length))
                if len(raw) != int(length):
                    raise ValueError
                fields = parse_qs(raw.decode('utf-8'), strict_parsing=True)
                if set(fields) != {'key'} or len(fields['key']) != 1:
                    raise ValueError
                save_credential(provider, fields['key'][0])
                state['saved'] = True
                self.respond(200, b'Encrypted credential saved and verified. No remote request was made.')
            except (AppError, ValueError, OSError):
                self.respond(400, b'Credential could not be saved. Previous value preserved.')
    server = HTTPServer(('127.0.0.1', 0), Handler)
    server.timeout = .5
    return server, f'http://127.0.0.1:{server.server_port}/{token}', state


def connect(provider: str) -> dict:
    import json
    server, url, state = form_server(provider)
    print(json.dumps({'setupUrl': url, 'expiresSeconds': 600}), flush=True)
    try:
        while not state['saved'] and time.monotonic() < state['expires']:
            server.handle_request()
    finally:
        server.server_close()
    return {'configured': state['saved'], 'remoteAuthentication': 'not-tested', 'generation': 'not-tested'}
