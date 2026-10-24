#!/usr/bin/env python3
"""Collect fixed normal-SDB identity reads into owner-private evidence; never change TV settings."""
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
import stat
import tempfile
import time

try:
    import resource
except ImportError:
    resource = None

try:
    from tools.identify_tv import identify, PRIVATE_NETWORKS, EXPECTED_MODEL
except ModuleNotFoundError:  # Direct script invocation.
    from identify_tv import identify, PRIVATE_NETWORKS, EXPECTED_MODEL


SDB_SHA256 = '05db410d2e36e85147f95b20bae6296a71c54dab0e1ec79f9e11b89c4b6bd2cd'
MAX_OUTPUT = 65536
READS = (('uname', '-m'), ('uname', '-r'), ('getconf', 'LONG_BIT'),
         ('cat', '/proc/cpuinfo'), ('cat', '/proc/device-tree/compatible'))
FILE_READS = ('/proc/cpuinfo', '/proc/device-tree/compatible')
# Manually reviewed family-source machine registration; not an exact-board identifier.
FAMILY_COMPATIBLE = 'samsung,sdp-pontusm'
ARCHITECTURES = {'armv7l', 'armv8l', 'aarch64', 'x86_64', 'i686', 'mips', 'mipsel'}


class PinnedSdb:
    def __init__(self, path):
        self.path = Path(path).resolve(strict=True)
        if not self.path.is_file() or self.path.stat().st_size > 32 * 1024 * 1024:
            raise ValueError('official SDB binary required')
        if self.path.stat().st_mode & (stat.S_ISUID | stat.S_ISGID):
            raise ValueError('privileged host SDK executable refused')
        if hashlib.sha256(self.path.read_bytes()).hexdigest() != SDB_SHA256:
            raise ValueError('official SDB digest mismatch')

    def run(self, arguments, timeout):
        return self._run(arguments, timeout, capture_errors=True)

    def capabilities(self, serial, timeout=5):
        return self._run(['-s', serial, 'capability'], timeout, capture_errors=True)

    def _run(self, arguments, timeout, *, limit_files=False, capture_errors=False):
        if limit_files and resource is None:
            raise ValueError('file transfer requires POSIX file-size enforcement')
        # No shell interpreter, inherited input or unbounded communicate buffer.
        with subprocess.Popen([str(self.path), *arguments], stdin=subprocess.DEVNULL,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE if capture_errors else subprocess.DEVNULL,
                              preexec_fn=_limit_pull_file if limit_files else None) as process:
            data, errors = bytearray(), bytearray()
            deadline = time.monotonic() + min(timeout, 5)
            try:
                with selectors.DefaultSelector() as selector:
                    selector.register(process.stdout, selectors.EVENT_READ, data)
                    if capture_errors:
                        selector.register(process.stderr, selectors.EVENT_READ, errors)
                    while selector.get_map():
                        remaining = deadline - time.monotonic()
                        if remaining <= 0:
                            raise TimeoutError('SDB read deadline exceeded')
                        ready = selector.select(remaining)
                        if not ready:
                            raise TimeoutError('SDB read deadline exceeded')
                        for key, _ in ready:
                            block = os.read(key.fd, min(4096, MAX_OUTPUT+1-len(data)-len(errors)))
                            if not block:
                                selector.unregister(key.fileobj)
                                continue
                            key.data.extend(block)
                            if len(data)+len(errors) > MAX_OUTPUT:
                                raise ValueError('SDB output exceeds budget')
                status = process.wait(timeout=max(0.001, deadline - time.monotonic()))
                return subprocess.CompletedProcess(arguments, status, bytes(data), bytes(errors))
            finally:
                if process.poll() is None:
                    process.kill()
                process.wait()

    def pull(self, serial, remote, timeout=5):
        if resource is None or os.geteuid() == 0:
            raise ValueError('file transfer requires a normal POSIX host account')
        address = serial[:-6] if serial.endswith(':26101') else serial
        parsed = ipaddress.IPv4Address(address)
        if (serial not in (str(parsed), str(parsed)+':26101')
                or not any(parsed in network for network in PRIVATE_NETWORKS)
                or remote not in FILE_READS):
            raise ValueError('only exact private endpoint and fixed files may be pulled')
        with tempfile.TemporaryDirectory(prefix='sovereign-tv-pull-') as directory:
            destination = Path(directory) / 'read.bin'
            # One regular destination in a non-writable directory: no recursive export or replacement.
            with os.fdopen(os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'wb'):
                pass
            os.chmod(directory, 0o500)
            try:
                result = self._run(['-s', serial, 'pull', remote, str(destination)], timeout,
                                   limit_files=True, capture_errors=True)
                info = destination.lstat()
                if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_OUTPUT:
                    raise ValueError('unexpected pull output')
                with destination.open('rb') as stream:
                    data = stream.read(MAX_OUTPUT+1)
            finally:
                os.chmod(directory, 0o700)
            if len(data) > MAX_OUTPUT:
                raise ValueError('pull input exceeds budget')
            status = 'bytes_received' if result.returncode == 0 and data else 'empty' if result.returncode == 0 else 'failed'
            if result.returncode != 0:
                diagnostics = result.stdout+result.stderr
                if b'You cannot pull files from this path' in diagnostics:
                    status = 'path_denied'
                elif b'NO support file pull' in diagnostics:
                    status = 'pull_unsupported'
            response = subprocess.CompletedProcess(result.args, result.returncode, data, b'')
            response.transfer_status = status
            return response


