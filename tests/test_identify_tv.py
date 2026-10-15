import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading
import unittest
from tools.identify_tv import identify, sanitize


class IdentificationTests(unittest.TestCase):
    def test_omits_identifiers_and_unrecognized_values(self):
        raw = {'device': {'modelName': 'QN50LS03FAFXZA', 'firmwareVersion': 'T-PTMFAKUC-0090-1301.0',
                          'developerMode': '1', 'FrameTVSupport': True, 'resolution': '3840x2160',
                          'serial': 'synthetic-serial', 'duid': 'synthetic-duid', 'wifiMac': 'synthetic-mac',
                          'ip': '192.168.1.2', 'name': 'synthetic-household', 'token': 'synthetic-token'}}
        result = sanitize(raw)
        self.assertEqual(result['model_match'], 'full_sku')
        self.assertTrue(result['developer_mode_reported'])
        self.assertEqual(result['reported_ui_resolution'], [3840, 2160])
        encoded = json.dumps(result)
        for value in ('synthetic-', '192.168.1.2', 'wifiMac', 'token'):
            self.assertNotIn(value, encoded)
        unknown = sanitize({'device': {'modelName': 'synthetic-serial', 'firmwareVersion': 'synthetic-token', 'resolution': '99999x99999'}})
        self.assertIsNone(unknown['reported_model_code'])
        self.assertIsNone(unknown['reported_software_build'])
        self.assertIsNone(unknown['reported_ui_resolution'])
        self.assertEqual(sanitize({'device': {'modelName': '50LS03F'}})['model_match'], 'family_only')

    def test_refuses_hostnames_public_addresses_and_implicit_loopback(self):
        for host in ('example.com', '8.8.8.8', '127.0.0.1', '0.0.0.0', '224.0.0.1', '192.168.1.0/24'):
            with self.assertRaises(ValueError):
                identify(host)

    def test_exact_get_only_no_redirect_and_bounded_body(self):
        observed = []
        status, body = 200, json.dumps({'device': {'modelName': '50LS03F'}}).encode()

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_): pass
            def do_GET(self):
                observed.append((self.command, self.path, self.headers.get('Authorization')))
                self.send_response(status)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Location', 'http://example.com/')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                try:
                    self.wfile.write(body)
                except (BrokenPipeError, ConnectionResetError):
                    pass

        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        worker = threading.Thread(target=server.serve_forever, daemon=True); worker.start()
        try:
            self.assertEqual(identify('127.0.0.1', port=server.server_port, allow_loopback_test=True)['model_match'], 'family_only')
            status = 302
            with self.assertRaises(ValueError):
                identify('127.0.0.1', port=server.server_port, allow_loopback_test=True)
            status, body = 200, b'x' * 65537
            with self.assertRaises(ValueError):
                identify('127.0.0.1', port=server.server_port, allow_loopback_test=True)
            self.assertEqual(observed, [('GET', '/api/v2/', None)] * 3)
        finally:
            server.shutdown(); server.server_close(); worker.join()
