import json
import os
from pathlib import Path
import subprocess
import tempfile
import sys
import time
import unittest
from unittest.mock import patch
from tools.collect_board_identity import collect, collect_files, public_cpu, write_report, PinnedSdb, source_family_match, MAX_OUTPUT, resource


class FakeSdb:
    def __init__(self, state='device'):
        self.calls = []
        self.state = state

    def run(self, arguments, timeout):
        self.calls.append(tuple(arguments))
        if arguments[-1] == 'wait-for-device':
            return subprocess.CompletedProcess(arguments, 1, b'', b'')
        if arguments[0] == 'connect':
            return subprocess.CompletedProcess(arguments, 0, b'connected to synthetic endpoint', b'')
        if arguments[0] == 'devices':
            return subprocess.CompletedProcess(arguments, 0, ('List of devices attached\n192.168.1.2:26101 ' + self.state + ' fixture\n').encode(), b'')
        command = tuple(arguments[3:])
        output = {('uname', '-m'): b'armv7l\n', ('uname', '-r'): b'5.4.261-owner-build-canary\n',
                  ('getconf', 'LONG_BIT'): b'32\n',
                  ('cat', '/proc/cpuinfo'): b'processor : 0\nCPU implementer : 0x41\nCPU architecture : 8\nCPU part : 0xd03\nSerial : UNIQUE-SERIAL-CANARY\nHardware : PRIVATE-HARDWARE-CANARY\n',
                  ('cat', '/proc/device-tree/compatible'): b'private-compatible-canary\0'}[command]
        return subprocess.CompletedProcess(arguments, 0, output, b'')


class FakeFileSdb(FakeSdb):
    def __init__(self, capability=b'filesync_support:pushpull\n', output=None):
        super().__init__()
        self.capability = capability
        self.output = output

    def run(self, arguments, timeout):
        if arguments[-1] == 'capability':
            self.calls.append(tuple(arguments))
            return subprocess.CompletedProcess(arguments, 0, self.capability, b'')
        return super().run(arguments, timeout)

    def capabilities(self, serial, timeout):
        return self.run(['-s', serial, 'capability'], timeout)

    def pull(self, serial, remote, timeout):
        self.calls.append(('-s', serial, 'pull', remote))
        data = { '/proc/cpuinfo': b'processor : 0\nCPU implementer : 0x41\nCPU architecture : 8\nCPU part : 0xd07\nSerial : PRIVATE-SERIAL-CANARY\n',
                 '/proc/device-tree/compatible': b'vendor,PRIVATE-COMPATIBLE\0samsung,sdp-pontusm\0'}[remote]
        return subprocess.CompletedProcess([], 0, data if self.output is None else self.output, b'')