def _limit_pull_file():
    # Called in the SDK client child only, after the normal SDK server/session check.
    os.umask(0o077)
    resource.setrlimit(resource.RLIMIT_FSIZE, (MAX_OUTPUT, MAX_OUTPUT))


def confirmed_session(address, runner, identifier, *, trace=None):
    def run(arguments):
        label = arguments[-1] if arguments[0] == '-s' else arguments[0]
        try:
            result = runner.run(arguments, timeout=5)
            if len(result.stdout)+len(result.stderr) > MAX_OUTPUT:
                raise ValueError('transport output budget')
        except Exception:
            if trace is not None:
                trace.append({'operation': label, 'client_failed': True})
            raise
        if trace is not None:
            trace.append({'operation': label, 'returncode': result.returncode,
                          'stdout': result.stdout.decode('utf-8', errors='replace'),
                          'stderr': result.stderr.decode('utf-8', errors='replace')})
        return result
    identity = identifier(str(address))
    if identity.get('model_match') != 'full_sku' or identity.get('reported_model_code') != EXPECTED_MODEL:
        return None, 'model_unconfirmed'
    endpoint = str(address)+':26101'
    if run(['connect', endpoint]).returncode != 0:
        return None, 'device_unconfirmed'
    def device_state():
        devices = run(['devices'])
        if devices.returncode != 0 or len(devices.stdout) > MAX_OUTPUT:
            return None
        candidates = []
        for line in devices.stdout.decode('utf-8', errors='replace').splitlines():
            fields = line.split()
            if len(fields) >= 2 and fields[0] in (str(address), endpoint):
                candidates.append((fields[0], fields[1]))
        return candidates
    candidates = device_state()
    if candidates is None or len(candidates) > 1:
        return None, 'device_unconfirmed'
    if len(candidates) == 1 and candidates[0][1] == 'device':
        return candidates[0][0], None
    if candidates and candidates[0][1] != 'offline':
        return None, 'device_unconfirmed'
    # At most one bounded wait for the same endpoint, never another connection or target.
    try:
        if run(['-s', endpoint, 'wait-for-device']).returncode != 0:
            return None, 'device_unconfirmed'
    except Exception:
        return None, 'device_unconfirmed'
    candidates = device_state()
    if candidates is None or len(candidates) != 1 or candidates[0][1] != 'device':
        return None, 'device_unconfirmed'
    return candidates[0][0], None


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


def source_family_match(raw):
    # The DT string-list must be terminated and structurally bounded. Failed/malformed reads stay unknown.
    if not isinstance(raw, str) or not raw.endswith('\0') or len(raw) > 4096:
        return None
    values = raw[:-1].split('\0')
    if not 1 <= len(values) <= 32 or any(not re.fullmatch(r'[A-Za-z0-9,._+-]{1,128}', value) for value in values):
        return None
    return FAMILY_COMPATIBLE in values


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
        serial, status = confirmed_session(address, runner, identifier)
        if status is not None:
            public['status'] = status
            return report
        outputs = {}
        for command in READS:
            public['board_commands_executed'] = True
            result = runner.run(['-s', serial, 'shell', *command], timeout=5)
            if len(result.stdout) > MAX_OUTPUT:
                raise ValueError('SDB output exceeds budget')
            raw = result.stdout.decode('utf-8', errors='replace')
            private['reads'].append({'command': list(command), 'returncode': result.returncode, 'stdout': raw})
            # Some retail-TV SDB sessions report exit 0 with no shell output.
            # Transport success alone is not a successful identity read.
            if result.returncode == 0 and raw.strip():
                outputs[command] = raw.strip()
        arch = outputs.get(READS[0])
        release = re.fullmatch(r'([0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,4})(?:[-+].*)?', outputs.get(READS[1], ''))
        bits = outputs.get(READS[2])
        cpu = public_cpu(outputs[READS[3]]) if READS[3] in outputs else None
        family_match = source_family_match(outputs.get(READS[4]))
        validated = sum((arch in ARCHITECTURES, release is not None, bits in ('32', '64'),
                         cpu is not None and cpu['reported_processor_entries'] > 0,
                         family_match is not None))
        public.update(status='reads_completed' if validated == len(READS) else 'reads_partial' if outputs else 'reads_empty',
                      kernel_architecture=arch if arch in ARCHITECTURES else None,
                      kernel_release_core=release.group(1) if release else None,
                      reported_userspace_bits=int(bits) if bits in ('32', '64') else None,
                      cpu=cpu,
                      source_family_compatible_match=family_match,
                      successful_reads=len(outputs), validated_reads=validated)
    except Exception:
        # SDK/server errors may contain device IDs. Retain no exception strings.
        public['status'] = 'collection_unavailable'
    return report


