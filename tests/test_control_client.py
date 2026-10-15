import hashlib
import json
import os
from pathlib import Path
import socket
import ssl
import struct
import subprocess
import tempfile
import threading
import time
import unittest
from sovereign_tv.control_client import Client, Unavailable, Unconfirmed, identity, MAX_METADATA


class ControlClientTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not ssl.OPENSSL_VERSION.startswith('OpenSSL ') or ssl.OPENSSL_VERSION_INFO < (3, 0):
            raise unittest.SkipTest('Mutual TLS qualification requires the supported OpenSSL 3 runtime')
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        cls.client_cert = identity(cls.root / 'executor')
        cls.client_key = cls.root / 'executor/client-key.pem'
        cls.server_cert = cls.root / 'device.pem'
        cls.server_key = cls.root / 'device-key.pem'
        cls.other_cert = cls.root / 'other.pem'
        cls.other_key = cls.root / 'other-key.pem'
        for certificate, key in ((cls.server_cert, cls.server_key), (cls.other_cert, cls.other_key)):
            key.touch(mode=0o600)
            subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-sha256', '-days', '1',
                            '-subj', '/CN=Synthetic TV test', '-addext', 'extendedKeyUsage=serverAuth',
                            '-keyout', str(key), '-out', str(certificate)], check=True, capture_output=True)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def endpoint(self, handler, *, wrong_device=False):
        listener = socket.socket(); listener.bind(('127.0.0.1', 0)); listener.listen(1); listener.settimeout(5)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.load_cert_chain(str(self.other_cert if wrong_device else self.server_cert), str(self.other_key if wrong_device else self.server_key))
        context.verify_mode = ssl.CERT_REQUIRED; context.load_verify_locations(cafile=str(self.client_cert))
        calls = []
        def serve():
            try:
                raw, _ = listener.accept()
                with raw, context.wrap_socket(raw, server_side=True) as connection:
                    deadline = time.monotonic() + 5
                    request = json.loads(Client._read(connection, MAX_METADATA, deadline))
                    calls.append(request)
                    handler(connection, request, deadline)
            except (OSError, EOFError, ValueError):
                pass
            finally:
                listener.close()
        thread = threading.Thread(target=serve, daemon=True); thread.start()
        self.addCleanup(lambda: thread.join(6))
        client = Client('127.0.0.1', listener.getsockname()[1], self.server_cert, self.client_cert, self.client_key, allow_loopback=True)
        return client, calls

    @staticmethod
    def response(connection, request, deadline, **extra):
        body = dict(v=1, device_id=request['device_id'], status='ok', **extra)
        Client._write(connection, json.dumps(body).encode(), deadline)

    def test_pinned_mutual_tls_reads_without_changing_the_request_envelope(self):
        client, calls = self.endpoint(lambda c, r, d: self.response(c, r, d, result={'revision': 7}))
        expiry = int(time.time() * 1000) + 10000
        response, image = client.request('state', expires_at_ms=expiry)
        self.assertEqual(response['result']['revision'], 7); self.assertIsNone(image)
        self.assertEqual(calls[0]['expires_at_ms'], expiry)
        self.assertEqual(calls[0]['device_id'], client.device_id)

    def test_lost_effect_reply_is_unconfirmed_and_never_automatically_replayed(self):
        client, calls = self.endpoint(lambda c, r, d: None)
        with self.assertRaises(Unconfirmed):
            client.request('apply', {'request_id': 'stable-attempt', 'base_revision': 7, 'document': '{}'}, expires_at_ms=int(time.time() * 1000) + 10000)
        self.assertEqual(len(calls), 1); self.assertEqual(calls[0]['request_id'], 'stable-attempt')

    def test_changed_device_identity_fails_before_application_data(self):
        client, calls = self.endpoint(lambda c, r, d: self.fail('Wrong device received application data'), wrong_device=True)
        with self.assertRaises(Unavailable):
            client.request('state', expires_at_ms=int(time.time() * 1000) + 10000)
        self.assertEqual(calls, [])

    def test_asset_integrity_and_frame_bounds_are_checked_before_returning_content(self):
        image = b'synthetic asset'; digest = hashlib.sha256(image).hexdigest()
        def serve(connection, request, deadline):
            self.response(connection, request, deadline, blob_bytes=len(image), result={'sha256': digest})
            Client._write(connection, image, deadline)
        client, _ = self.endpoint(serve)
        _, returned = client.request('artwork.open', {'sha256': digest}, expires_at_ms=int(time.time() * 1000) + 10000)
        self.assertEqual(returned, image)
        client, _ = self.endpoint(lambda c, r, d: c.sendall(struct.pack('!I', MAX_METADATA + 1)))
        with self.assertRaises(Unavailable):
            client.request('state', expires_at_ms=int(time.time() * 1000) + 10000)

    def test_local_key_and_endpoint_authority_are_required(self):
        with self.assertRaises(FileExistsError):
            identity(self.root / 'executor')
        for address in ('example.com', '8.8.8.8', '127.0.0.1', '169.254.1.1'):
            with self.assertRaises(ValueError):
                Client(address, 9443, self.server_cert, self.client_cert, self.client_key)
        mode = self.client_key.stat().st_mode
        try:
            self.client_key.chmod(0o644)
            with self.assertRaises(ValueError):
                Client('192.168.1.2', 9443, self.server_cert, self.client_cert, self.client_key)
        finally:
            self.client_key.chmod(mode)