class BoardIdentityTests(unittest.TestCase):
    def identity(self, _host):
        return {'model_match': 'full_sku', 'reported_model_code': 'QN50LS03FAFXZA'}

    def test_file_transfer_uses_only_two_fixed_reads_and_preserves_private_identifiers(self):
        runner = FakeFileSdb()
        report = collect_files('192.168.1.2', runner, identifier=self.identity)
        public = report['public']
        self.assertEqual(public['status'], 'file_reads_completed')
        self.assertEqual(public['validated_reads'], 2)
        self.assertEqual(public['cpu']['parts'], ['0xd07'])
        self.assertTrue(public['source_family_compatible_match'])
        self.assertFalse(public['shell_commands_requested'])
        self.assertFalse(public['settings_or_software_changed'])
        self.assertNotIn('PRIVATE', json.dumps(public))
        self.assertNotIn('192.168.1.2', json.dumps(public))
        self.assertIn('PRIVATE-SERIAL', json.dumps(report['private']))
        self.assertEqual([c[3:] for c in runner.calls if len(c)>2 and c[2]=='pull'],
                         [('/proc/cpuinfo',), ('/proc/device-tree/compatible',)])
        self.assertFalse(any('shell' in c or 'root' in c or 'push' in c for c in runner.calls))

    def test_file_transfer_requires_fresh_pull_capability_and_exact_target(self):
        for capability in (b'', b'filesync_support:push\n', b'filesync_support:pushpull\nfilesync_support:pull\n'):
            runner = FakeFileSdb(capability)
            result = collect_files('192.168.1.2', runner, identifier=self.identity)['public']
            self.assertEqual(result['status'], 'file_transfer_unavailable')
            self.assertFalse(result['file_reads_attempted'])
        runner = FakeFileSdb()
        result = collect_files('192.168.1.2', runner, identifier=lambda _: {'model_match':'family_only'})
        self.assertEqual(runner.calls, [])
        self.assertFalse(result['public']['file_reads_attempted'])
        for collector in (collect, collect_files):
            runner = FakeFileSdb()
            runner.run = lambda args, timeout: subprocess.CompletedProcess(args, 1, b'', b'')
            self.assertEqual(collector('192.168.1.2', runner, identifier=self.identity)['public']['status'], 'device_unconfirmed')

    def test_one_bounded_same_endpoint_wait_and_stderr_capability(self):
        runner = FakeFileSdb()
        original = runner.run
        ready = False
        def run(args, timeout):
            nonlocal ready
            if args[-1] == 'wait-for-device':
                self.assertEqual(args, ['-s','192.168.1.2:26101','wait-for-device'])
                self.assertEqual(timeout, 5)
                runner.calls.append(tuple(args)); ready = True
                return subprocess.CompletedProcess(args, 0, b'', b'')
            if args == ['devices'] and not ready:
                runner.calls.append(tuple(args))
                return subprocess.CompletedProcess(args, 0, b'List of devices attached\n', b'')
            return original(args, timeout)
        runner.run = run
        runner.capabilities = lambda serial, timeout: subprocess.CompletedProcess([], 0, b'',
                                         b'filesync_support:pushpull\nPRIVATE-DIAGNOSTIC-CANARY\n')
        report = collect_files('192.168.1.2', runner, identifier=self.identity)
        self.assertEqual(report['public']['status'], 'file_reads_completed')
        self.assertEqual(report['public']['capability_query_status'], 'parsed')
        self.assertEqual(sum(c[0]=='connect' for c in runner.calls), 1)
        self.assertEqual(sum(c[-1]=='wait-for-device' for c in runner.calls), 1)
        self.assertEqual(sum(c[0]=='devices' for c in runner.calls), 2)
        self.assertNotIn('PRIVATE-DIAGNOSTIC', json.dumps(report['public']))
        self.assertIn('PRIVATE-DIAGNOSTIC', json.dumps(report['private']))

    def test_empty_failed_and_unrecognized_files_do_not_establish_identity(self):
        for output, status in ((b'', 'file_reads_empty'), (b' \n', 'file_reads_empty'),
                               (b'PRIVATE-UNRECOGNIZED', 'file_reads_partial')):
            result = collect_files('192.168.1.2', FakeFileSdb(output=output), identifier=self.identity)['public']
            self.assertEqual(result['status'], status)
            self.assertEqual(result['validated_reads'], 0)
            self.assertNotIn('PRIVATE', json.dumps(result))
        runner = FakeFileSdb()
        runner.pull = lambda *args, **kwargs: subprocess.CompletedProcess([], 1, b'processor : 0\nCPU part : 0xd07\n', b'')
        result = collect_files('192.168.1.2', runner, identifier=self.identity)['public']
        self.assertIsNone(result['cpu'])
        self.assertEqual(result['successful_reads'], 0)

    def test_partial_file_evidence_survives_a_later_client_failure_without_error_leak(self):
        runner = FakeFileSdb()
        original = runner.pull
        def pull(serial, remote, timeout):
            if remote.endswith('compatible'):
                raise TimeoutError('PRIVATE-ERROR-CANARY')
            return original(serial, remote, timeout)
        runner.pull = pull
        result = collect_files('192.168.1.2', runner, identifier=self.identity)
        public = result['public']
        self.assertTrue(public['collection_interrupted'])
        self.assertEqual(public['status'], 'file_reads_partial')
        self.assertEqual(public['validated_reads'], 1)
        self.assertEqual(public['cpu']['parts'], ['0xd07'])
        self.assertNotIn('PRIVATE-ERROR-CANARY', json.dumps(result))
        runner = FakeFileSdb(output=b'x'*(MAX_OUTPUT+1))
        public = collect_files('192.168.1.2', runner, identifier=self.identity)['public']
        self.assertEqual(public['status'], 'collection_unavailable')
        self.assertEqual(len(public['file_read_results']), 1)

    @unittest.skipIf(resource is None or (hasattr(os, 'geteuid') and os.geteuid() == 0), 'normal POSIX host account required')
    def test_pull_has_no_remote_path_or_endpoint_escape_and_private_regular_destination(self):
        runner = object.__new__(PinnedSdb)
        runner.path = Path(sys.executable)
        seen = []
        def run(args, timeout, *, limit_files, capture_errors):
            self.assertTrue(limit_files)
            self.assertTrue(capture_errors)
            path = Path(args[-1])
            self.assertTrue(path.is_file())
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(path.parent.stat().st_mode & 0o777, 0o500)
            with self.assertRaises(PermissionError):
                (path.parent / 'unexpected-directory-output').write_bytes(b'not allowed')
            seen.append(args)
            path.write_bytes(b'payload')
            return subprocess.CompletedProcess(args, 0, b'unpublished SDK progress', b'')
        runner._run = run
        result = runner.pull('192.168.1.2:26101', '/proc/cpuinfo')
        self.assertEqual(result.stdout, b'payload')
        self.assertEqual(result.transfer_status, 'bytes_received')
        self.assertFalse(Path(seen[0][-1]).exists())
        for endpoint, remote in (('8.8.8.8:26101','/proc/cpuinfo'), ('192.168.1.2:22','/proc/cpuinfo'),
                                  ('192.168.1.2:26101','/dev/mmcblk0'), ('192.168.1.2:26101','/proc')):
            with self.assertRaises(ValueError): runner.pull(endpoint, remote)
        self.assertEqual(len(seen), 1)

    @unittest.skipIf(resource is None, 'POSIX resource limit unavailable')
    def test_sdk_client_file_output_has_an_os_enforced_size_limit(self):
        runner = object.__new__(PinnedSdb)
        runner.path = Path(sys.executable)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'limited-output'
            result = runner._run(['-c', 'import sys; open(sys.argv[1],"wb").write(b"x"*1000000)', str(path)],
                                 timeout=2, limit_files=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertLessEqual(path.stat().st_size, MAX_OUTPUT)

    def test_pull_diagnostics_have_a_shared_bounded_budget(self):
        runner = object.__new__(PinnedSdb)
        runner.path = Path(sys.executable)
        with self.assertRaises(ValueError):
            runner._run(['-c', 'import os; os.write(1,b"x"*40000); os.write(2,b"y"*40000)'],
                        timeout=2, capture_errors=True)
        result = runner._run(['-c', 'import os; os.write(1,b"out"); os.write(2,b"err")'],
                             timeout=2, capture_errors=True)
        self.assertEqual((result.stdout,result.stderr),(b'out',b'err'))

    def test_wrong_model_or_unconfirmed_device_never_reaches_a_shell(self):
        runner = FakeSdb()
        report = collect('192.168.1.2', runner, identifier=lambda _: {'model_match': 'family_only'})
        self.assertFalse(report['public']['board_commands_executed']); self.assertEqual(runner.calls, [])
        for status in ('offline', 'unauthorized'):
            runner = FakeSdb(status)
            report = collect('192.168.1.2', runner, identifier=self.identity)
            self.assertFalse(report['public']['board_commands_executed'])
            self.assertTrue(all('shell' not in call and 'pull' not in call for call in runner.calls))
        with self.assertRaises(ValueError):
            collect('8.8.8.8', FakeSdb(), identifier=self.identity)

    def test_fixed_reads_keep_raw_identifiers_private_and_preserve_abi_distinctions(self):
        runner = FakeSdb()
        report = collect('192.168.1.2', runner, identifier=self.identity)
        public = report['public']
        self.assertTrue(public['board_commands_executed'])
        self.assertFalse(public['settings_or_software_changed'])
        self.assertEqual(public['kernel_architecture'], 'armv7l')
        self.assertEqual(public['kernel_release_core'], '5.4.261')
        self.assertEqual(public['reported_userspace_bits'], 32)
        self.assertEqual(public['cpu']['architectures'], [8])
        self.assertEqual(public['cpu']['parts'], ['0xd03'])
        self.assertNotIn('CANARY', json.dumps(public))
        self.assertNotIn('192.168.1.2', json.dumps(public))
        self.assertIn('UNIQUE-SERIAL-CANARY', json.dumps(report['private']))
        self.assertEqual([call[3:] for call in runner.calls if call[0] == '-s'], [
            ('uname', '-m'), ('uname', '-r'), ('getconf', 'LONG_BIT'),
            ('cat', '/proc/cpuinfo'), ('cat', '/proc/device-tree/compatible')])
        with tempfile.TemporaryDirectory() as directory:
            output = write_report(Path(directory) / 'private-collection', report)
            self.assertEqual(output.stat().st_mode & 0o777, 0o700)
            for file in output.iterdir():
                self.assertEqual(file.stat().st_mode & 0o777, 0o600)
            with self.assertRaises(FileExistsError):
                write_report(output, report)

    def test_unknown_cpu_strings_cannot_become_public_identification(self):
        report = public_cpu('Serial : PRIVATE\nHardware : PRIVATE\nCPU implementer : PRIVATE\nCPU part : PRIVATE\nCPU architecture : PRIVATE\nprocessor : PRIVATE\n')
        self.assertNotIn('PRIVATE', json.dumps(report)); self.assertEqual(report['parts'], [])
        self.assertEqual(report['reported_processor_entries'], 0)

    def test_zero_exit_empty_or_unrecognized_responses_are_not_completed_identity(self):
        for output, status, successful in ((b'', 'reads_empty', 0), (b' \n\t', 'reads_empty', 0),
                                            (b'PRIVATE-UNRECOGNIZED-CANARY', 'reads_partial', 5)):
            runner = FakeSdb()
            original = runner.run
            def run(arguments, timeout):
                result = original(arguments, timeout)
                if arguments[0] == '-s':
                    result.stdout = output
                return result
            runner.run = run
            report = collect('192.168.1.2', runner, identifier=self.identity)
            public = report['public']
            self.assertEqual(public['status'], status)
            self.assertEqual(public['successful_reads'], successful)
            self.assertEqual(public['validated_reads'], 0)
            self.assertNotIn('CANARY', json.dumps(public))
            if successful == 0:
                self.assertIsNone(public['cpu'])

    def test_source_match_is_exact_bounded_and_does_not_expose_other_compatibles(self):
        self.assertTrue(source_family_match('vendor,PRIVATE-CANARY\0samsung,sdp-pontusm\0'))
        for raw in ('samsung,sdp-pontusmx\0', 'prefix-samsung,sdp-pontusm\0', 'vendor,other\0'):
            self.assertFalse(source_family_match(raw))
        for raw in (None, '', 'samsung,sdp-pontusm', '\0', 'samsung,sdp-pontusm\0\0', 'bad\nvalue\0', 'a' * 4097 + '\0'):
            self.assertIsNone(source_family_match(raw))
        runner = FakeSdb()
        original = runner.run
        def run(arguments, timeout):
            result = original(arguments, timeout)
            if tuple(arguments[3:]) == ('cat', '/proc/device-tree/compatible'):
                result.stdout = b'vendor,PRIVATE-CANARY\0samsung,sdp-pontusm\0'
            return result
        runner.run = run
        report = collect('192.168.1.2', runner, identifier=self.identity)
        self.assertTrue(report['public']['source_family_compatible_match'])
        self.assertNotIn('PRIVATE-CANARY', json.dumps(report['public']))
        self.assertIn('PRIVATE-CANARY', json.dumps(report['private']))
        def fail(arguments, timeout):
            result = run(arguments, timeout)
            if tuple(arguments[3:]) == ('cat', '/proc/device-tree/compatible'):
                result.returncode = 1
            return result
        runner.run = fail
        report = collect('192.168.1.2', runner, identifier=self.identity)
        self.assertIsNone(report['public']['source_family_compatible_match'])

    def test_unpinned_executable_is_refused_before_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            fake = Path(directory) / 'not-the-official-sdb'
            fake.write_text('Synthetic executable canary; never execute')
            with self.assertRaises(ValueError):
                PinnedSdb(fake)

    def test_ambiguous_or_wrong_endpoint_never_reaches_a_shell(self):
        for listing in (b'192.168.1.3:26101 device fixture\n',
                        b'192.168.1.2:26101 device fixture\n192.168.1.2 device fixture\n'):
            runner = FakeSdb()
            original = runner.run
            def run(arguments, timeout):
                if arguments == ['devices']:
                    runner.calls.append(tuple(arguments))
                    return subprocess.CompletedProcess(arguments, 0, listing, b'')
                return original(arguments, timeout)
            runner.run = run
            report = collect('192.168.1.2', runner, identifier=self.identity)
            self.assertFalse(report['public']['board_commands_executed'])
            self.assertFalse(any('shell' in call or 'pull' in call for call in runner.calls))

    def test_failed_cpu_read_is_unknown_not_zero_and_errors_are_sanitized(self):
        runner = FakeSdb()
        original = runner.run
        def run(arguments, timeout):
            result = original(arguments, timeout)
            if tuple(arguments[3:]) == ('cat', '/proc/cpuinfo'):
                result.returncode = 1
            return result
        runner.run = run
        report = collect('192.168.1.2', runner, identifier=self.identity)
        self.assertIsNone(report['public']['cpu'])
        self.assertEqual(report['public']['status'], 'reads_partial')
        runner.run = lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError('PRIVATE-ERROR-CANARY'))
        report = collect('192.168.1.2', runner, identifier=self.identity)
        self.assertNotIn('PRIVATE-ERROR-CANARY', json.dumps(report))
        self.assertEqual(report['public']['status'], 'collection_unavailable')

    def test_runner_bounds_real_subprocess_output_and_wall_time(self):
        # Bypass the pinned-SDK constructor only here; the CLI cannot select another digest.
        runner = object.__new__(PinnedSdb)
        runner.path = Path(sys.executable)
        for code, timeout, error in (
                ('import os; os.write(1, b"x" * 70000)', 2, ValueError),
                ('import time; time.sleep(20)', 0.15, TimeoutError),
                ('import os,time\nwhile True:\n os.write(1,b"x"); time.sleep(.02)', 0.15, TimeoutError)):
            started = time.monotonic()
            with self.assertRaises(error):
                runner.run(['-c', code], timeout=timeout)
            self.assertLess(time.monotonic() - started, 3)
