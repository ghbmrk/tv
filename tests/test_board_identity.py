import json
import os
from pathlib import Path
import subprocess
import tempfile
import sys
import time
import unittest
from unittest.mock import patch
from tools.collect_board_identity import collect, public_cpu, write_report, PinnedSdb, source_family_match


class FakeSdb:
    def __init__(self, state='device'):
        self.calls = []
        self.state = state

    def run(self, arguments, timeout):
        self.calls.append(tuple(arguments))
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


class BoardIdentityTests(unittest.TestCase):
    def identity(self, _host):
        return {'model_match': 'full_sku', 'reported_model_code': 'QN50LS03FAFXZA'}

    def test_wrong_model_or_unconfirmed_device_never_reaches_a_shell(self):
        runner = FakeSdb()
        report = collect('192.168.1.2', runner, identifier=lambda _: {'model_match': 'family_only'})
        self.assertFalse(report['public']['board_commands_executed']); self.assertEqual(runner.calls, [])
        for status in ('offline', 'unauthorized'):
            runner = FakeSdb(status)
            report = collect('192.168.1.2', runner, identifier=self.identity)
            self.assertFalse(report['public']['board_commands_executed'])
            self.assertTrue(all('-s' not in call for call in runner.calls))
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
            self.assertFalse(any(call[0] == '-s' for call in runner.calls))

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
