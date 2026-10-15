#!/usr/bin/env python3
"""Hash and CRC-check a bounded offline update ZIP; scan markers without extracting or executing."""
import argparse
import hashlib
import json
import struct
from pathlib import Path, PurePosixPath
import zipfile


MARKERS = {'msdu11': b'MSDU11', 'openssl_salted': b'Salted__', 'elf': b'\x7fELF',
           'android_boot': b'ANDROID!', 'avb': b'AVB0', 'squashfs_le': b'hsqs',
           'fdt': b'\xd0\x0d\xfe\xed'}


def msdu11_table(prefix, total_size):
    """Independently parse bounded public layout facts, not authenticated partition semantics."""
    cursor = 0

    def take(fmt):
        nonlocal cursor
        size = struct.calcsize(fmt)
        if cursor + size > len(prefix):
            raise ValueError('truncated MSDU11 table')
        result = struct.unpack_from(fmt, prefix, cursor)
        cursor += size
        return result

    magic, _, _, _, count = take('<6s4I')
    if magic != b'MSDU11' or not 1 <= count <= 64:
        raise ValueError('unsupported MSDU11 table')
    sections = []
    for _ in range(count):
        identifier, offset, size = take('<IQQ')
        sections.append({'id': identifier, 'offset': offset, 'size_bytes': size})
    if len({s['id'] for s in sections}) != count:
        raise ValueError('duplicate section identifier')
    count, = take('<I')
    if not 1 <= count <= 64:
        raise ValueError('header count outside budget')
    headers = []
    for _ in range(count):
        offset, size, length = take('<QIB')
        if not 1 <= length <= 64 or cursor + length > len(prefix):
            raise ValueError('header label outside budget')
        label = prefix[cursor:cursor + length].decode('ascii')
        if any(ord(c) < 32 or ord(c) > 126 for c in label):
            raise ValueError('unsafe header label')
        cursor += length
        headers.append({'label': label, 'offset': offset, 'size_bytes': size})
    ranges = sorted(headers + sections, key=lambda item: item['offset'])
    end = cursor
    contiguous = True
    for item in ranges:
        offset, size = item['offset'], item['size_bytes']
        if offset < end or size < 1 or offset + size > total_size:
            raise ValueError('overlapping or out-of-bounds table range')
        contiguous = contiguous and offset == end
        end = offset + size
    return {'format_candidate': 'MSDU11_outer_table', 'metadata_end': cursor,
            'headers': headers, 'sections': sections, 'ranges_in_bounds_and_nonoverlapping': True,
            'data_ranges_cover_remainder': contiguous and end == total_size,
            'runtime_partition_mapping': 'unverified', 'table_authenticated': False}


def scan(stream, limit, chunk_size=1024 * 1024, parse_outer_table=False):
    digest = hashlib.sha256()
    count = 0
    overlap = b''
    keep = max(map(len, MARKERS.values())) - 1
    markers = {key: {'count': 0, 'first_offsets': []} for key in MARKERS}
    last = {key: -1 for key in MARKERS}
    prefix = bytearray()
    while True:
        block = stream.read(chunk_size)
        if not block:
            break
        if count + len(block) > limit:
            raise ValueError('expanded member budget exceeded')
        digest.update(block)
        if parse_outer_table:
            prefix.extend(block[:max(0, 65536 - len(prefix))])
        data = overlap + block
        start = count - len(overlap)
        for key, signature in MARKERS.items():
            cursor = 0
            while True:
                index = data.find(signature, cursor)
                if index < 0:
                    break
                absolute = start + index
                if absolute > last[key]:
                    markers[key]['count'] += 1
                    if len(markers[key]['first_offsets']) < 32:
                        markers[key]['first_offsets'].append(absolute)
                    last[key] = absolute
                cursor = index + 1
        count += len(block)
        overlap = data[-keep:]
    result = {'size_bytes': count, 'sha256': digest.hexdigest(), 'marker_candidates': markers}
    if parse_outer_table and prefix.startswith(b'MSDU11'):
        result['outer_table_candidate'] = msdu11_table(prefix, count)
    return result


def inspect(path):
    if path.stat().st_size > 2 * 1024**3:
        raise ValueError('archive exceeds 2 GiB budget')
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    records = []
    with zipfile.ZipFile(path) as archive:
        members = archive.infolist()
        if len(members) > 32 or sum(m.file_size for m in members) > 3 * 1024**3:
            raise ValueError('update archive member/expansion budget exceeded')
        seen = set()
        for member in members:
            name = member.filename
            parts = PurePosixPath(name)
            if (parts.is_absolute() or '..' in parts.parts or '\\' in name
                    or any(ord(c) < 32 for c in name) or name in seen):
                raise ValueError('unsafe or duplicate update member')
            seen.add(name)
            with archive.open(member) as stream:
                record = scan(stream, member.file_size, parse_outer_table=name.endswith('/upgrade.msd'))
            if record['size_bytes'] != member.file_size:
                raise ValueError('member size mismatch')
            record.update({'path': name, 'zip_crc32': format(member.CRC, '08x'), 'zip_crc_checked': True})
            records.append(record)
    return {'schema_version': 1, 'archive_sha256': digest.hexdigest(),
            'archive_size_bytes': path.stat().st_size, 'members': records,
            'coverage': 'zip_integrity_and_raw_marker_scan', 'publisher_signature_verified': False,
            'firmware_reconstructed': False, 'device_backup': False, 'code_executed': False,
            'limit': 'Marker candidates are not validated partitions, executables, encryption or boot-policy evidence.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = inspect(args.archive)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(f"Checked {len(result['members'])} update members; no extraction or execution.")


if __name__ == '__main__':
    main()
