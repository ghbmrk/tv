import copy
import hashlib
import struct
import unittest

from tools.check_native_calls import blx_target, inspect


def fixture():
    data = bytearray(256)
    data[:7] = b'\x7fELF\x01\x01\x01'
    struct.pack_into('<HH5I6H', data, 16, 3, 40, 1, 0, 52, 0, 0, 52, 32, 1, 0, 0, 0)
    struct.pack_into('<8I', data, 52, 1, 0, 0, 0, 256, 256, 5, 4096)
    data[128:132] = bytes.fromhex('00f000e8')  # BLX with zero displacement.
    record = {'decoded_sha256': hashlib.sha256(data).hexdigest(), 'analysis_image_base': 65536,
              'call_sites': [{'address': '0x10080', 'file_offset': '0x80', 'target': '0x10084',
                              'instruction_sha256': hashlib.sha256(data[128:132]).hexdigest()}]}
    return data, record


class NativeCallsTest(unittest.TestCase):
    def test_forward_backward_and_aligned_pc(self):
        self.assertEqual(blx_target(bytes.fromhex('00f000e8'), 0x1000), 0x1004)
        self.assertEqual(blx_target(bytes.fromhex('00f000e8'), 0x1002), 0x1004)
        self.assertEqual(blx_target(bytes.fromhex('fff7feef'), 0x1000), 0x1000)

    def test_refuse_other_encodings_and_bad_addresses(self):
        for raw, at in [(b'\0'*4, 0x1000), (bytes.fromhex('00f000f8'), 0x1000),
                        (bytes.fromhex('00f001e8'), 0x1000), (b'\0', 0x1000),
                        (bytes.fromhex('00f000e8'), 1)]:
            with self.subTest(raw=raw, address=at), self.assertRaises(ValueError):
                blx_target(raw, at)

    def test_rebase_and_original_file_coordinates(self):
        data, record = fixture()
        result = inspect(data, record)
        self.assertEqual(result['analysis_rebase_bytes'], 65536)
        self.assertEqual(result['checked_calls'][0]['file_offset'], '0x80')
        self.assertFalse(result['executed'])

    def test_mismatch_refusals(self):
        data, original = fixture()
        for field, value in [('address', '0x10082'), ('file_offset', '0x10080'),
                             ('target', '0x10088'), ('instruction_sha256', '0'*64)]:
            record = copy.deepcopy(original)
            record['call_sites'][0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                inspect(data, record)
        data[132] = 1
        with self.assertRaisesRegex(ValueError, 'input digest'):
            inspect(data, original)

    def test_ambiguous_nonexecuting_or_out_of_bounds_segments(self):
        for kind in ('duplicate', 'nonexec', 'bounds', 'wrongmachine'):
            data, record = fixture()
            if kind == 'duplicate':
                struct.pack_into('<H', data, 44, 2)
                data[84:116] = data[52:84]
            elif kind == 'nonexec':
                struct.pack_into('<I', data, 76, 4)
            elif kind == 'bounds':
                struct.pack_into('<I', data, 68, 257)
            else:
                struct.pack_into('<H', data, 18, 183)
            record['decoded_sha256'] = hashlib.sha256(data).hexdigest()
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                inspect(data, record)

    def test_empty_or_duplicate_call_inventory(self):
        data, record = fixture()
        record['call_sites'] *= 2
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            inspect(data, record)
        record['call_sites'] = []
        with self.assertRaisesRegex(ValueError, 'call count'):
            inspect(data, record)
