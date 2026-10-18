import hashlib
import json
import os
import struct
import tempfile
import unittest
import zlib
from pathlib import Path
from unittest.mock import patch

from tools.inspect_vdfs_library import decode, elf32, inspect, main


def elf():
    b = bytearray(512); b[:7] = b'\x7fELF\x01\x01\x01'
    struct.pack_into('<HH5I6H', b, 16, 3, 40, 1, 0, 52, 0, 0, 52, 32, 2, 0, 0, 0)
    struct.pack_into('<8I', b, 52, 1, 0, 0x1000, 0, 512, 512, 4, 4096)
    struct.pack_into('<8I', b, 84, 2, 128, 0x1080, 0, 40, 40, 4, 4)
    names = b'\0libc.so.6\0synthetic.so\0'; b[256:256+len(names)] = names
    for i, (tag, value) in enumerate(((5, 0x1100), (10, len(names)), (1, 1), (14, 11), (0, 0))):
        struct.pack_into('<iI', b, 128+i*8, tag, value)
    return b


def wrap(plain=None, flags=0, size=None, layout=6, log=9, chunk=None):
    plain = elf() if plain is None else bytes(plain)
    if chunk is None:
        chunk = plain if flags == 1 else zlib.compress(plain)
    chunk += b'\0'*(-len(chunk)%64)
    ext = struct.pack('<HHIQ', 0, flags, len(chunk), 0)
    desc = bytearray(40); desc[7] = 1; desc[8:12] = b'hZip'
    struct.pack_into('<HHQII', desc, 12, 1, layout, len(plain) if size is None else size, 0, log)
    hashes = hashlib.sha256(chunk).digest()+hashlib.sha256(desc).digest()
    check = ext+hashes+b'\0'*128+desc
    struct.pack_into('<I', desc, 24, zlib.crc32(check, 0xffffffff)^0xffffffff)
    return chunk+ext+hashes+b'\0'*128+desc


class VdfsLibraryTests(unittest.TestCase):
    def test_bounded_decode_and_static_dependencies_are_not_eligibility(self):
        result = inspect(wrap())
        self.assertEqual(result['elf']['needed_libraries'], ['libc.so.6'])
        self.assertEqual(result['elf']['soname'], 'synthetic.so')
        self.assertTrue(result['compression']['chunk_and_descriptor_hashes_match'])
        for key in ('executed', 'device_accessed', 'signature_verified', 'android_compatibility_verified', 'provider_or_quality_eligibility_verified'):
            self.assertFalse(result[key])
        self.assertNotIn('decoded', result)

    def test_refuses_encrypted_unsupported_corrupt_bomb_and_wrong_size(self):
        bad = [wrap(flags=2), wrap(layout=5), wrap(log=21), wrap(size=513),
               wrap(chunk=b'not zlib'), wrap(plain=b'x'*200000, size=512),
               wrap(chunk=zlib.compress(elf())+b'nonzero trailing data')]
        for at in (0, -40, -16, -200):
            b = bytearray(wrap()); b[at] ^= 1; bad.append(b)
        for b in bad:
            with self.subTest(size=len(b)), self.assertRaises(ValueError):
                inspect(b)
        with self.assertRaises(ValueError):
            decode(b'x'*(8*1024**2+1))

    def test_elf_refuses_ambiguous_tags_segments_strings_and_header_bounds(self):
        cases = []
        for at, fmt, value in ((4, '<B', 2), (18, '<H', 183), (28, '<I', 2**32-1), (44, '<H', 129),
                               (52+16, '<I', 2**32-1), (84+16, '<I', 7), (128+8, '<i', 5), (128+20, '<I', 255)):
            b = elf(); struct.pack_into(fmt, b, at, value); cases.append(b)
        b = elf(); b[257] = ord('/'); cases.append(b)
        b = elf(); length = struct.unpack_from('<I', b, 140)[0]
        b[257:256+length] = b'x'*(length-1); cases.append(b)
        for index, b in enumerate(cases):
            with self.subTest(index=index, size=len(b)), self.assertRaises(ValueError):
                elf32(b)

    def test_cli_writes_metadata_only_and_refuses_input_aliases(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); source = root/'input.json'; source.write_bytes(wrap()); output = root/'output.json'
            args = ['inspect', '--file', str(source), '--output', str(output)]
            with patch('sys.argv', args):
                main()
            self.assertEqual(json.loads(output.read_text())['elf']['class_bits'], 32)
            alias = root/'alias.json'; os.link(source, alias)
            symlink = root/'symlink.json'; symlink.symlink_to(source)
            for out in (source, alias, symlink):
                with patch('sys.argv', args[:-1]+[str(out)]), self.assertRaises(ValueError):
                    main()
            self.assertEqual(source.read_bytes(), wrap())
