#!/usr/bin/env python3
"""Synthetic emulator-only Android/Python mutual TLS qualification. Never install on a real TV."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import ssl
import sys
import tempfile
import time
import uuid

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from sovereign_tv.control_client import Client, identity  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--adb', default='adb')
    parser.add_argument('--serial', required=True)
    args = parser.parse_args()
    command = [args.adb, '-s', args.serial]
    def adb(*parts, input=None, check=True):
        return subprocess.run(command + list(parts), input=input, check=check, capture_output=True, timeout=20)
    if adb('shell', 'getprop', 'ro.kernel.qemu').stdout.strip() != b'1':
        raise RuntimeError('Refused: an Android emulator is required')
    artifacts = ['app/build/outputs/apk/debug/app-debug.apk', 'control/build/outputs/apk/debug/control-debug.apk',
                 'control/build/outputs/apk/androidTest/debug/control-debug-androidTest.apk']
    for path in artifacts:
        adb('install', '-r', '-t', str(ROOT / 'android' / path))
    adb('shell', 'run-as', 'local.sovereigntv.control', 'mkdir', '-p', 'files')
    adb('shell', 'run-as', 'local.sovereigntv.control', 'rm', '-f', 'files/interop-ready.json', 'files/interop-done')
    port = None; process = None
    with tempfile.TemporaryDirectory(prefix='sovereign-control-interop-') as temporary:
        directory = Path(temporary)
        certificate = identity(directory / 'executor')
        adb('shell', '-T', 'run-as', 'local.sovereigntv.control', 'dd', 'of=files/interop-client-public.pem', input=certificate.read_bytes())
        transferred = adb('exec-out', 'run-as', 'local.sovereigntv.control', 'cat', 'files/interop-client-public.pem').stdout
        if transferred != certificate.read_bytes():
            raise RuntimeError('Public certificate fixture transfer was incomplete')
        try:
            process = subprocess.Popen(command + ['shell', 'am', 'instrument', '-w', '-e', 'host_interop', 'true', '-e', 'class',
                'local.sovereigntv.control.HostInteropTest', 'local.sovereigntv.control.test/androidx.test.runner.AndroidJUnitRunner'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            deadline = time.monotonic() + 30
            while True:
                result = adb('shell', 'run-as', 'local.sovereigntv.control', 'cat', 'files/interop-ready.json', check=False)
                if result.returncode == 0:
                    try:
                        ready = json.loads(result.stdout)
                        break
                    except ValueError:
                        pass
                if time.monotonic() >= deadline or process.poll() is not None:
                    startup = 'deadline'
                    if process.poll() is not None:
                        output, error = process.communicate()
                        logs = ROOT / '.local'
                        logs.mkdir(mode=0o700, exist_ok=True)
                        (logs / 'control-interop-last.log').write_bytes(output + error)
                        # Only fixed categories may enter hosted output; retain raw diagnostics
                        # locally, never in public CI artifacts or exception messages.
                        startup = 'bind_failed' if b'java.net.BindException' in output + error else 'fixture_exited'
                    raise RuntimeError('Synthetic listener unavailable (' + startup + '); inspect private interop diagnostics')
                time.sleep(.2)
            device = directory / 'device-public.pem'; device.write_text(ready['public_certificate'])
            remote_port = ready['port']
            if type(remote_port) is not int or not 1 <= remote_port <= 65535:
                raise RuntimeError('Invalid synthetic listener port')
            port = int(adb('forward', 'tcp:0', 'tcp:' + str(remote_port)).stdout)
            client = Client('127.0.0.1', port, device, certificate, directory / 'executor/client-key.pem', allow_loopback=True)
            def call(operation, arguments=None):
                response, _ = client.request(operation, arguments, expires_at_ms=int(time.time() * 1000) + 10000)
                if response['status'] != 'ok':
                    raise RuntimeError('Synthetic operation refused')
                return response['result']
            # A default successful handshake proves only its negotiated version. Qualify both
            # enabled versions through the real Keystore endpoint, including client authentication.
            version_states = []
            for version in (ssl.TLSVersion.TLSv1_2, ssl.TLSVersion.TLSv1_3):
                client.context.minimum_version = version
                client.context.maximum_version = version
                version_states.append(call('state'))
            if version_states[0] != version_states[1]:
                raise RuntimeError('Read-only protocol probes changed native state')
            client.context.minimum_version = ssl.TLSVersion.TLSv1_2
            client.context.maximum_version = ssl.TLSVersion.MAXIMUM_SUPPORTED
            before = call('state'); base = before['revision']; document = json.loads(before['document'])
            document['title'] = 'External executor qualification'
            exact = json.dumps(document, ensure_ascii=False, separators=(',', ':'))
            request_id = str(uuid.uuid4())
            change = {'request_id': request_id, 'base_revision': base, 'document': exact}
            receipt = call('apply', change)['receipt']
            if call('receipt', {'request_id': request_id}) != receipt or call('state')['document'] != exact:
                raise RuntimeError('Synthetic committed read-back mismatch')
            if call('apply', change)['receipt'] != receipt:
                raise RuntimeError('Exact retry changed its receipt')
            call('undo', {'request_id': str(uuid.uuid4()), 'base_revision': base + 1, 'restore_revision': base})
            after = call('state')
            if after['document'] != before['document'] or after['revision'] != base + 2:
                raise RuntimeError('Synthetic undo mismatch')
            adb('shell', '-T', 'run-as', 'local.sovereigntv.control', 'dd', 'of=files/interop-done', input=b'done')
            output, error = process.communicate(timeout=15)
            if process.returncode or b'OK (1 test)' not in output:
                raise RuntimeError('Android interop assertions failed')
            print(json.dumps({'scope': 'owned Android emulator; Python OpenSSL 3 to Android Keystore TLS',
                              'read_back': True, 'receipt': True, 'exact_retry': True, 'undo': True,
                              'mutual_tls_versions': ['TLSv1.2', 'TLSv1.3'],
                              'agentos_qualified': False, 'target_tv_qualified': False}))
        finally:
            if process is not None and process.poll() is None:
                adb('shell', '-T', 'run-as', 'local.sovereigntv.control', 'dd', 'of=files/interop-done', input=b'done', check=False)
                try:
                    process.communicate(timeout=5)
                except subprocess.TimeoutExpired:
                    process.terminate(); process.communicate(timeout=5)
                    adb('shell', 'am', 'force-stop', 'local.sovereigntv.control', check=False)
            if port is not None:
                adb('forward', '--remove', 'tcp:' + str(port), check=False)


if __name__ == '__main__':
    main()
