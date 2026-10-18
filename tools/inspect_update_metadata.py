#!/usr/bin/env python3
"""Inspect bounded, already-decrypted update metadata/FDT/kernel files; no decryption or execution."""
import argparse
import hashlib
import json
import os
import stat
import re
import struct
import zlib
from pathlib import Path


MAGIC = b'Tizen Software Upgrade Tree Binary Format ver. 1.9\0'
NAME = re.compile(r'[A-Za-z0-9._ -]{1,128}')


def require(ok, message='invalid or unsupported bounded metadata'):
    if not ok:
        raise ValueError(message)


def unpack(data, offset, fmt, end=None):
    require(0 <= offset <= offset + struct.calcsize(fmt) <= (len(data) if end is None else end) <= len(data))
    return struct.unpack_from(fmt, data, offset)


def descriptor(data, offset, limit):
    flag, size, tag = unpack(data, offset, '<BII', limit)
    end = offset + 5 + size
    require(flag == 1 and size >= 4 and offset + 9 <= end <= limit)
    return tag, offset + 9, end


def children(data, offset, count, limit):
    require(0 <= count <= 32)
    result = []
    for _ in range(count):
        tag, start, end = descriptor(data, offset, limit)
        result.append((tag, start, end))
        offset = end
    require(offset == limit)
    return result


def label(data, start, end, expected_flag=1):
    flag, size = unpack(data, start, '<BB', end)
    require(flag == expected_flag and 1 <= size <= 128 and start + 2 + size <= end)
    value = data[start + 2:start + 2 + size].rstrip(b'\0').decode('ascii')
    require(NAME.fullmatch(value) is not None)
    return value, start + 2 + size


def metadata(data):
    require(0 < len(data) <= 65536)
    _, signature_size = unpack(data, 0, '<IH')
    require(signature_size in (256, 512))
    offset = 6 + signature_size
    require(data[offset:offset + len(MAGIC)] == MAGIC)
    offset += len(MAGIC)
    count, = unpack(data, offset, '<I'); offset += 4
    require(1 <= count <= 128)
    items, groups, opaque = [], [], []
    for _ in range(count):
        tag, start, end = descriptor(data, offset, len(data)); offset = end
        if tag == 1:
            flag, identifier, _, original, processed, _ = unpack(data, start, '<BIBQQH', end)
            require(flag == 1 and 0 < original <= 2**31 and 0 < processed <= 2**31)
            n, = unpack(data, start + 24, '<I', end)
            item = {'item_id': identifier, 'original_bytes': original, 'processed_bytes': processed,
                    'encrypted': False, 'signature_verified': False}
            for sub, a, z in children(data, start + 28, n, end):
                if sub == 10:
                    require('name' not in item)
                    name, after = label(data, a, z)
                    require(after == z and re.fullmatch(r'[A-Za-z0-9._-]{1,128}', name) is not None
                            and name not in ('.', '..'))
                    item['name'] = name
                elif sub == 7:
                    flag, n = unpack(data, a, '<BI', z); require(flag == 1)
                    for kind, u, v in children(data, a + 5, n, z):
                        if kind == 14:
                            flag, length = unpack(data, u, '<BB', v)
                            require(not item['encrypted'] and flag == 1 and length in (8, 16) and u + 2 + length + 8 == v)
                            encrypted_size, = unpack(data, u + 2 + length, '<Q', v)
                            require(encrypted_size == processed and processed % 16 == 0)
                            item.update(encrypted=True, encryption_salt_bytes=length)
                        elif kind == 16:
                            flag, _, length = unpack(data, u, '<BIH', v)
                            require('signature_bytes' not in item and flag == 1 and length in (256, 512) and u + 7 + length == v)
                            item['signature_bytes'] = length
                        elif kind == 18:
                            flag, crc = unpack(data, u, '<BI', v)
                            require('crc32' not in item and flag == 1 and u + 5 == v)
                            item['crc32'] = format(crc, '08x')
                        else:
                            raise ValueError('unsupported processing descriptor')
                elif sub == 19:
                    require(z - a == 5 and data[a] == 1)
                else:
                    raise ValueError('unsupported item descriptor')
            require('name' in item)
            items.append(item)
        elif tag == 2:
            flag, _, n = unpack(data, start, '<BII', end); require(flag == 1)
            group = {}
            for sub, a, z in children(data, start + 9, n, end):
                if sub == 25:
                    require('name' not in group)
                    name, after = label(data, a, z); require(z - after in (4, 5))
                    major, minor = unpack(data, z - 4, '<HH', z)
                    group.update(name=name, major=major, minor=minor)
                elif sub == 61:
                    require('device_type' not in group)
                    value, after = label(data, a, z, expected_flag=0); require(after == z)
                    group['device_type'] = value
                else:
                    group.setdefault('opaque_tags', []).append(sub)
            groups.append(group)
        elif tag in (0x37, 0x23, 0x3a):
            opaque.append({'tag': tag, 'body_bytes': end - start})
        else:
            raise ValueError('unsupported top descriptor')
    require(offset == len(data) and items and len({v['item_id'] for v in items}) == len(items)
            and len({v['name'] for v in items}) == len(items))
    return {'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data), 'format': 'Tizen update tree 1.9',
            'signature_bytes': signature_size, 'signature_verified': False, 'items': items,
            'groups': groups, 'opaque_descriptors': opaque, 'all_descriptor_bounds_checked': True, 'exact_eof': True}


