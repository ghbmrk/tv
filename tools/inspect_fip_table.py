#!/usr/bin/env python3
"""Inspect a bounded FIP-shaped table, including the observed AA32 marker variant.

Metadata only. Layout similarity does not establish loader compatibility or image roles.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.inspect_update_metadata import read_bounded, require

MAX_BYTES = 2 * 1024**2
MAX_ENTRIES = 64


def inspect(data):
    require(56 <= len(data) <= MAX_BYTES, 'input size')
    magic, serial, flags = struct.unpack_from('<IIQ', data)
    require(magic in (0xaa320001, 0xaa640001) and serial != 0, 'unsupported header')
    cursor, entries, seen = 16, [], set()
    for _ in range(MAX_ENTRIES + 1):
        require(cursor + 40 <= len(data), 'truncated table')
        uuid, offset, size, entry_flags = struct.unpack_from('<16sQQQ', data, cursor)
        cursor += 40
        if uuid == b'\0'*16:
            require(size == entry_flags == 0 and offset == len(data), 'unsupported terminator')
            break
        require(len(entries) < MAX_ENTRIES and uuid not in seen, 'duplicate or excessive entries')
        require(0 < size <= len(data) and offset <= len(data)-size, 'payload range')
        seen.add(uuid)
        entries.append((uuid, offset, size, entry_flags))
    else:
        raise ValueError('missing table terminator')
    require(entries, 'empty table')
    ranges = sorted((o, o+s) for _, o, s, _ in entries)
    require(ranges[0][0] >= cursor, 'payload overlaps header/table')
    require(all(a[1] <= b[0] for a, b in zip(ranges, ranges[1:])), 'overlapping payloads')
    records = [{'index': i, 'uuid_sha256': hashlib.sha256(uid).hexdigest(),
                'file_offset': o, 'bytes': s, 'payload_sha256': hashlib.sha256(data[o:o+s]).hexdigest(),
                'entry_flags_zero': f == 0, 'role': None}
               for i, (uid, o, s, f) in enumerate(entries)]
    return {'schema_version': 1, 'input_bytes': len(data),
            'input_sha256': hashlib.sha256(data).hexdigest(), 'header_magic': hex(magic),
            'matches_upstream_tfa_magic': magic == 0xaa640001,
            'header_serial_nonzero': True, 'header_flags_zero': flags == 0,
            'header_and_terminated_table_bytes': cursor, 'entries': records,
            'uninterpreted_gap_or_padding_bytes': len(data)-cursor-sum(v[2] for v in entries),
            'payload_exported': False, 'executed': False, 'device_accessed': False,
            'signature_authenticated': False, 'boot_or_recovery_qualified': False,
            'scope': 'Observed little-endian table shape, bounds, uniqueness and hashes only. '
                     'AA32 is not the inspected upstream TF-A marker. No payload role, CPU '
                     'architecture, executing loader, signing authority or compatibility proof.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--file', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    if (args.output.suffix != '.json' or args.output.is_symlink()
            or args.output.resolve() == args.file.resolve()
            or (args.output.exists() and (not args.output.is_file() or args.output.samefile(args.file)))):
        raise ValueError('output must preserve input')
    result = inspect(read_bounded(args.file, MAX_BYTES))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2)+'\n')
    print('FIP-shaped metadata inspected; no payload export, execution or device access.')


if __name__ == '__main__':
    main()
