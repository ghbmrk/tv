#!/usr/bin/env python3
"""Bounded static VDFS 2007 catalog inspection; no extraction, mounting or execution."""
import argparse
import hashlib
import json
import struct
import sys
from collections import Counter
from pathlib import Path

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.inspect_update_metadata import platform_header, read_bounded, require, unpack


# Deliberate public research targets. Never export arbitrary catalog names or values.
TARGETS = frozenset(('libcapi-drm-widevinecdm.so.0.1.1', 'libdrm-service.so.0.1.0',
                     'org.tizen.netflix-app.sh'))
MAX_METADATA = 64 * 1024**2
MAX_RECORDS = 1_000_000


def crc(data):
    import zlib
    return zlib.crc32(data, 0xffffffff) ^ 0xffffffff


def inspect(prefix, data, image_bytes):
    wrapper = platform_header(prefix, image_bytes)
    parts = [p for p in wrapper['partitions'] if p['name'] == 'pltf_t.img']
    require(len(parts) == 1, 'needs unique platform image partition')
    part = parts[0]
    start, size = part['image_file_start_byte'], part['image_bytes']
    require('vdfs_headers' in part and 0 < len(data) <= MAX_METADATA, 'needs checked VDFS headers and bounded metadata')
    volume = prefix[start:]
    header, extended = volume[1024:1536], volume[1536:4096]
    block = part['vdfs_headers']['block_bytes']
    node_size = part['vdfs_headers']['metadata_node_bytes']
    require(node_size == 16384 and block == 4096, 'unsupported catalog geometry')
    table_block, table_blocks = unpack(extended, 72, '<QQ')
    table_start, table_end = table_block*block, (table_block+table_blocks)*block
    require(8192 <= table_start < table_end <= min(len(volume), size) and table_end-table_start <= 1024**2)
    require(table_end <= part['vdfs_headers']['declared_volume_blocks']*block, 'table beyond declared volume')
    table = volume[table_start:table_end]
    require(table[:4] == b'CoWB', 'unsupported snapshot table')
    check_at = unpack(table, 16, '<Q')[0]
    require(104 <= check_at <= len(table)-4 and crc(table[:check_at]) == unpack(table, check_at, '<I')[0]
            and unpack(header, 232, '<I')[0] == unpack(table, check_at, '<I')[0], 'snapshot CRC or reference mismatch')
    extents = [unpack(extended, 88+i*16, '<QQ') for i in range(96)]
    require(extents[0][1] > 0 and not any(a or n for a, n in extents[1:]), 'only one metadata extent supported')
    meta_start, meta_blocks = extents[0]
    require(meta_start >= (table_end+block-1)//block and (meta_start+meta_blocks) <= part['vdfs_headers']['declared_volume_blocks']
            and meta_blocks*block == len(data), 'metadata range mismatch')
    count = unpack(table, 24, '<Q')[0]+1
    offsets = unpack(table, 64, '<5Q')
    off = offsets[0]
    require(2 <= count <= 4096 and 104 <= off <= off+count*16 <= check_at, 'catalog translation bounds')
    # No other table may alias catalog translations.
    require(all(not v or v >= off+count*16 for v in offsets[1:]), 'overlapping translation tables')
    graph, siblings, locations = {}, {}, set()
    record_types, node_types = Counter(), Counter()
    selected, total, root, height = [], 0, None, None
    for node in range(count):
        physical, sync, mount = unpack(table, off+node*16, '<QII')
        at = physical*block
        require(at % node_size == 0 and at not in locations and at+node_size <= len(data), 'node range or alias')
        locations.add(at)
        b = data[at:at+node_size]
        require(crc(b[:-4]) == unpack(b, node_size-4, '<I')[0], 'catalog node CRC mismatch')
        require(unpack(b, 4, '<2I') == (sync, mount), 'snapshot node version mismatch')
        if node == 0:
            require(b[:4] == b'eHND', 'catalog head magic')
            root, height = unpack(b, 12, '<IH')
            continue
        require(b[:4] == b'Nd\0\0', 'catalog node magic')
        n = unpack(b, 14, '<H')[0]
        ident, prev, nxt, kind = unpack(b, 16, '<4I')
        require(ident == node and kind in (1, 2) and 0 < n <= 512 and prev < count and nxt < count, 'catalog node fields')
        graph[node], siblings[node] = [], (prev, nxt, kind)
        node_types[str(kind)] += 1
        end = node_size-4-4*(n+1)
        ranges = []
        for index in range(n):
            record = unpack(b, node_size-4-4*(index+1), '<I')[0]
            require(32 <= record < end, 'record offset')
            keylen, reclen = unpack(b, record+4, '<HH')
            require(26 <= keylen <= reclen and record+reclen <= end, 'record bounds')
            ranges.append((record, record+reclen))
            record_type, name_bytes = b[record+24:record+26]
            require(record_type in (1, 2, 3, 5) and 26+name_bytes <= keylen, 'catalog key fields')
            name = b[record+26:record+26+name_bytes].decode('utf-8')
            require('\0' not in name, 'catalog name contains NUL')
            if kind == 1:
                require(keylen+4 <= reclen, 'index value bounds')
                child = unpack(b, record+keylen, '<I')[0]
                require(0 < child < count, 'index child range')
                graph[node].append(child)
            else:
                total += 1
                require(total <= MAX_RECORDS, 'catalog record budget')
                record_types[str(record_type)] += 1
                if name in TARGETS and record_type == 2:
                    value = b[record+keylen:record+reclen]
                    require(len(value) == 312, 'unsupported selected file value')
                    selected.append({'name': name, 'record_type': record_type,
                                     'file_mode': unpack(value, 32, '<H')[0],
                                     'declared_file_bytes': unpack(value, 80, '<Q')[0],
                                     'catalog_record_sha256': hashlib.sha256(b[record:record+reclen]).hexdigest()})
        ranges.sort()
        require(all(a[1] <= b[0] for a, b in zip(ranges, ranges[1:])), 'overlapping catalog records')
    require(root in graph and 1 <= height <= 16, 'catalog root or height')
    seen, depths, pending = set(), set(), [(root, 1)]
    while pending:
        node, depth = pending.pop()
        require(node not in seen and depth <= 16, 'cycle, shared child or excessive depth')
        seen.add(node)
        if siblings[node][2] == 2:
            depths.add(depth)
        pending.extend((child, depth+1) for child in graph[node])
    require(len(seen) == count-1 and depths == {height}, 'unreachable nodes or unequal leaf depth')
    for node, (prev, nxt, kind) in siblings.items():
        require(not prev or siblings[prev][1] == node and siblings[prev][2] == kind, 'previous sibling mismatch')
        require(not nxt or siblings[nxt][0] == node and siblings[nxt][2] == kind, 'next sibling mismatch')
    require(len({v['name'] for v in selected}) == len(selected), 'ambiguous selected file records')
    return {'schema_version': 1, 'scope': 'Shared update catalog structure and selected file declarations only.',
            'platform_prefix_sha256': hashlib.sha256(prefix).hexdigest(),
            'metadata_sha256': hashlib.sha256(data).hexdigest(), 'metadata_bytes': len(data),
            'snapshot_crc_and_reference_match': True, 'catalog_nodes': count,
            'node_crcs_checked': count, 'node_type_counts': dict(sorted(node_types.items())),
            'leaf_records': total, 'record_type_counts': dict(sorted(record_types.items())),
            'rooted_graph_reaches_every_node_once': True, 'graph_height_matches': True,
            'sibling_links_reciprocal': True, 'selected_files': sorted(selected, key=lambda v: v['name']),
            'arbitrary_names_values_and_file_extents_exported': False,
            'file_contents_validated': False, 'signature_verified': False,
            'installed_variant_verified': False, 'boot_or_recovery_qualified': False,
            'code_executed': False, 'device_accessed': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--platform-prefix', type=Path, required=True)
    parser.add_argument('--metadata', type=Path, required=True)
    parser.add_argument('--image-bytes', type=int, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    inputs = (args.platform_prefix, args.metadata)
    require(args.output.suffix == '.json' and not args.output.is_symlink(), 'output must be a JSON file, not a link')
    require(all(args.output.resolve() != v.resolve() for v in inputs), 'output aliases input')
    if args.output.exists():
        require(args.output.is_file() and all(not args.output.samefile(v) for v in inputs), 'output aliases input')
    result = inspect(read_bounded(args.platform_prefix, 4*1024**2), read_bounded(args.metadata, MAX_METADATA), args.image_bytes)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2)+'\n')
    print('Catalog structure inspected; no extraction, mount, code execution, device access or signature qualification.')


if __name__ == '__main__':
    main()