def cstring(data, offset, limit, budget):
    require(0 <= offset < limit <= len(data))
    stop = data.find(b'\0', offset, min(limit, offset + budget + 1))
    require(stop >= offset)
    return data[offset:stop].decode('ascii'), stop + 1


def fdt(data, offset):
    magic, total, st, ss, reserve, version, last, _, strsize, stsize = unpack(data, offset, '>10I')
    require(magic == 0xd00dfeed and 40 <= total <= 2*1024**2 and offset + total <= len(data)
            and 16 <= last <= version <= 17)
    blob = data[offset:offset + total]
    require(st % 4 == 0 and st >= 40 and st + stsize <= total and ss >= 40 and ss + strsize <= total
            and reserve % 8 == 0 and 40 <= reserve < total
            and (st + stsize <= ss or ss + strsize <= st))
    reserve_end = reserve
    for _ in range(1024):
        require(reserve_end + 16 <= total)
        address, length = unpack(blob, reserve_end, '>QQ')
        reserve_end += 16
        if address == length == 0:
            break
    else:
        raise ValueError('FDT reservation budget exceeded')
    require((reserve_end <= st or reserve >= st + stsize)
            and (reserve_end <= ss or reserve >= ss + strsize))
    cursor, end, stack = st, st + stsize, []
    selected, seen, node_paths = {}, set(), set()
    nodes = properties = 0
    ended = False
    while cursor < end:
        token, = unpack(blob, cursor, '>I', end); cursor += 4
        if token == 1:
            name, cursor = cstring(blob, cursor, end, 128)
            require(re.fullmatch(r'[A-Za-z0-9,._+@#-]*', name) is not None)
            require((not stack and nodes == 0 and name == '') or (bool(stack) and bool(name)))
            cursor = (cursor + 3) & ~3
            stack.append(name); nodes += 1
            path = '/'.join(stack)
            require(path not in node_paths); node_paths.add(path)
            require(len(stack) <= 64 and nodes <= 4096)
        elif token == 2:
            require(bool(stack)); stack.pop()
        elif token == 3:
            require(bool(stack))
            length, nameoff = unpack(blob, cursor, '>II', end); cursor += 8
            require(length <= 65536 and cursor + length <= end and nameoff < strsize)
            name, _ = cstring(blob, ss + nameoff, ss + strsize, 128)
            require(re.fullmatch(r'[A-Za-z0-9,._+?#-]{1,128}', name) is not None)
            path = '/'.join(stack); key = (path, name)
            require(key not in seen); seen.add(key)
            value = blob[cursor:cursor + length]; cursor = (cursor + length + 3) & ~3
            properties += 1; require(properties <= 16384)
            if (len(stack) == 1 and name in ('model', 'compatible')) or (path.startswith('/cpus/') and name == 'compatible'):
                require(0 < len(value) <= 1024 and value.endswith(b'\0'))
                text = value.rstrip(b'\0').decode('ascii')
                require(text and all(text.split('\0')) and all(c == '\0' or 32 <= ord(c) <= 126 for c in text))
                selected[path + '/' + name] = text.split('\0')
        elif token == 4:
            pass
        elif token == 9:
            require(not stack); ended = True; break
        else:
            raise ValueError('unsupported FDT token')
    require(ended and cursor <= end and all(v == 0 for v in blob[cursor:end]))
    cpu = {tuple(v) for k, v in selected.items() if k.startswith('/cpus/')}
    return {'file_offset': offset, 'bytes': total, 'sha256': hashlib.sha256(blob).hexdigest(),
            'version': version, 'nodes': nodes, 'properties': properties,
            'root_model': selected.get('/model', []), 'root_compatible': selected.get('/compatible', []),
            'cpu_compatible_sets': [list(v) for v in sorted(cpu)],
            'cpu_compatible_node_count': sum(k.startswith('/cpus/') for k in selected)}


