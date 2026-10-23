#!/usr/bin/env python3
"""Inspect bounded embedded XZ streams without exporting or executing their payloads."""
import argparse
import hashlib
import json
import lzma
from pathlib import Path
import re
import stat
import zlib

MAX_INPUT = 16 * 1024**2
MAX_OUTPUT = 32 * 1024**2
MAX_MEMORY = 64 * 1024**2
MAX_CANDIDATES = 64
MAGIC = b'\xfd7zXZ\0'


def inspect(data):
    if not 0 < len(data) <= MAX_INPUT:
        raise ValueError('input budget exceeded')
    offsets = []
    for match in re.finditer(re.escape(MAGIC), data):
        if len(offsets) >= MAX_CANDIDATES:
            raise ValueError('candidate budget exceeded')
        offsets.append(match.start())
    records = []
    decoded_total = 0
    for offset in offsets:
        source = data[offset:]
        row = {'offset': offset, 'validated': False}
        records.append(row)
        if len(source) < 12 or zlib.crc32(source[6:8]) != int.from_bytes(source[8:12], 'little'):
            row['rejection'] = 'header_crc_or_length'
            continue
        if decoded_total >= MAX_OUTPUT:
            row['rejection'] = 'output_budget'
            continue
        try:
            decoder = lzma.LZMADecompressor(format=lzma.FORMAT_XZ, memlimit=MAX_MEMORY)
            remaining = MAX_OUTPUT - decoded_total
            plain = decoder.decompress(source, max_length=remaining + 1)
        except lzma.LZMAError:
            row['rejection'] = 'invalid_stream_or_memory_limit'
            continue
        decoded_total += len(plain)
        if len(plain) > remaining:
            row['rejection'] = 'output_budget'
            continue
        if not decoder.eof:
            row['rejection'] = 'incomplete_stream'
            continue
        if decoder.check not in (lzma.CHECK_CRC32, lzma.CHECK_CRC64, lzma.CHECK_SHA256):
            row['rejection'] = 'integrity_check_required'
            continue
        versions = set()
        for match in re.finditer(
                rb'Linux version ([0-9]{1,6}\.[0-9]{1,6}\.[0-9]{1,6})(?=[^0-9.]|$)', plain):
            versions.add(match.group(1).decode('ascii'))
            if len(versions) == 8:
                break
        row.update(validated=True, stored_stream_bytes=len(source)-len(decoder.unused_data),
                   decoded_bytes=len(plain), decoded_sha256=hashlib.sha256(plain).hexdigest(),
                   integrity_check_id=decoder.check, linux_version_tokens=sorted(versions))
    return {'schema_version': 1, 'input_bytes': len(data),
            'input_sha256': hashlib.sha256(data).hexdigest(), 'candidates': records,
            'payload_exported': False, 'executed': False, 'device_accessed': False,
            'signature_authenticated': False, 'boot_or_recovery_qualified': False,
            'scope': 'XZ stream integrity and bounded version tokens only; no executable identity, '
                     'boot-stage role, installed-unit correspondence or trust-policy proof.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--file', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    info = args.file.lstat()
    if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= MAX_INPUT:
        raise ValueError('input must be a bounded regular file')
    if args.output.suffix != '.json' or args.output.is_symlink() or args.output.resolve() == args.file.resolve():
        raise ValueError('output must preserve input')
    if args.output.exists() and (not args.output.is_file() or args.output.samefile(args.file)):
        raise ValueError('output aliases input')
    with args.file.open('rb') as stream:
        data = stream.read(MAX_INPUT + 1)
    result = inspect(data)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print('Embedded XZ metadata inspected; no payload export, execution or device access.')


if __name__ == '__main__':
    main()
