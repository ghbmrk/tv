import struct
import os
import tempfile
from pathlib import Path
from unittest.mock import patch
import unittest
import zlib
from tools.inspect_update_metadata import metadata, dtb_bundle, kernel_header, read_bounded, platform_header, main, MAGIC


def desc(tag, body):
    return struct.pack('<BII', 1, len(body) + 4, tag) + body


def label(value, flag=1):
    return bytes([flag, len(value)]) + value


def item(name=b'uImage', identifier=1002, original=16, processed=32, salt_size=8):
    transforms = (desc(18, struct.pack('<BI', 1, 123))
                  + desc(14, bytes([1, salt_size]) + b's'*salt_size + struct.pack('<Q', processed))
                  + desc(16, struct.pack('<BIH', 1, 0, 256) + b'x'*256))
    children = desc(10, label(name)) + desc(7, struct.pack('<BI', 1, 3) + transforms)
    return desc(1, struct.pack('<BIBQQHI', 1, identifier, 0, original, processed, 0, 2) + children)


def tree(items=None):
    entries = [item()] if items is None else items
    group = desc(25, label(b'TEST') + struct.pack('<HH', 1301, 0)) + desc(61, label(b'Common', 0))
    entries = entries + [desc(2, struct.pack('<BII', 1, 0, 2) + group)]
    return struct.pack('<IH', 0, 256) + b'x'*256 + MAGIC + struct.pack('<I', len(entries)) + b''.join(entries)


def fdt_bytes(duplicate=False, depth=0):
    strings = b'model\0compatible\0'
    def word(v):
        return struct.pack('>I', v)
    def padded(b):
        return b + b'\0'*(-len(b) % 4)
    def begin(name):
        return word(1) + padded(name + b'\0')
    def prop(nameoff, value):
        return word(3) + struct.pack('>II', len(value), nameoff) + padded(value)
    st = begin(b'') + prop(0, b'Synthetic DTV\0')
    if duplicate:
        st += prop(0, b'duplicate\0')
    st += prop(6, b'vendor,synthetic\0') + begin(b'cpus') + begin(b'cpu@0')
    st += prop(6, b'arm,cortex-a57\0arm,armv8\0') + word(2) + word(2)
    for i in range(depth):
        st += begin(('n'+str(i)).encode())
    st += word(2)*depth + word(2) + word(9)
    header = struct.pack('>10I', 0xd00dfeed, 56+len(st)+len(strings), 56, 56+len(st), 40, 17, 16, 0, len(strings), len(st))
    return header + b'\0'*16 + st + strings


def kernel_bytes():
    payload = b'SYNTHETIC KERNEL DATA'
    values = [0x27051956, 0, 0, len(payload), 0, 0, zlib.crc32(payload), 5, 2, 2, 0, b'Synthetic kernel']
    header = struct.pack('>7I4B32s', *values)
    values[1] = zlib.crc32(header)
    return struct.pack('>7I4B32s', *values) + payload + b'UNINTERPRETED TRAILER'


def gpt_bytes(ranges=((8, 10), (11, 13)), names=('pltf_t.img', 'prd_t.img')):
    data = bytearray(8192)
    data[510:512] = b'\x55\xaa'
    for i, ((start, end), name) in enumerate(zip(ranges, names)):
        at = 1024 + i*128
        data[at:at+32] = bytes([i+1])*32
        struct.pack_into('<QQQ', data, at+32, start, end, 0)
        encoded = name.encode('utf-16-le')
        data[at+56:at+56+len(encoded)] = encoded
    data[4096:4100] = b'VDFS'
    struct.pack_into('<8s4I4Q16sQIII', data, 512, b'EFI PART', 0x10000, 92, 0, 0,
                     1, 19, 4, 17, b'g'*16, 2, 2, 128, zlib.crc32(data[1024:1280]))
    struct.pack_into('<I', data, 528, zlib.crc32(data[512:604]))
    return data


