import hashlib
import struct
import unittest
from unittest.mock import patch

from tools.inspect_fip_table import inspect


def fixture(magic=0xaa320001):
    data = bytearray(256)
    struct.pack_into('<IIQ', data, 0, magic, 1, 0)
    struct.pack_into('<16sQQQ', data, 16, b'a'*16, 192, 32, 0)
    struct.pack_into('<16sQQQ', data, 56, b'b'*16, 224, 32, 0)
    struct.pack_into('<16sQQQ', data, 96, b'\0'*16, 256, 0, 0)
    data[192:224] = b'private-payload-canary'.ljust(32, b'\0')
    data[224:256] = b'other-private-canary'.ljust(32, b'\0')
    return data


class FipTableTests(unittest.TestCase):
    def test_checked_ranges_do_not_claim_standard_compatibility_or_roles(self):
        data = fixture()
        result = inspect(data)
        self.assertFalse(result['matches_upstream_tfa_magic'])
        self.assertEqual(result['header_and_terminated_table_bytes'], 136)
        self.assertEqual(result['uninterpreted_gap_or_padding_bytes'], 56)
        self.assertEqual(result['entries'][0]['payload_sha256'], hashlib.sha256(data[192:224]).hexdigest())
        self.assertIsNone(result['entries'][0]['role'])
        self.assertNotIn('private-payload', str(result))
        self.assertNotIn('a'*16, str(result))
        self.assertFalse(result['boot_or_recovery_qualified'])
        self.assertTrue(inspect(fixture(0xaa640001))['matches_upstream_tfa_magic'])

    def test_refuses_ranges_overlap_duplicates_and_bad_terminators(self):
        for offset, fmt, value in ((0, '<I', 0), (4, '<I', 0), (32, '<Q', 128),
                                   (32, '<Q', 250), (40, '<Q', 2**64-1),
                                   (72, '<Q', 208), (112, '<Q', 255),
                                   (120, '<Q', 1), (128, '<Q', 1)):
            data = fixture(); struct.pack_into(fmt, data, offset, value)
            with self.subTest(offset=offset, value=value), self.assertRaises(ValueError):
                inspect(data)
        data = fixture(); data[56:72] = data[16:32]
        with self.assertRaises(ValueError): inspect(data)
        for data in (fixture()[:55], fixture()[:100], fixture()[:-1]):
            with self.assertRaises(ValueError): inspect(data)

    def test_budgets_missing_terminator_and_empty_table(self):
        with patch('tools.inspect_fip_table.MAX_BYTES', 128):
            with self.assertRaises(ValueError): inspect(fixture())
        with patch('tools.inspect_fip_table.MAX_ENTRIES', 1):
            with self.assertRaises(ValueError): inspect(fixture())
        data = fixture(); data[96:112] = b'c'*16
        with self.assertRaises(ValueError): inspect(data)
        data = fixture(); struct.pack_into('<16sQQQ', data, 16, b'\0'*16, len(data), 0, 0)
        with self.assertRaises(ValueError): inspect(data)
