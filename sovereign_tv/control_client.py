"""Owner/executor-only pinned TLS client. Never a guest tool or an automatic effect retry loop."""
import argparse
import hashlib
import ipaddress
import json
import os
import re
from pathlib import Path
import socket
import ssl
import stat
import struct
import subprocess
import time

MAX_METADATA = 512 * 1024
MAX_ASSET = 8 * 1024 * 1024
EFFECTS = {'apply', 'undo', 'restore_default', 'artwork.put'}
OPERATIONS = EFFECTS | {'capabilities', 'state', 'apps.list', 'preview', 'receipt', 'artwork.open'}


class Unavailable(RuntimeError):
    pass


class Unconfirmed(RuntimeError):
    pass


def identity(directory):
    """Create an offline client identity; refuse to replace existing material."""
    directory = Path(directory)
    directory.mkdir(mode=0o700)
    key = directory / 'client-key.pem'
    certificate = directory / 'client-public.pem'
    key.touch(mode=0o600, exist_ok=False)
    result = subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-sha256',
                             '-days', '365', '-subj', '/CN=Sovereign household executor',
                             '-addext', 'keyUsage=digitalSignature', '-addext', 'extendedKeyUsage=clientAuth',
                             '-keyout', str(key), '-out', str(certificate)], capture_output=True)
    if result.returncode:
        raise Unavailable('Offline identity generation failed; no existing identity was replaced')
    key.chmod(0o600)
    return certificate


def public_certificate(path):
    with open(path, 'rb') as stream:
        data = stream.read(16385)
    if not 1 <= len(data) <= 16384:
        raise ValueError('One bounded public certificate required')
    pem = data.decode('ascii').strip()
    if not re.fullmatch(r'-----BEGIN CERTIFICATE-----\s+[A-Za-z0-9+/=\s]+\s+-----END CERTIFICATE-----', pem):
        raise ValueError('One public PEM certificate required')
    return pem, hashlib.sha256(ssl.PEM_cert_to_DER_cert(pem)).hexdigest()


def certificate_pin(path):
    return public_certificate(path)[1]


