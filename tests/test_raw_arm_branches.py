import copy
import hashlib
import struct
import unittest

from tools.check_raw_arm_branches import branch, inspect


def fixture():
    # Original assembled fixture: unsigned x<4 ? 3*x+7 : -1.
    data = bytes.fromhex('040050e30100003a0000e0e31eff2fe1800080e0070080e21eff2fe1')
    record = {'input_bytes': len(data), 'input_sha256': hashlib.sha256(data).hexdigest(),
              'analysis_image_base': 0x100000,
              'branch_sites': [{'file_offset': 4, 'target_file_offset': 16, 'link': False,
                                'condition_id': 3, 'instruction_sha256': hashlib.sha256(data[4:8]).hexdigest()}]}
    return data, record


class RawArmBranchTests(unittest.TestCase):
    def test_original_control_and_coordinate_translation(self):
        data, record = fixture()
        self.assertEqual(hashlib.sha256(data).hexdigest(),
                         '786175195116c0d52f3103c8db616f896e3806f4e603f980f0793ccf215cbcac')
        first = inspect(data, record)
        record['analysis_image_base'] = 0
        self.assertEqual(inspect(data, record), first)
        self.assertEqual(first['checked_branches'][0]['target_file_offset'], 16)
        self.assertFalse(first['boot_or_recovery_qualified'])

    def test_signed_branch_and_link_bit(self):
        self.assertEqual(branch(bytes.fromhex('feffffea'), 0x1000), (0x1000, False, 14))
        self.assertEqual(branch(bytes.fromhex('feffffeb'), 0x1000), (0x1000, True, 14))
        self.assertEqual(branch(bytes.fromhex('000000ea'), 0x1000), (0x1008, False, 14))

    def test_rejects_non_a32_branch_interworking_and_wrapping(self):
        for raw, at in [(b'\0'*4, 0), (bytes.fromhex('000000fa'), 0),
                        (bytes.fromhex('1eff2fe1'), 0), (bytes.fromhex('00f000f8'), 0),
                        (bytes.fromhex('feffffea'), 1), (b'\0', 0),
                        (struct.pack('<I', 0xea800000), 0),
                        (struct.pack('<I', 0xea7fffff), 0xfffffff0)]:
            with self.subTest(raw=raw, at=at), self.assertRaises(ValueError):
                branch(raw, at)

    def test_digest_bounds_duplicates_and_encoding_mismatches(self):
        data, original = fixture()
        for key, value in [('file_offset', -4), ('file_offset', 5),
                           ('target_file_offset', 28), ('target_file_offset', 20),
                           ('link', True), ('condition_id', 14), ('instruction_sha256', '0'*64)]:
            record = copy.deepcopy(original)
            record['branch_sites'][0][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                inspect(data, record)
        for mutate in ('digest', 'mapping', 'duplicate', 'empty'):
            record = copy.deepcopy(original)
            if mutate == 'digest': record['input_sha256'] = '0'*64
            elif mutate == 'mapping': record['analysis_image_base'] = 0xffffffff
            elif mutate == 'duplicate': record['branch_sites'] *= 2
            else: record['branch_sites'] = []
            with self.subTest(mutate=mutate), self.assertRaises(ValueError):
                inspect(data, record)
