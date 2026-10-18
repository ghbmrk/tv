import json
import os
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib
from pathlib import Path
from unittest.mock import patch

from test_update_metadata import gpt_bytes, vdfs_bytes
from tools.inspect_vdfs_catalog import inspect, main, crc


def node(identifier, kind, records, prev=0, nxt=0):
    b = bytearray(16384)
    b[:4] = b'Nd\0\0'
    struct.pack_into('<2I2H4I', b, 4, 1, 0, 0, len(records), identifier, prev, nxt, kind)
    at = 32
    for i, record in enumerate(records):
        b[at:at+len(record)] = record
        struct.pack_into('<I', b, 16376-4*i, at)
        at += len(record)
    struct.pack_into('<I', b, 16376-4*len(records), at)
    struct.pack_into('<I', b, 16380, crc(b[:-4]))
    return b


def record(name, child=None):
    name = name.encode()
    keylen = (26+len(name)+7)//8*8
    size = keylen+(312 if child is None else 8)
    b = bytearray(size)
    b[:4] = b'eFr\0'
    struct.pack_into('<HHQQBB', b, 4, keylen, size, 1, 99, 2, len(name))
    b[26:26+len(name)] = name
    if child is not None:
        struct.pack_into('<I', b, keylen, child)
    else:
        struct.pack_into('<H', b, keylen+32, 0o100755)
        struct.pack_into('<Q', b, keylen+80, 123)
    return b


def fix_node(b):
    struct.pack_into('<I', b, 16380, crc(b[:-4]))
    return b


def fixture():
    prefix = gpt_bytes(ranges=((8, 255), (256, 271)))
    prefix.extend(b'\0'*(20480-len(prefix)))
    struct.pack_into('<QQ', prefix, 536, 1, 287)
    struct.pack_into('<QQ', prefix, 552, 4, 285)
    struct.pack_into('<I', prefix, 600, zlib.crc32(prefix[1024:1280]))
    prefix[528:532] = b'\0'*4
    struct.pack_into('<I', prefix, 528, zlib.crc32(prefix[512:604]))
    volume = bytearray(vdfs_bytes())
    volume.extend(b'\0'*4096)
    table = bytearray(4096); table[:4] = b'CoWB'
    struct.pack_into('<IQ', table, 4, 1, 0)
    struct.pack_into('<Q', table, 16, 168)
    struct.pack_into('<Q', table, 24, 3)
    struct.pack_into('<Q', table, 64, 104)
    for i in range(4):
        struct.pack_into('<QII', table, 104+i*16, i*4, 1, 0)
    struct.pack_into('<I', table, 168, crc(table[:168]))
    volume[8192:12288] = table
    for base in (0, 4096):
        ex = bytearray(volume[base+1536:base+4096])
        struct.pack_into('<QQ', ex, 72, 2, 1)
        struct.pack_into('<QQ', ex, 88, 3, 16)
        struct.pack_into('<Q', ex, 1640, 30)
        struct.pack_into('<I', ex, 2556, crc(ex[:2556]))
        volume[base+1536:base+4096] = ex
        sb = bytearray(volume[base+1024:base+1536])
        struct.pack_into('<II', sb, 228, crc(ex[:2556]), crc(table[:168]))
        struct.pack_into('<I', sb, 508, crc(sb[:508]))
        volume[base+1024:base+1536] = sb
    prefix[4096:4096+len(volume)] = volume
    head = bytearray(16384); head[:4] = b'eHND'
    struct.pack_into('<2IIH', head, 4, 1, 0, 1, 2)
    data = fix_node(head) + node(1, 1, [record('a', 2), record('b', 3)])
    data += node(2, 2, [record('libcapi-drm-widevinecdm.so.0.1.1')], nxt=3)
    data += node(3, 2, [record('PRIVATE_CATALOG_NAME')], prev=2)
    return prefix, data, 288*512


class VdfsCatalogTests(unittest.TestCase):
    def test_checked_graph_exports_only_fixed_targets_and_no_content_claim(self):
        prefix, data, size = fixture()
        result = inspect(prefix, data, size)
        self.assertEqual(result['catalog_nodes'], 4)
        self.assertEqual(result['leaf_records'], 2)
        self.assertEqual(result['selected_files'][0]['declared_file_bytes'], 123)
        self.assertNotIn('PRIVATE_CATALOG_NAME', json.dumps(result))
        for key in ('file_contents_validated', 'signature_verified', 'installed_variant_verified', 'boot_or_recovery_qualified'):
            self.assertFalse(result[key])

    def test_refuses_crc_damage_truncation_geometry_and_snapshot_mismatch(self):
        p, d, s = fixture()
        for at in (0, 16380, 16384, len(d)-1):
            b = bytearray(d); b[at] ^= 1
            with self.subTest(at=at), self.assertRaises(ValueError):
                inspect(p, b, s)
        for prefix, data, size in ((p, d[:-1], s), (p[:12000], d, s), (p, d, s-1)):
            with self.assertRaises(ValueError):
                inspect(prefix, data, size)
        b = bytearray(d); struct.pack_into('<I', b, 4, 2); b[:16384] = fix_node(b[:16384])
        with self.assertRaises(ValueError):
            inspect(p, b, s)

    def test_rejects_graph_aliases_cycles_unreachable_nodes_and_wrong_height(self):
        p, d, s = fixture()
        cases = []
        for targets in ((2, 2), (1, 3), (2, 1)):
            b = bytearray(d); b[16384:32768] = node(1, 1, [record('a', targets[0]), record('b', targets[1])]); cases.append(b)
        b = bytearray(d); struct.pack_into('<H', b, 16, 3); b[:16384] = fix_node(b[:16384]); cases.append(b)
        b = bytearray(d); b[49152:] = node(3, 2, [record('x')], prev=0); cases.append(b)
        for b in cases:
            with self.assertRaises(ValueError):
                inspect(p, b, s)

    def test_rejects_record_overlap_bad_fields_and_ambiguous_target(self):
        p, d, s = fixture(); cases = []
        for offset, fmt, value in ((14, '<H', 513), (16, '<I', 99), (16376, '<I', 16380), (32+4, '<H', 1), (32+25, '<B', 255)):
            b = bytearray(d); n = bytearray(b[32768:49152]); struct.pack_into(fmt, n, offset, value); b[32768:49152] = fix_node(n); cases.append(b)
        b = bytearray(d); b[49152:] = node(3, 2, [record('libcapi-drm-widevinecdm.so.0.1.1')], prev=2); cases.append(b)
        for b in cases:
            with self.assertRaises(ValueError):
                inspect(p, b, s)

    def test_cli_runs_directly_and_preserves_input_aliases(self):
        p, d, s = fixture()
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); prefix = root/'prefix.json'; prefix.write_bytes(p)
            metadata = root/'metadata.bin'; metadata.write_bytes(d); out = root/'out.json'
            args = ['tools/inspect_vdfs_catalog.py', '--platform-prefix', str(prefix), '--metadata', str(metadata), '--image-bytes', str(s), '--output', str(out)]
            run = subprocess.run([sys.executable]+args, capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertEqual(json.loads(out.read_text())['catalog_nodes'], 4)
            alias = root/'alias.json'; os.link(prefix, alias)
            link = root/'link.json'; link.symlink_to(prefix)
            for output in (prefix, alias, link):
                with patch('sys.argv', args[:-1]+[str(output)]), self.assertRaises(ValueError):
                    main()
            self.assertEqual(prefix.read_bytes(), p)
            self.assertEqual(metadata.read_bytes(), d)