class Client:
    def __init__(self, address, port, device_certificate, client_certificate, client_key, *, allow_loopback=False):
        if not ssl.OPENSSL_VERSION.startswith('OpenSSL ') or ssl.OPENSSL_VERSION_INFO < (3, 0):
            raise Unavailable('Local control requires Python linked to OpenSSL 3 or later')
        address = ipaddress.IPv4Address(address)
        private = any(address in ipaddress.IPv4Network(cidr) for cidr in ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16'))
        if not private and not (allow_loopback and address.is_loopback):
            raise ValueError('An explicit private IPv4 endpoint is required')
        if type(port) is not int or not 1 <= port <= 65535:
            raise ValueError('Invalid endpoint port')
        info = Path(client_key).lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077 or info.st_uid != os.getuid():
            raise ValueError('Client key must be a private regular file owned by this user')
        self.address, self.port = str(address), port
        device_pem, self.device_id = public_certificate(device_certificate)
        self.context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        self.context.check_hostname = False  # Exact certificate identity, independent of a changing LAN address.
        self.context.minimum_version = ssl.TLSVersion.TLSv1_2
        self.context.load_verify_locations(cadata=device_pem)  # No public/system CA store.
        self.context.load_cert_chain(certfile=str(client_certificate), keyfile=str(client_key))

    @classmethod
    def from_profile(cls, path, *, allow_loopback=False):
        path = Path(path)
        config = json.loads(path.read_text())
        if set(config) != {'address', 'port', 'device_certificate', 'client_certificate', 'client_key'}:
            raise ValueError('Unexpected or missing profile fields')
        for field in ('device_certificate', 'client_certificate', 'client_key'):
            config[field] = path.parent / config[field]
        return cls(**config, allow_loopback=allow_loopback)

    @staticmethod
    def _remaining(connection, deadline):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError('Bounded connection deadline elapsed')
        connection.settimeout(remaining)

    @classmethod
    def _read(cls, connection, maximum, deadline):
        def exact(count):
            result = bytearray()
            while len(result) < count:
                cls._remaining(connection, deadline)
                block = connection.recv(count - len(result))
                if not block:
                    raise EOFError('Incomplete response')
                result.extend(block)
            return bytes(result)
        size, = struct.unpack('!I', exact(4))
        if not 1 <= size <= maximum:
            raise ValueError('Response frame bound exceeded')
        return exact(size)

    @classmethod
    def _write(cls, connection, value, deadline):
        cls._remaining(connection, deadline)
        connection.sendall(struct.pack('!I', len(value)) + value)

    def request(self, operation, arguments=None, *, expires_at_ms, asset=None):
        if operation not in OPERATIONS or type(expires_at_ms) is not int:
            raise ValueError('Declared operation and integer expiry required')
        arguments = {} if arguments is None else dict(arguments)
        if set(arguments) & {'v', 'device_id', 'operation', 'expires_at_ms'}:
            raise ValueError('Arguments cannot override the pinned request envelope')
        if operation in {'apply', 'undo', 'restore_default'} and not arguments.get('request_id'):
            raise ValueError('A stable caller-supplied request ID is required')
        body = dict(arguments, v=1, device_id=self.device_id, operation=operation, expires_at_ms=expires_at_ms)
        encoded = json.dumps(body, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode('utf-8')
        if not 1 <= len(encoded) <= MAX_METADATA:
            raise ValueError('Request metadata exceeds its bound')
        if operation == 'artwork.put':
            if not isinstance(asset, bytes) or not 1 <= len(asset) <= MAX_ASSET or arguments.get('bytes') != len(asset) or arguments.get('sha256') != hashlib.sha256(asset).hexdigest():
                raise ValueError('Bounded asset and exact digest required')
        elif asset is not None:
            raise ValueError('Only artwork.put accepts upload bytes')
        attempted = False
        try:
            with socket.create_connection((self.address, self.port), timeout=5) as raw:
                with self.context.wrap_socket(raw) as connection:
                    if hashlib.sha256(connection.getpeercert(binary_form=True)).hexdigest() != self.device_id:
                        raise ValueError('Device identity changed')
                    deadline = time.monotonic() + 40
                    attempted = True
                    self._write(connection, encoded, deadline)
                    if asset is not None:
                        self._write(connection, asset, deadline)
                    response = json.loads(self._read(connection, MAX_METADATA, deadline))
                    if not isinstance(response, dict) or type(response.get('v')) is not int or response['v'] != 1 or response.get('device_id') != self.device_id or not isinstance(response.get('status'), str):
                        raise ValueError('Invalid or cross-device response')
                    image = None
                    if 'blob_bytes' in response:
                        if operation != 'artwork.open' or response['status'] != 'ok':
                            raise ValueError('Unexpected binary content')
                        image = self._read(connection, MAX_ASSET, deadline)
                        if type(response['blob_bytes']) is not int or len(image) != response['blob_bytes'] or hashlib.sha256(image).hexdigest() != arguments['sha256']:
                            raise ValueError('Asset response integrity mismatch')
                    return response, image
        except (OSError, EOFError, ValueError) as error:
            if attempted and operation in EFFECTS:
                raise Unconfirmed('Effect unconfirmed; reconcile the original request ID or exact asset hash') from error
            raise Unavailable('Pinned local connection unavailable; no automatic retry performed') from error


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    create = sub.add_parser('identity'); create.add_argument('directory')
    send = sub.add_parser('request'); send.add_argument('profile'); send.add_argument('request_json')
    send.add_argument('--upload'); send.add_argument('--asset-output')
    args = parser.parse_args()
    if args.command == 'identity':
        certificate = identity(args.directory)
        print(json.dumps({'public_certificate': str(certificate), 'sha256': certificate_pin(certificate)}))
        return
    request = json.loads(Path(args.request_json).read_text())
    operation = request.pop('operation'); expiry = request.pop('expires_at_ms')
    asset = None
    if args.upload:
        with open(args.upload, 'rb') as stream:
            asset = stream.read(MAX_ASSET + 1)
    response, image = Client.from_profile(args.profile).request(operation, request, expires_at_ms=expiry, asset=asset)
    if image is not None:
        if not args.asset_output:
            raise ValueError('Explicit private output path required for image content')
        fd = os.open(args.asset_output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(image)
    print(json.dumps(response, ensure_ascii=False))


if __name__ == '__main__':
    main()
