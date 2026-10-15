import io
import tempfile
import unittest
from pathlib import Path
import zipfile
import struct
from tools.inspect_update_container import inspect, scan, msdu11_table


class UpdateContainerTests(unittest.TestCase):
    def test_msdu11_ranges_and_table_budgets(self):
        data = (struct.pack('<6s4I', b'MSDU11', 0, 0, 0, 2)
                + struct.pack('<IQQ', 1, 99, 5) + struct.pack('<IQQ', 2, 104, 8)
                + struct.pack('<I', 1) + struct.pack('<QIB', 83, 16, 4) + b'TEST')
        result = msdu11_table(data, 112)
        self.assertTrue(result['data_ranges_cover_remainder'])
        self.assertFalse(result['table_authenticated'])
        for corrupted, size in ((data[:-1], 112), (data, 111),
                                (data[:18] + struct.pack('<I', 65) + data[22:], 112),
                                (data[:42] + struct.pack('<IQQ', 2, 100, 8) + data[62:], 112),
                                (data[:42] + struct.pack('<IQQ', 1, 104, 8) + data[62:], 112)):
            with self.assertRaises(ValueError):
                msdu11_table(corrupted, size)

    def test_marker_scan_handles_boundaries_without_double_counting(self):
        data = b'MSDU11' + b'x' * 5 + b'Salted__' + b'\x7fELF' + b'Salted__'
        for size in (1, 4, 8, 64):
            result = scan(io.BytesIO(data), len(data), chunk_size=size)
            self.assertEqual(result['marker_candidates']['openssl_salted']['first_offsets'], [11, 23])
            self.assertEqual(result['marker_candidates']['elf']['count'], 1)
        with self.assertRaises(ValueError):
            scan(io.BytesIO(data), len(data) - 1)

    def test_update_integrity_and_path_bounds(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'synthetic.zip'
            with zipfile.ZipFile(path, 'w') as archive:
                archive.writestr('image/update', b'MSDU11synthetic')
            result = inspect(path)
            self.assertTrue(result['members'][0]['zip_crc_checked'])
            self.assertFalse(result['firmware_reconstructed'])
            self.assertFalse((Path(directory) / 'image').exists())
            for name in ('../escape', '/absolute', 'a\\b', 'a\nb'):
                with zipfile.ZipFile(path, 'w') as archive:
                    archive.writestr(name, b'data')
                with self.assertRaises(ValueError):
                    inspect(path)

    def test_crc_damage_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'synthetic.zip'
            with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_STORED) as archive:
                archive.writestr('image/update', b'UNIQUE_SYNTHETIC_BYTES')
            path.write_bytes(path.read_bytes().replace(b'UNIQUE_SYNTHETIC_BYTES', b'CHANGED_SYNTHETIC_BYTE'))
            with self.assertRaises(zipfile.BadZipFile):
                inspect(path)