def dtb_bundle(data):
    require(0 < len(data) <= 2*1024**2)
    offset, records = 0, []
    while True:
        offset = data.find(b'\xd0\x0d\xfe\xed', offset)
        if offset < 0:
            break
        require(len(records) < 64)
        record = fdt(data, offset)
        if records:
            require(offset >= records[-1]['file_offset'] + records[-1]['bytes'])
        records.append(record); offset += 4
    require(bool(records))
    return {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(), 'fdts': records,
            'trailing_or_inter_tree_bytes_interpreted': False}


def kernel_header(data):
    require(64 <= len(data) <= 16*1024**2)
    magic, crc, _, size, _, _, dcrc, osid, arch, kind, comp, name = unpack(data, 0, '>7I4B32s')
    header = bytearray(data[:64]); header[4:8] = b'\0'*4
    require(magic == 0x27051956 and zlib.crc32(header) == crc and 0 < size <= len(data) - 64
            and zlib.crc32(data[64:64 + size]) == dcrc)
    name = name.split(b'\0', 1)[0].decode('ascii'); require(all(32 <= ord(c) <= 126 for c in name))
    return {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(), 'format': 'legacy uImage',
            'header_crc_matches': True, 'data_crc_matches': True, 'declared_data_bytes': size,
            'uninterpreted_trailing_bytes': len(data) - 64 - size, 'os_id': osid, 'architecture_id': arch,
            'image_type_id': kind, 'compression_id': comp, 'name': name,
            'load_entry_values_omitted': True, 'signature_verified': False}


