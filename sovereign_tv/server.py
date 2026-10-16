"""Loopback-only development API. Not the authenticated LAN/device executor."""
import argparse
import hmac
import json
import os
from pathlib import Path
import secrets
import io
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from .model import Invalid, artwork_refs, canonical
from .store import Conflict, Store
from .artwork import MAX_IMAGE_BYTES, ArtworkStore

ROOT = Path(__file__).resolve().parent.parent
MAX_BODY = 65536


def handler(store, token):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass  # No request bodies, credentials, or viewing data in logs.

        def send(self, status, value, content_type='application/json'):
            data = canonical(value).encode() if content_type == 'application/json' else value
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Security-Policy', "default-src 'self'; img-src 'self' blob:; script-src 'self'; style-src 'self'; frame-ancestors 'none'; base-uri 'none'")
            self.end_headers()
            self.wfile.write(data)

        def boundary(self):
            expected = '127.0.0.1:' + str(self.server.server_port)
            if self.headers.get('Host') != expected:
                self.send(403, {'error': 'use the exact loopback address'})
                return False
            origin = self.headers.get('Origin')
            if origin and origin != 'http://' + expected:
                self.send(403, {'error': 'foreign origin refused'})
                return False
            if self.path.startswith('/api/') and not hmac.compare_digest(self.headers.get('Authorization', ''), 'Bearer ' + token):
                self.send(401, {'error': 'local development token required'})
                return False
            return True

        def do_GET(self):
            if not self.boundary():
                return
            if self.path == '/api/state':
                return self.send(200, store.state())
            if self.path == '/api/export':
                try:
                    state = store.state()
                    store.check_assets(state['experience'])
                    output = io.BytesIO()
                    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_STORED) as bundle:
                        bundle.writestr('experience.json', canonical(state['experience']))
                        for digest in sorted(artwork_refs(state['experience'])):
                            bundle.writestr('artwork/' + digest + '.png', store.artwork.read(digest))
                    return self.send(200, output.getvalue(), 'application/zip')
                except (ValueError, OSError):
                    return self.send(409, {'error': 'saved artwork unavailable; export refused'})
            if self.path.startswith('/api/assets/'):
                try:
                    if store.artwork is None:
                        raise Invalid('artwork store unavailable')
                    return self.send(200, store.artwork.read(self.path[len('/api/assets/'):]), 'image/png')
                except (ValueError, OSError):
                    return self.send(404, {'error': 'artwork unavailable'})
            if self.path == '/api/capabilities':
                return self.send(200, {'api_version': 1, 'mode': 'loopback-development',
                    'operations': ['state', 'preview', 'apply', 'undo', 'receipt', 'asset-put', 'asset-get', 'export'],
                    'experience_schema_versions': [1, 2, 3], 'manual_movie_curation': True, 'home_autoplay': False, 'movie_playback_qualified': False, 'hardware_control': False, 'agentos_qualified': False})
            if self.path.startswith('/api/receipts/'):
                result = store.receipt(self.path[len('/api/receipts/'):])
                return self.send(200 if result else 404, result or {'error': 'unknown request'})
            static = {'/': ('index.html', 'text/html; charset=utf-8'),
                      '/app.js': ('app.js', 'application/javascript'), '/style.css': ('style.css', 'text/css')}
            static['/storybook.js'] = ('storybook.js', 'application/javascript')
            static.update({'/preview': ('preview.html','text/html; charset=utf-8'), '/preview.js':('preview.js','application/javascript'), '/preview.css':('preview.css','text/css')})
            if self.path == '/storybook-default.json':
                return self.send(200, json.loads((ROOT / 'examples/storybook.json').read_text()))
            if self.path in ('/storybook/background.png', '/storybook/posters.png'):
                name = self.path.rsplit('/', 1)[1]
                return self.send(200, (ROOT / 'android/app/src/main/assets/storybook' / name).read_bytes(), 'image/png')
            if self.path in static:
                name, mime = static[self.path]
                return self.send(200, (ROOT / 'web' / name).read_bytes(), mime)
            self.send(404, {'error': 'not found'})

        def do_PUT(self):
            if not self.boundary():
                return
            if not self.path.startswith('/api/assets/') or store.artwork is None:
                return self.send(404, {'error': 'not found'})
            try:
                if self.headers.get('Content-Type') != 'image/png':
                    return self.send(415, {'error': 'image/png required'})
                if self.headers.get('Transfer-Encoding'):
                    raise Invalid('transfer encoding unsupported')
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 < size <= MAX_IMAGE_BYTES:
                    return self.send(413, {'error': 'PNG must be 1–8388608 bytes'})
                self.connection.settimeout(10)
                data = self.rfile.read(size)
                if len(data) != size:
                    raise Invalid('incomplete upload')
                return self.send(200, store.artwork.put(self.path[len('/api/assets/'):], data))
            except (ValueError, OSError):
                return self.send(400, {'error': 'invalid PNG, asset ID or storage capacity'})

        def do_POST(self):
            if not self.boundary():
                return
            if self.path not in ('/api/preview', '/api/apply', '/api/undo'):
                return self.send(404, {'error': 'not found'})
            try:
                if self.headers.get('Content-Type') != 'application/json':
                    return self.send(415, {'error': 'application/json required'})
                if self.headers.get('Transfer-Encoding'):
                    raise Invalid('transfer encoding unsupported')
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 < size <= MAX_BODY:
                    return self.send(413, {'error': 'body must be 1–65536 bytes'})
                request = json.loads(self.rfile.read(size), parse_constant=lambda _: (_ for _ in ()).throw(Invalid('non-finite number')))
                result = store.preview(request) if self.path == '/api/preview' else store.apply(request, undo=self.path == '/api/undo')
                self.send(200, result)
            except Conflict as error:
                self.send(409, {'error': str(error)})
            except (ValueError, TypeError, KeyError, RecursionError):
                self.send(400, {'error': 'invalid request or experience document'})
    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', type=Path, default=Path('.local'))
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    args.data.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(args.data, 0o700)
    token_path = args.data / 'development-token'
    if not token_path.exists():
        fd = os.open(token_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w') as stream:
            stream.write(secrets.token_urlsafe(32))
    os.chmod(token_path, 0o600)
    store = Store(args.data / 'experience.sqlite3', json.loads((ROOT / 'examples/storybook.json').read_text()), ArtworkStore(args.data / 'artwork'))
    server = ThreadingHTTPServer(('127.0.0.1', args.port), handler(store, token_path.read_text().strip()))
    print(f'Preview: http://127.0.0.1:{server.server_port}\nLocal development token file: {token_path} (paste into preview; never publish it)', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
