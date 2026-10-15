#!/usr/bin/env python3
"""Collect five fixed normal-SDB reads into owner-private evidence; never change TV settings."""
import argparse
from datetime import datetime, timezone
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import selectors
import subprocess
import time

try:
    from tools.identify_tv import identify, PRIVATE_NETWORKS, EXPECTED_MODEL
except ModuleNotFoundError:  # Direct script invocation.
    from identify_tv import identify, PRIVATE_NETWORKS, EXPECTED_MODEL


SDB_SHA256 = '05db410d2e36e85147f95b20bae6296a71c54dab0e1ec79f9e11b89c4b6bd2cd'
MAX_OUTPUT = 65536
READS = (('uname', '-m'), ('uname', '-r'), ('getconf', 'LONG_BIT'),
         ('cat', '/proc/cpuinfo'), ('cat', '/proc/device-tree/compatible'))
ARCHITECTURES = {'armv7l', 'armv8l', 'aarch64', 'x86_64', 'i686', 'mips', 'mipsel'}


class PinnedSdb:
    def __init__(self, path):
        self.path = Path(path).resolve(strict=True)
        if not self.path.is_file() or self.path.stat().st_size > 32 * 1024 * 1024:
            raise ValueError('official SDB binary required')
        if hashlib.sha256(self.path.read_bytes()).hexdigest() != SDB_SHA256:
            raise ValueError('official SDB digest mismatch')

    def run(self, arguments, timeout):
        # No shell interpreter, inherited input, stderr content or unbounded communicate buffer.
        with subprocess.Popen([str(self.path), *arguments], stdin=subprocess.DEVNULL,
                              stdout=subprocess.PIPE, stderr=subprocess.DEVNULL) as process:
            data = bytearray()
            deadline = time.monotonic() + min(timeout, 5)
            try:
                with selectors.DefaultSelector() as selector:
                    selector.register(process.stdout, selectors.EVENT_READ)
                    while True:
                        remaining = deadline - time.monotonic()
                        if remaining <= 0:
                            raise TimeoutError('SDB read deadline exceeded')
                        if not selector.select(remaining):
                            raise TimeoutError('SDB read deadline exceeded')
                        block = os.read(process.stdout.fileno(), min(4096, MAX_OUTPUT + 1 - len(data)))
                        if not block:
                            break
                        data.extend(block)
                        if len(data) > MAX_OUTPUT:
                            raise ValueError('SDB output exceeds budget')
                status = process.wait(timeout=max(0.001, deadline - time.monotonic()))
                return subprocess.CompletedProcess(arguments, status, bytes(data), b'')
            finally:
                if process.poll() is None:
                    process.kill()
                process.wait()


def public_cpu(raw):
    fields = {'implementers': set(), 'parts': set(), 'architectures': set()}
    processors = set()
    for line in raw.splitlines():
        key, separator, value = line.partition(':')
        if not separator:
            continue
        key, value = key.strip(), value.strip()
        if key in ('CPU implementer', 'CPU part') and re.fullmatch(r'0x[0-9a-fA-F]{1,4}', value):
            fields['implementers' if key == 'CPU implementer' else 'parts'].add(hex(int(value, 16)))
        elif key == 'CPU architecture' and re.fullmatch(r'[0-9]{1,2}', value):
            fields['architectures'].add(int(value))
        elif key == 'processor' and re.fullmatch(r'[0-9]{1,3}', value):
            processors.add(int(value))
    return {**{key: sorted(values) for key, values in fields.items()},
            'reported_processor_entries': len(processors)}


def collect(host, runner, *, identifier=identify):
    address = ipaddress.IPv4Address(host)
    if not any(address in network for network in PRIVATE_NETWORKS):
        raise ValueError('owner-supplied private IPv4 required')
    public = {'schema_version': 1, 'observed_utc': datetime.now(timezone.utc).isoformat(),
              'board_commands_executed': False, 'settings_or_software_changed': False,
              'status': 'model_unconfirmed',
              'limit': 'Unauthenticated identity plus normal SDB reads; not boot, SoC, recovery or playback qualification.'}
    private = {'host': str(address), 'reads': []}
    report = {'public': public, 'private': private}
    try:
        identity = identifier(str(address))
        if identity.get('model_match') != 'full_sku' or identity.get('reported_model_code') != EXPECTED_MODEL:
            return report
        endpoint = str(address) + ':26101'
        runner.run(['connect', endpoint], timeout=5)
        devices = runner.run(['devices'], timeout=5)
        if devices.returncode != 0 or len(devices.stdout) > MAX_OUTPUT:
            public['status'] = 'device_unconfirmed'
            return report
        candidates = []
        for line in devices.stdout.decode('utf-8', errors='replace').splitlines():
            fields = line.split()
            if len(fields) >= 2 and fields[0] in (str(address), endpoint):
                candidates.append((fields[0], fields[1]))
        if len(candidates) != 1 or candidates[0][1] != 'device':
            public['status'] = 'device_unconfirmed'
            return report
        serial = candidates[0][0]
        outputs = {}
        for command in READS:
            public['board_commands_executed'] = True
            result = runner.run(['-s', serial, 'shell', *command], timeout=5)
            if len(result.stdout) > MAX_OUTPUT:
                raise ValueError('SDB output exceeds budget')
            raw = result.stdout.decode('utf-8', errors='replace')
            private['reads'].append({'command': list(command), 'returncode': result.returncode, 'stdout': raw})
            if result.returncode == 0:
                outputs[command] = raw.strip()
        arch = outputs.get(READS[0])
        release = re.fullmatch(r'([0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,4})(?:[-+].*)?', outputs.get(READS[1], ''))
        bits = outputs.get(READS[2])
        public.update(status='reads_completed' if len(outputs) == len(READS) else 'reads_partial',
                      kernel_architecture=arch if arch in ARCHITECTURES else None,
                      kernel_release_core=release.group(1) if release else None,
                      reported_userspace_bits=int(bits) if bits in ('32', '64') else None,
                      cpu=public_cpu(outputs[READS[3]]) if READS[3] in outputs else None,
                      successful_reads=len(outputs))
    except Exception:
        # SDK/server errors may contain device IDs. Retain no exception strings.
        public['status'] = 'collection_unavailable'
    return report


def write_report(path, report):
    path = Path(path)
    path.mkdir(mode=0o700, parents=True, exist_ok=False)
    os.chmod(path, 0o700)
    for name in ('public', 'private'):
        with os.fdopen(os.open(path / (name + '.json'), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'w') as output:
            json.dump(report[name], output, indent=2)
            output.write('\n')
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('host', help='Exact owner-supplied private TV IPv4; no discovery')
    args = parser.parse_args()
    try:
        runner = PinnedSdb(Path(__file__).resolve().parents[1] / '.local/toolchain/sdb-4.2.36/sdb')
        report = collect(args.host, runner)
        target = Path(__file__).resolve().parents[1] / '.local/board-identity' / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        write_report(target, report)
    except Exception:
        parser.exit(1, 'Collection refused or unavailable; no raw diagnostic printed.\n')
    print('Private collection saved under .local/board-identity; status: ' + report['public']['status'])
    return 0 if report['public']['status'] == 'reads_completed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
