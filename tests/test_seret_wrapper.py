import hashlib
import struct
import unittest
from unittest.mock import patch
import zlib

from tests.test_update_metadata import fdt_bytes
from tools.inspect_seret_wrapper import envelope, inspect


def packed(data):
    encoder = zlib.compressobj(wbits=-15)
    return encoder.compress(data) + encoder.flush()


def fixture(plain=None, trailing=b''):
    if plain is None: plain = b'private-canary00' + fdt_bytes()
    stream = packed(plain) + trailing
    image = bytearray(64)
    struct.pack_into('<15I', image, 0, *((0xe1a00000,)*8 +
                     (0xea000005, 0x016f2818, 0, 64, 0x04030201, 0x45454545, 60)))
    return bytes(image) + struct.pack('<III', 0x2020, len(plain), len(stream)) + stream


class SeretWrapperTests(unittest.TestCase):
    def test_checks_real_structure_without_exporting_payload_or_addresses(self):
        data = fixture()
        result = inspect(data)
        tail = result['post_image_envelope']
        self.assertEqual(tail['file_offset'], 64)
        self.assertEqual(len(tail['dtb_bundle']['fdts']), 1)
        self.assertEqual(tail['decoded_sha256'], hashlib.sha256(b'private-canary00'+fdt_bytes()).hexdigest())
        self.assertNotIn('private-canary', str(result))
        self.assertNotIn('contained_xz_candidate_indices', result['zimage'])
        self.assertFalse(result['boot_or_recovery_qualified'])

    def test_rejects_truncation_declared_sizes_trailing_and_non_dtb(self):
        data = fixture()
        cases = [data[:-1], fixture(trailing=b'extra'), fixture(b'not a device tree'),
                 fixture(fdt_bytes(duplicate=True))]
        for offset, value in ((64, 0), (68, 0), (68, 2**32-1), (68, 1),
                              (68, 1000), (72, 0), (72, 2**32-1)):
            changed = bytearray(data)
            struct.pack_into('<I', changed, offset, value)
            cases.append(changed)
        for case in cases:
            with self.subTest(size=len(case)), self.assertRaises(ValueError):
                inspect(case)

    def test_limits_expansion_and_ambiguous_image_candidates(self):
        data = fixture(b'x' * 1024)
        with patch('tools.inspect_seret_wrapper.MAX_DECODED', 128):
            with self.assertRaises(ValueError): inspect(data)
        with self.assertRaises(ValueError): inspect(fixture()+fixture())
        for offset in (-1, len(data)-11, True):
            with self.assertRaises(ValueError): envelope(data, offset)
