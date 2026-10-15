import io
import stat
import tarfile
import unittest
import zipfile
from unittest.mock import patch

from tools.inspect_platform_dependencies import inspect_package


class PlatformDependencyTests(unittest.TestCase):
    def zip_data(self, entries):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, 'w') as archive:
            for path, data in entries:
                archive.writestr(path, data)
        return stream.getvalue()

    def test_reports_locations_without_source_text_or_device_claims(self):
        result = inspect_package('test.zip', self.zip_data([
            ('selected.c', b'private canary\xff\n smc #0\n'), ('other.c', 'ignored')]), ['selected.c'])
        item = result['selected_files'][0]
        self.assertEqual(item['lexical_markers']['secure_monitor_instruction'][0]['line'], 2)
        self.assertNotIn('private canary', str(result))
        self.assertEqual(len(item['sha256']), 64)

    def test_rejects_traversal_missing_file_and_expansion(self):
        for entries in [[('../bad', 'x')], [('other', 'x')]]:
            with self.assertRaises(ValueError):
                inspect_package('test.zip', self.zip_data(entries), ['selected'])
        with patch('tools.inspect_platform_dependencies.MAX_EXPANDED', 2):
            with self.assertRaises(ValueError):
                inspect_package('test.zip', self.zip_data([('selected', 'abc')]), ['selected'])

    def test_rejects_selected_zip_symlink(self):
        entry = zipfile.ZipInfo('selected')
        entry.create_system = 3
        entry.external_attr = (stat.S_IFLNK | 0o777) << 16
        with self.assertRaises(ValueError):
            inspect_package('test.zip', self.zip_data([(entry, 'elsewhere')]), ['selected'])

    def test_rejects_selected_tar_link_and_duplicate(self):
        for kind in ['link', 'duplicate']:
            stream = io.BytesIO()
            with tarfile.open(fileobj=stream, mode='w:gz') as archive:
                item = tarfile.TarInfo('selected')
                if kind == 'link':
                    item.type = tarfile.SYMTYPE
                    item.linkname = 'elsewhere'
                    archive.addfile(item)
                else:
                    item.size = 1
                    archive.addfile(item, io.BytesIO(b'x'))
                    archive.addfile(item, io.BytesIO(b'y'))
            with self.assertRaises(ValueError):
                inspect_package('test.tar.gz', stream.getvalue(), ['selected'])


if __name__ == '__main__':
    unittest.main()
