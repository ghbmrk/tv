import copy
import hashlib
from http.server import ThreadingHTTPServer
import http.client
import io
import json
from pathlib import Path
import struct
import tempfile
import threading
import unittest
from unittest.mock import patch
import zipfile
import zlib

from sovereign_tv.artwork import ArtworkStore, png_info
from sovereign_tv.model import Invalid, validate
from sovereign_tv.server import handler
from sovereign_tv.store import Store


def chunk(kind, payload):
    return struct.pack('>I', len(payload)) + kind + payload + struct.pack('>I', zlib.crc32(kind + payload))


def png(width=2, height=2, raw=None):
    if raw is None:
        raw = (b'\0' + bytes((50, 120, 180)) * width) * height
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(raw)) + chunk(b'IEND', b''))


def document(digest):
    doc = json.loads(Path('examples/experience.json').read_text())
    doc.update(schema_version=2, collections=[{'id': 'artwork', 'title': 'Local artwork', 'items': [
        {'id': 'first', 'title': 'First image', 'kind': 'artwork', 'target': digest, 'visible': True}]}])
    return doc


class ArtworkTests(unittest.TestCase):
    def test_png_profile_rejects_corruption_expansion_and_active_formats(self):
        valid = png()
        self.assertEqual(png_info(valid)['width'], 2)
        for value in [b'<svg/>', valid[:-1], valid + b'junk', png(8192, 8192, b'\0'),
                      png(raw=b'x' * 100000), png(raw=b'\5' + b'x' * 6 + b'\0' + b'x' * 6),
                      valid[:33] + chunk(b'acTL', b'12345678') + valid[33:]]:
            with self.assertRaises(Invalid):
                png_info(value)
        damaged = bytearray(valid); damaged[-5] ^= 1
        with self.assertRaises(Invalid): png_info(bytes(damaged))

    def test_asset_idempotency_integrity_quota_and_undo(self):
        with tempfile.TemporaryDirectory() as directory:
            art = ArtworkStore(Path(directory) / 'art')
            data = png(); digest = hashlib.sha256(data).hexdigest()
            with self.assertRaises(Invalid): art.put('a' * 64, data)
            result = art.put(digest, data)
            self.assertEqual(result, art.put(digest, data))
            self.assertEqual(art.read(digest), data)
            initial = json.loads(Path('examples/experience.json').read_text())
            store = Store(Path(directory) / 'db', initial, art)
            edit = {'request_id': 'art-import', 'base_revision': 1, 'experience': document(digest)}
            self.assertFalse(store.preview(edit)['applied'])
            self.assertIn('collections', store.preview(edit)['changed_fields'])
            self.assertEqual(store.state()['experience'], initial)
            store.apply(edit)
            self.assertEqual(Store(Path(directory) / 'db', initial, art).state()['experience'], document(digest))
            store.apply({'request_id': 'undo-art', 'base_revision': 2, 'restore_revision': 1}, undo=True)
            self.assertEqual(store.state()['experience'], initial)
            self.assertEqual(art.read(digest), data)  # Undo never destroys reusable artwork.
            missing = document('0' * 64)
            with self.assertRaises(Invalid): store.apply({'request_id': 'missing', 'base_revision': 3, 'experience': missing})
            with patch('sovereign_tv.artwork.MAX_STORE_BYTES', 1):
                self.assertEqual(art.put(digest, data)['id'], digest)
                other = png(1, 1)
                with self.assertRaises(Invalid): art.put(hashlib.sha256(other).hexdigest(), other)
            art.path(digest).write_bytes(b'corrupt')
            with self.assertRaises(Invalid): art.read(digest)

    def test_collection_reference_kind_and_bounds_validation(self):
        doc = document('a' * 64)
        self.assertEqual(validate(doc), doc)
        candidates = []
        for key, value in [('kind', 'collection'), ('target', '../../file'), ('visible', 1)]:
            candidate = copy.deepcopy(doc); candidate['collections'][0]['items'][0][key] = value; candidates.append(candidate)
        candidate = copy.deepcopy(doc); candidate['collections'] = []; candidates.append(candidate)
        candidate = copy.deepcopy(doc); candidate['collections'] *= 2; candidates.append(candidate)
        for candidate in candidates:
            with self.assertRaises(Invalid): validate(candidate)

    def test_http_asset_authority_preview_and_portable_export(self):
        with tempfile.TemporaryDirectory() as directory:
            art = ArtworkStore(Path(directory) / 'art')
            initial = json.loads(Path('examples/experience.json').read_text())
            store = Store(Path(directory) / 'db', initial, art)
            server = ThreadingHTTPServer(('127.0.0.1', 0), handler(store, 'synthetic-test-token'))
            worker = threading.Thread(target=server.serve_forever, daemon=True); worker.start()

            def request(method, path, body=None, auth=True, mime='image/png'):
                conn = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=5)
                headers = {'Content-Type': mime}
                if auth: headers['Authorization'] = 'Bearer synthetic-test-token'
                try:
                    conn.request(method, path, body, headers)
                    r = conn.getresponse(); return r.status, r.read()
                finally: conn.close()
            try:
                data = png(); digest = hashlib.sha256(data).hexdigest(); path = '/api/assets/' + digest
                self.assertEqual(request('PUT', path, data, auth=False)[0], 401)
                self.assertEqual(request('PUT', path, data, mime='text/html')[0], 415)
                self.assertEqual(request('PUT', path, b'<svg/>')[0], 400)
                self.assertEqual(request('PUT', path, data)[0], 200)
                self.assertEqual(request('GET', path)[1], data)
                self.assertEqual(request('GET', path, auth=False)[0], 401)
                self.assertEqual(request('GET', '/api/assets/../../anything')[0], 404)
                store.apply({'request_id': 'apply', 'base_revision': 1, 'experience': document(digest)})
                code, bundle = request('GET', '/api/export')
                self.assertEqual(code, 200)
                with zipfile.ZipFile(io.BytesIO(bundle)) as archive:
                    self.assertEqual(set(archive.namelist()), {'experience.json', 'artwork/' + digest + '.png'})
                    self.assertEqual(json.loads(archive.read('experience.json')), store.state()['experience'])
                    self.assertEqual(archive.read('artwork/' + digest + '.png'), data)
            finally:
                server.shutdown(); server.server_close(); worker.join()


if __name__ == '__main__': unittest.main()