def platform_header(data, image_bytes):
    require(1024 <= len(data) <= 4*1024**2 and len(data) <= image_bytes <= 2**31 and image_bytes % 512 == 0)
    require(data[510:512] == b'\x55\xaa' and data[512:520] == b'EFI PART')
    header = data[512:1024]
    version, size, crc, reserved = unpack(header, 8, '<4I')
    require(version == 0x10000 and 92 <= size <= 512 and reserved == 0)
    checked = bytearray(header[:size]); checked[16:20] = b'\0'*4
    require(zlib.crc32(checked) == crc)
    current, backup, first, last = unpack(header, 24, '<4Q')
    table_lba, count, entry_size, table_crc = unpack(header, 72, '<QIII')
    require(current == 1 and backup == image_bytes // 512 - 1 and 2 <= first <= last < backup
            and table_lba >= 2 and 1 <= count <= 1024 and 128 <= entry_size <= 1024 and entry_size % 8 == 0)
    table_start, table_end = table_lba*512, table_lba*512 + count*entry_size
    require(table_end <= len(data) and table_end <= first*512)
    table = data[table_start:table_end]; require(zlib.crc32(table) == table_crc)
    records, names, ranges = [], set(), []
    for i in range(count):
        entry = table[i*entry_size:(i+1)*entry_size]
        if entry[:16] == b'\0'*16:
            require(not any(entry)); continue
        start, end, _ = unpack(entry, 32, '<QQQ')
        require(first <= start <= end <= last)
        name = entry[56:128].decode('utf-16-le').split('\0', 1)[0]
        require(re.fullmatch(r'[A-Za-z0-9 ._-]{1,36}', name) is not None and name not in names)
        names.add(name); ranges.append((start, end))
        record = {'name': name, 'image_file_start_byte': start*512, 'image_bytes': (end-start+1)*512}
        if data[start*512:start*512+4] == b'VDFS':
            record['filesystem_marker_candidate'] = 'VDFS'
        records.append(record)
    require(records and all(a[1] < b[0] for a, b in zip(sorted(ranges), sorted(ranges)[1:])))
    return {'prefix_bytes': len(data), 'prefix_sha256': hashlib.sha256(data).hexdigest(),
            'declared_image_bytes': image_bytes, 'header_crc_matches': True, 'entry_array_crc_matches': True,
            'partitions': records, 'backup_gpt_checked': False, 'filesystem_validated': False,
            'guid_values_omitted': True, 'live_device_layout_verified': False,
            'scope': 'GPT ranges inside an update image only; not live-device flash addresses.'}


def read_bounded(path, limit):
    require(stat.S_ISREG(path.lstat().st_mode), 'input must be a regular file, not a device or link')
    fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
    with os.fdopen(fd, 'rb') as stream:
        require(stat.S_ISREG(os.fstat(stream.fileno()).st_mode), 'input must remain a regular file')
        data = stream.read(limit + 1)
    require(0 < len(data) <= limit, 'input outside size budget')
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--metadata', type=Path, required=True)
    parser.add_argument('--dtb', type=Path)
    parser.add_argument('--kernel', type=Path)
    parser.add_argument('--platform-prefix', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    inputs = [v for v in (args.metadata, args.dtb, args.kernel, args.platform_prefix) if v is not None]
    require(args.output.suffix == '.json' and not args.output.is_symlink(), 'output must be a JSON file, not a link')
    require(all(args.output.resolve() != path.resolve() for path in inputs), 'output must preserve inputs')
    if args.output.exists():
        require(args.output.is_file() and all(not args.output.samefile(path) for path in inputs), 'output must preserve inputs')
    result = {'schema_version': 1, 'metadata': metadata(read_bounded(args.metadata, 65536)),
              'signature_verified': False, 'device_identity_verified': False,
              'boot_or_recovery_qualified': False, 'code_executed': False,
              'scope': 'Input-file declarations only; not observed hardware, live partitions or boot policy.'}
    if args.dtb:
        result['dtb_bundle'] = dtb_bundle(read_bounded(args.dtb, 2*1024**2))
    if args.kernel:
        result['kernel_image'] = kernel_header(read_bounded(args.kernel, 16*1024**2))
    if args.platform_prefix:
        platform = [v for v in result['metadata']['items'] if v['name'] == 'platform.img']
        require(len(platform) == 1, 'platform prefix needs matching metadata')
        result['platform_image_prefix'] = platform_header(read_bounded(args.platform_prefix, 4*1024**2), platform[0]['original_bytes'])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print('Bounded update metadata inspected; no decryption, execution, device access or signature qualification.')


if __name__ == '__main__':
    main()
