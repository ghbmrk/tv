import tempfile
import unittest
from pathlib import Path
import zipfile
from tools.index_source import index


class SourceIndexTests(unittest.TestCase):
    def test_indexes_nested_source_without_extracting_it(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'synthetic.zip'
            with zipfile.ZipFile(path, 'w') as archive:
                archive.writestr('kernel/arch/arm/configs/example_defconfig', 'CONFIG_EXAMPLE=y')
                archive.writestr('other/file.txt', 'data')
            result = index(path)
            self.assertEqual(result['member_count'], 2)
            self.assertEqual(result['candidate_count'], 1)
            self.assertFalse(result['extracted'])
            self.assertFalse((Path(directory) / 'kernel').exists())
            self.assertEqual(len(result['sha256']), 64)

    def test_refuses_traversal_absolute_and_control_character_paths(self):
        for name in ('../board.txt', '/board.txt', 'dir\\board.txt', 'board\n.txt'):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / 'synthetic.zip'
                with zipfile.ZipFile(path, 'w') as archive:
                    archive.writestr(name, 'data')
                with self.assertRaises(ValueError):
                    index(path)
