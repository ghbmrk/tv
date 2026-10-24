import io
import json
import unittest
import zipfile
from tools.inspect_media_source import inspect, inspect_gpu, PREFIX, SELECTED, GPU_PREFIX, GPU_SELECTED


def fixture(duplicate=False, missing=False, oversize=False):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w', compression=zipfile.ZIP_DEFLATED) as z:
        for name in SELECTED:
            if missing and name == 'Makefile':
                continue
            data = b'VENDOR-PRIVATE-CANARY\n'
            if name == 'sdp_cm7_top.c':
                data += b'DEFINE_SIMPLE_ATTRIBUTE(cm7_dbg_ew_test_fops, cm7_dbg_ew_test_show, NULL, "%llu");\n'
                data += b'debugfs_create_file("ew_test", 0444, dir, NULL, &cm7_dbg_ew_test_fops);\n'
                data += b'memcpy_toio(destination, microcode, length);\n'
            if oversize and name == 'Makefile':
                data = b'x' * (2 * 1024**2 + 1)
            z.writestr(PREFIX + name, data)
        if duplicate:
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter('ignore')
                z.writestr(PREFIX + 'Makefile', b'duplicate')
    stream.seek(0)
    return zipfile.ZipFile(stream)


class MediaSourceTests(unittest.TestCase):
    def test_gpu_scope_keeps_source_text_private(self):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, 'w') as z:
            for name in GPU_SELECTED:
                z.writestr(GPU_PREFIX+name, b'private-canary\n{ .compatible = "arm,mali-midgard" },\n')
        stream.seek(0)
        with zipfile.ZipFile(stream) as z:
            result = inspect_gpu(z)
        self.assertEqual(len(result['selected_files']), 4)
        self.assertNotIn('private-canary', json.dumps(result))
        self.assertTrue(result['selected_crc_checked'])
        self.assertEqual(result['selected_files'][0]['lexical_markers']
                         ['generic_gpu_compatible'][0]['line'], 2)

    def test_records_read_callback_and_side_effect_locations_without_source_text(self):
        with fixture() as z:
            result = inspect(z)
        text = json.dumps(result)
        self.assertNotIn('VENDOR-PRIVATE-CANARY', text)
        self.assertFalse(result['device_accessed'])
        self.assertFalse(result['code_executed'])
        record = next(r for r in result['selected_files'] if r['path'].endswith('sdp_cm7_top.c'))
        self.assertEqual(record['lexical_markers']['microcode_transfer'][0]['line'], 4)
        self.assertEqual(record['lexical_markers']['read_permission_debug_entry'][0]['line'], 3)
        self.assertEqual(len(record['sha256']), 64)

    def test_refuses_missing_duplicate_and_oversized_members(self):
        for option in ('missing', 'duplicate', 'oversize'):
            with self.subTest(option=option), fixture(**{option: True}) as z, self.assertRaises(ValueError):
                inspect(z)
