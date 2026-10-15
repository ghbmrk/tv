import io
import tarfile
import unittest
from tools.inspect_kernel_source import inspect


def archive(name, data=b'', kind=tarfile.REGTYPE):
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode='w:gz') as output:
        member = tarfile.TarInfo(name)
        member.type = kind
        member.size = len(data) if kind == tarfile.REGTYPE else 0
        output.addfile(member, io.BytesIO(data))
    stream.seek(0)
    return stream


class KernelSourceTests(unittest.TestCase):
    def test_reports_config_provenance_without_extracting_source(self):
        stream = archive('linux-5.4/arch/arm/configs/PONTUSM_release_defconfig',
                         b'CONFIG_ARM=y\n# CONFIG_ANDROID_BINDER_IPC is not set\nCONFIG_SDP_EXAMPLE=y\n')
        result = inspect(stream)
        record = result['selected_metadata'][0]
        self.assertEqual(record['selected_config_values']['CONFIG_ARM'], 'y')
        self.assertEqual(record['selected_config_values']['CONFIG_ANDROID_BINDER_IPC'], 'not_set')
        self.assertEqual(record['platform_config_values'], {'CONFIG_SDP_EXAMPLE': 'y'})
        self.assertEqual(len(record['sha256']), 64)
        self.assertFalse(result['files_extracted'])

    def test_version_parser_does_not_consume_next_line(self):
        result = inspect(archive('linux-5.4/Makefile',
                                b'VERSION = 5\nSUBLEVEL = 261\nEXTRAVERSION =\nNAME = Example\n'))
        self.assertEqual(result['selected_metadata'][0]['version_fields'],
                         {'VERSION': '5', 'SUBLEVEL': '261', 'EXTRAVERSION': ''})

    def test_refuses_unsafe_paths_links_and_budgets(self):
        for name in ('../escape', '/absolute', 'a\\b', 'a\nb'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                inspect(archive(name))
        with self.assertRaises(ValueError):
            inspect(archive('linux-5.4/Makefile', kind=tarfile.SYMTYPE))
        with self.assertRaises(ValueError):
            inspect(archive('irrelevant', b'large'), expanded_limit=4)
        with self.assertRaises(ValueError):
            inspect(archive('irrelevant'), member_limit=0)