def collect_files(host, runner, *, identifier=identify):
    address = ipaddress.IPv4Address(host)
    if not any(address in network for network in PRIVATE_NETWORKS):
        raise ValueError('owner-supplied private IPv4 required')
    public = {'schema_version': 1, 'observed_utc': datetime.now(timezone.utc).isoformat(),
              'transport': 'normal_sdb_file_transfer', 'shell_commands_requested': False,
              'file_reads_attempted': False, 'settings_or_software_changed': False,
              'normal_sdb_session_confirmed': False, 'pull_capability_reported': None,
              'status': 'model_unconfirmed', 'file_read_results': [],
              'limit': 'SDK-reported file capability and two ordinary reads only; not exact board, '
                       'physical SoC, boot, recovery or playback qualification.'}
    private = {'host': str(address), 'reads': []}
    report = {'public': public, 'private': private}
    try:
        serial, status = confirmed_session(address, runner, identifier,
                                           trace=private.setdefault('transport_diagnostics', []))
        if status is not None:
            public['status'] = status
            return report
        public['normal_sdb_session_confirmed'] = True
        capability = runner.capabilities(serial, timeout=5)
        if len(capability.stdout)+len(capability.stderr) > MAX_OUTPUT:
            raise ValueError('capability budget')
        capability_text = capability.stdout.decode('utf-8', errors='replace')+'\n'+capability.stderr.decode('utf-8', errors='replace')
        values = [line.split(':', 1)[1].strip()
                  for line in capability_text.splitlines()
                  if ':' in line and line.split(':', 1)[0].strip() == 'filesync_support']
        private['capability'] = {'returncode': capability.returncode,
                                 'stdout': capability.stdout.decode('utf-8', errors='replace'),
                                 'stderr': capability.stderr.decode('utf-8', errors='replace')}
        parsed_mode = capability.returncode == 0 and len(values) == 1 and values[0] in ('pull', 'pushpull', 'push', 'none', 'disabled')
        public['capability_query_status'] = ('failed' if capability.returncode != 0 else
                                              'empty' if not capability_text.strip() else
                                              'parsed' if parsed_mode else 'unrecognized')
        if parsed_mode:
            public['pull_capability_reported'] = values[0] in ('pull', 'pushpull')
        if capability.returncode != 0 or len(values) != 1 or values[0] not in ('pull', 'pushpull'):
            public['status'] = 'file_transfer_unavailable'
            return report
        public['pull_capability_reported'] = True
        outputs = {}
        interrupted = False
        for remote in FILE_READS:
            public['file_reads_attempted'] = True
            path_id = 'cpuinfo' if remote == FILE_READS[0] else 'compatible'
            try:
                result = runner.pull(serial, remote, timeout=5)
                if len(result.stdout) > MAX_OUTPUT:
                    raise ValueError('file budget')
            except Exception:
                interrupted = True
                private['reads'].append({'path': remote, 'client_failed': True})
                public['file_read_results'].append({'path_id': path_id, 'sdk_reported_status': None,
                                                    'client_failed': True})
                break
            raw = result.stdout.decode('utf-8', errors='replace')
            private['reads'].append({'path': remote, 'returncode': result.returncode, 'stdout': raw})
            if result.returncode == 0 and raw.strip():
                outputs[remote] = raw
            reported = getattr(result, 'transfer_status', 'unknown')
            if reported not in ('bytes_received', 'empty', 'failed', 'path_denied', 'pull_unsupported'):
                reported = 'unknown'
            public['file_read_results'].append({'path_id': path_id, 'sdk_reported_status': reported,
                                                'client_failed': False})
        cpu = public_cpu(outputs[FILE_READS[0]]) if FILE_READS[0] in outputs else None
        family = source_family_match(outputs.get(FILE_READS[1]))
        validated = int(bool(cpu and cpu['reported_processor_entries'] and cpu['implementers'] and cpu['parts'])) + int(family is not None)
        public.update(status='file_reads_completed' if validated == 2 else 'file_reads_partial' if outputs else 'collection_unavailable' if interrupted else 'file_reads_empty',
                      cpu=cpu, source_family_compatible_match=family,
                      successful_reads=len(outputs), validated_reads=validated,
                      collection_interrupted=interrupted)
    except Exception:
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
    parser.add_argument('--file-transfer', action='store_true', help='Use two fixed file pulls; never fall back to shell')
    args = parser.parse_args()
    try:
        runner = PinnedSdb(Path(__file__).resolve().parents[1] / '.local/toolchain/sdb-4.2.36/sdb')
        report = collect_files(args.host, runner) if args.file_transfer else collect(args.host, runner)
        target = Path(__file__).resolve().parents[1] / '.local/board-identity' / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        write_report(target, report)
    except Exception:
        parser.exit(1, 'Collection refused or unavailable; no raw diagnostic printed.\n')
    print('Private collection saved under .local/board-identity; status: ' + report['public']['status'])
    return 0 if report['public']['status'] in ('reads_completed', 'file_reads_completed') else 1


if __name__ == '__main__':
    raise SystemExit(main())
