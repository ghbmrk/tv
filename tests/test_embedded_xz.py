import hashlib
import lzma
import struct
import unittest
from unittest.mock import patch

from tools.inspect_embedded_xz import inspect, MAGIC


class EmbeddedXZTests(unittest.TestCase):
    def zimage(self, payload):
        image = bytearray(64 + len(payload))
        struct.pack_into('<15I', image, 0, *((0xe1a00000,) * 8 +
                         (0xea000005, 0x016f2818, 0, len(image),
                          0x04030201, 0x45454545, 60)))
        image[64:] = payload
        return image

    def test_header_range_binds_only_wholly_contained_valid_streams(self):
        packed = lzma.compress(b'Linux version 5.4.261 private-canary')
        image = self.zimage(packed)
        result = inspect(b'prefix00' + image + packed)
        row = result['arm_zimage_candidates'][0]
        self.assertTrue(row['validated'])
        self.assertEqual(row['offset'], 8)
        self.assertEqual(row['image_bytes'], len(image))
        self.assertEqual(row['image_sha256'], hashlib.sha256(image).hexdigest())
        self.assertEqual(row['contained_xz_candidate_indices'], [0])
        self.assertNotIn('private-canary', str(result))
        self.assertFalse(result['signature_authenticated'])
        self.assertFalse(result['boot_or_recovery_qualified'])

        # A valid stream straddling the declared image end is not bound to it.
        struct.pack_into('<I', image, 44, 68)
        self.assertEqual(inspect(image)['arm_zimage_candidates'][0]
                         ['contained_xz_candidate_indices'], [])

    def test_false_magic_unsupported_headers_and_truncation_never_validate(self):
        base = self.zimage(b'synthetic only' * 8)
        cases = [b'\x18\x28\x6f\x01', b'x' + base, base[:59]]
        for field, value in ((0, 0), (32, 0), (40, 0x1000), (44, 0xffffffff),
                             (48, 0), (52, 0), (56, 0), (56, len(base))):
            image = bytearray(base)
            struct.pack_into('<I', image, field, value)
            cases.append(image)
        for image in cases:
            with self.subTest(size=len(image)):
                for row in inspect(image)['arm_zimage_candidates']:
                    self.assertFalse(row['validated'])
                    self.assertNotIn('image_sha256', row)
        with self.assertRaises(ValueError):
            inspect(b'\x18\x28\x6f\x01' * 65)

    def test_embedded_stream_checks_integrity_and_omits_private_text(self):
        plain = b'Linux version 5.4.261 private-build-host\0credential-canary'
        packed = lzma.compress(plain, check=lzma.CHECK_CRC32)
        source = MAGIC + b'bad header and prefix' + packed + b'trailing container bytes'
        result = inspect(source)
        self.assertFalse(result['candidates'][0]['validated'])
        row = result['candidates'][1]
        self.assertTrue(row['validated'])
        self.assertEqual(row['decoded_sha256'], hashlib.sha256(plain).hexdigest())
        self.assertEqual(row['stored_stream_bytes'], len(packed))
        self.assertEqual(row['linux_version_tokens'], ['5.4.261'])
        self.assertNotIn('private-build-host', str(result))
        self.assertNotIn('credential-canary', str(result))
        self.assertFalse(result['boot_or_recovery_qualified'])

    def test_rejects_corrupt_footer_and_truncated_stream(self):
        packed = lzma.compress(b'original synthetic payload')
        corrupt = bytearray(packed)
        corrupt[-5] ^= 1
        for source in (bytes(corrupt), packed[:-8]):
            row = inspect(source)['candidates'][0]
            self.assertFalse(row['validated'])
            self.assertNotIn('decoded_sha256', row)

    def test_bounds_expansion_and_candidate_count(self):
        packed = lzma.compress(b'x' * 1024)
        with patch('tools.inspect_embedded_xz.MAX_OUTPUT', 128):
            self.assertEqual(inspect(packed)['candidates'][0]['rejection'], 'output_budget')
        with self.assertRaises(ValueError):
            inspect(MAGIC * 65)
        with patch('tools.inspect_embedded_xz.MAX_INPUT', 2):
            with self.assertRaises(ValueError):
                inspect(b'abc')

    def test_requires_payload_integrity_check(self):
        packed = lzma.compress(b'synthetic payload', check=lzma.CHECK_NONE)
        self.assertEqual(inspect(packed)['candidates'][0]['rejection'], 'integrity_check_required')

    def test_expansion_budget_is_shared_across_streams(self):
        packed = lzma.compress(b'x' * 64)
        with patch('tools.inspect_embedded_xz.MAX_OUTPUT', 100):
            rows = inspect(packed + packed + packed)['candidates']
        self.assertTrue(rows[0]['validated'])
        self.assertEqual(rows[1]['rejection'], 'output_budget')
        self.assertEqual(rows[2]['rejection'], 'output_budget')


if __name__ == '__main__':
    unittest.main()