class UpdateMetadataTests(unittest.TestCase):
    def test_metadata_is_bounded_inventory_not_authentication_or_key_export(self):
        result = metadata(tree())
        self.assertEqual(result['groups'], [{'name': 'TEST', 'major': 1301, 'minor': 0, 'device_type': 'Common'}])
        self.assertEqual(result['items'][0]['name'], 'uImage')
        self.assertEqual(result['items'][0]['encryption_salt_bytes'], 8)
        self.assertEqual(result['items'][0]['signature_bytes'], 256)
        self.assertNotIn('salt', result['items'][0])
        self.assertNotIn('signature', result['items'][0])
        self.assertFalse(result['signature_verified'])
        self.assertTrue(result['exact_eof'])

    def test_metadata_refuses_truncation_trailing_data_ambiguous_ids_and_unsafe_names(self):
        for bad in (tree()[:-1], tree()+b'x', tree([item(), item()]), tree([item(b'../escape')]),
                    tree([item(b'uImage', original=0)]), tree([item(b'uImage', processed=31)]),
                    tree([item(b'uImage', salt_size=32)]), b'\0'*65537):
            with self.subTest(size=len(bad)), self.assertRaises(ValueError):
                metadata(bad)
        value = bytearray(tree())
        struct.pack_into('<I', value, 313, 129)
        with self.assertRaises(ValueError):
            metadata(value)
        value = bytearray(tree()); struct.pack_into('<I', value, 318, 2**32-1)
        with self.assertRaises(ValueError):
            metadata(value)

    def test_dtb_bundle_reports_declared_cpu_without_hardware_identity(self):
        a = fdt_bytes(); bundle = dtb_bundle(b'PAD!' + a + b'\0'*12 + a)
        self.assertEqual([f['file_offset'] for f in bundle['fdts']], [4, 4+len(a)+12])
        self.assertEqual(bundle['fdts'][0]['root_model'], ['Synthetic DTV'])
        self.assertEqual(bundle['fdts'][0]['cpu_compatible_sets'], [['arm,cortex-a57', 'arm,armv8']])
        self.assertEqual(bundle['fdts'][0]['cpu_compatible_node_count'], 1)
        self.assertNotIn('physical_cpu_verified', bundle)
        self.assertFalse(bundle['trailing_or_inter_tree_bytes_interpreted'])

    def test_fdt_rejects_overlapping_blocks_invalid_tokens_duplicates_and_unbounded_nesting(self):
        cases = [fdt_bytes()[:-1], fdt_bytes(duplicate=True), fdt_bytes(depth=65)]
        for field, value in ((4, 2**32-1), (8, 40), (12, 40), (16, 56), (20, 99), (32, 2**32-1)):
            b = bytearray(fdt_bytes()); struct.pack_into('>I', b, field, value); cases.append(b)
        b = bytearray(fdt_bytes()); struct.pack_into('>I', b, 56, 99); cases.append(b)
        b = bytearray(fdt_bytes()); b[40:56] = b'\xff'*16; cases.append(b)
        for bad in cases:
            with self.subTest(size=len(bad)), self.assertRaises(ValueError):
                dtb_bundle(bad)
        for bad in (b'not a device tree', b'\0'*(2*1024**2+1)):
            with self.assertRaises(ValueError):
                dtb_bundle(bad)

    def test_kernel_checks_both_crcs_and_does_not_interpret_trailer_or_addresses(self):
        data = kernel_bytes(); result = kernel_header(data)
        self.assertEqual(result['uninterpreted_trailing_bytes'], len(b'UNINTERPRETED TRAILER'))
        self.assertEqual(result['architecture_id'], 2)
        self.assertTrue(result['load_entry_values_omitted'])
        self.assertFalse(result['signature_verified'])
        for at in (1, 4, 10, 64):
            b = bytearray(data); b[at] ^= 1
            with self.assertRaises(ValueError):
                kernel_header(b)
        with self.assertRaises(ValueError):
            kernel_header(data[:63])

    def test_platform_gpt_checks_crcs_and_limits_claims_to_image_ranges(self):
        result = platform_header(gpt_bytes(), 10240)
        self.assertEqual(result['partitions'][0], {
            'name': 'pltf_t.img', 'image_file_start_byte': 4096, 'image_bytes': 1536,
            'filesystem_marker_candidate': 'VDFS'})
        self.assertTrue(result['guid_values_omitted'])
        self.assertFalse(result['filesystem_validated'])
        self.assertFalse(result['backup_gpt_checked'])
        self.assertFalse(result['live_device_layout_verified'])
        self.assertNotIn('guid', result)

    def test_platform_gpt_refuses_damage_overlap_duplicates_and_invalid_ranges(self):
        cases = [gpt_bytes(ranges=((8, 11), (11, 13))),
                 gpt_bytes(ranges=((3, 10), (11, 13))),
                 gpt_bytes(ranges=((8, 10), (11, 18))),
                 gpt_bytes(names=('duplicate', 'duplicate')),
                 gpt_bytes()[:1100], b'X'*2048]
        for at in (510, 520, 528, 1024):
            data = gpt_bytes(); data[at] ^= 1; cases.append(data)
        for bad in cases:
            with self.subTest(size=len(bad)), self.assertRaises(ValueError):
                platform_header(bad, 10240)
        for size in (10239, 1024, 2**31+512):
            with self.assertRaises(ValueError):
                platform_header(gpt_bytes(), size)

    def test_cli_preserves_inputs_and_refuses_links_and_oversized_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); source = root / 'input.json'; source.write_bytes(tree())
            alias = root / 'alias.json'; os.link(source, alias)
            link = root / 'link.json'; link.symlink_to(source)
            for output in (source, alias, link):
                with patch('sys.argv', ['inspect', '--metadata', str(source), '--output', str(output)]):
                    with self.assertRaises(ValueError):
                        main()
                self.assertEqual(source.read_bytes(), tree())
            with self.assertRaises(ValueError):
                read_bounded(link, 65536)
            with self.assertRaises(ValueError):
                read_bounded(source, 8)
            with self.assertRaises(ValueError):
                read_bounded(root, 65536)
