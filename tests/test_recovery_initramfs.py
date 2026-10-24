import lzma
import stat
import struct
import unittest
from unittest.mock import patch

from tools.inspect_recovery_initramfs import inspect, newc


def member(name, data=b'', mode=stat.S_IFREG | 0o644, *, links=1):
    name = name.encode()+b'\0'
    fields = [1, mode, 0, 0, links, 0, len(data), 0, 0, 0, 0, len(name), 0]
    result = b'070701'+b''.join(f'{value:08x}'.encode() for value in fields)+name
    result += b'\0'*(-len(result) % 4)
    result += data
    return result+b'\0'*(-len(result) % 4)


def archive(*members):
    return b''.join(members)+member('TRAILER!!!')+b'\0'*16


def elf():
    data = bytearray(52)
    data[:7] = b'\x7fELF\x01\x01\x01'
    struct.pack_into('<H', data, 18, 40)
    struct.pack_into('<H', data, 40, 52)
    return bytes(data)


class RecoveryInitramfsTests(unittest.TestCase):
    def test_nested_archive_metadata_and_private_omission(self):
        data = archive(member('bin/upgrade_mgr', elf()), member('bin/toybox', elf()),
                       member('init', b'/bin/toybox\0', stat.S_IFLNK | 0o777),
                       member('etc/inittab', b'::sysinit:-/etc/init.d/rcS\n'),
                       member('etc/init.d/rcS', b'#!/bin/sh\nupgrade_mgr\n'),
                       member('private-path-canary', b'private-data-canary'),
                       member('dev', mode=stat.S_IFDIR | 0o755),
                       member('dev/hidden-device', mode=stat.S_IFCHR | 0o600))
        result = inspect(b'prefix'+lzma.compress(data, check=lzma.CHECK_CRC32)+b'tail')
        row = result['xz_candidates'][0]
        self.assertEqual(row['file_offset'], 6)
        self.assertTrue(row['validated'])
        self.assertEqual(row['archive']['members'], 8)
        selected = {r['path']: r for r in row['archive']['selected_members']}
        self.assertEqual(selected['bin/upgrade_mgr']['elf_header']['machine_id'], 40)
        self.assertTrue(selected['init']['targets_bin_toybox'])
        self.assertTrue(selected['etc/init.d/rcS']['standalone_upgrade_mgr_line'])
        self.assertTrue(selected['etc/inittab']['sysinit_rcs_line'])
        self.assertNotIn('private-', str(result))
        self.assertNotIn('hidden-device', str(result))
        self.assertFalse(result['recovery_qualified'])
        self.assertFalse(result['payload_exported'])

    def test_rejects_paths_duplicates_hardlinks_and_invalid_types(self):
        cases = [archive(member(name)) for name in ('../escape', '/absolute', 'a/../b',
                                                    './init', 'a//b', 'a\\b', 'a\nb', '.')]
        cases += [archive(member('init'), member('init')),
                  archive(member('lib', mode=stat.S_IFDIR), member('lib/', mode=stat.S_IFDIR)),
                  archive(member('file', links=2)), archive(member('file', links=0)),
                  archive(member('device', b'not-empty', stat.S_IFBLK)),
                  archive(member('init', mode=stat.S_IFLNK)),
                  archive(member('unknown', mode=0))]
        for data in cases:
            with self.subTest(size=len(data)), self.assertRaises(ValueError):
                newc(data)
        self.assertEqual(newc(archive(member('lib/', mode=stat.S_IFDIR)))['members'], 1)

    def test_rejects_bounds_header_fields_padding_and_missing_trailer(self):
        valid = archive(member('init', b'x'))
        cases = [valid[:109], valid[:-len(member('TRAILER!!!'))-16],
                 valid+archive(), valid+b'nonzero', member('TRAILER!!!', b'x')]
        for start, value in ((0, b'070702'), (6, b'zzzzzzzz'),
                             (54, b'ffffffff'), (94, b'ffffffff'), (102, b'00000001')):
            changed = bytearray(valid)
            changed[start:start+len(value)] = value
            cases.append(changed)
        # Name and data alignment padding, plus name termination.
        for index in (114, 115, 117):
            changed = bytearray(valid)
            changed[index] = ord('x')
            cases.append(changed)
        for data in cases:
            with self.subTest(size=len(data)), self.assertRaises(ValueError): newc(data)
        with patch('tools.inspect_recovery_initramfs.MAX_MEMBERS', 1):
            with self.assertRaises(ValueError): newc(archive(member('a'), member('b')))

    def test_no_integrity_incomplete_bad_and_nonarchive_streams(self):
        data = archive(member('init'))
        for stream, rejection in (
                (lzma.compress(data, check=lzma.CHECK_NONE), 'integrity_check_required'),
                (lzma.compress(data)[:-10], 'incomplete_or_output_limited_xz'),
                (b'\xfd7zXZ\0'+b'broken', 'invalid_or_memory_limited_xz')):
            result = inspect(stream)['xz_candidates'][0]
            self.assertFalse(result['validated'])
            self.assertEqual(result['rejection'], rejection)
        result = inspect(lzma.compress(b'not cpio'))['xz_candidates'][0]
        self.assertTrue(result['validated'])
        self.assertNotIn('archive', result)
        self.assertEqual(inspect(b'070701')['xz_candidates'], [])

    def test_resource_limits_and_unsupported_selected_elf(self):
        with patch('tools.inspect_recovery_initramfs.MAX_DECODED', 128):
            row = inspect(lzma.compress(b'x'*1024))['xz_candidates'][0]
            self.assertEqual(row['rejection'], 'incomplete_or_output_limited_xz')
        with self.assertRaises(ValueError): inspect(b'\xfd7zXZ\0'*17)
        with self.assertRaises(ValueError): newc(archive(member('bin/upgrade_mgr', b'\x7fELF')))
        with self.assertRaises(ValueError): inspect(b'')

    def test_commented_or_partial_commands_are_not_startup_lines(self):
        r = newc(archive(member('etc/init.d/rcS', b'#upgrade_mgr\nupgrade_mgr_extra\n'),
                         member('init', b'/private-target', stat.S_IFLNK)))
        self.assertFalse(r['selected_members'][0]['standalone_upgrade_mgr_line'])
        self.assertFalse(r['selected_members'][1]['targets_bin_toybox'])
        self.assertNotIn('/private-target', str(r))


if __name__ == '__main__':
    unittest.main()
