#!/usr/bin/env python3
"""Inspect bounded XZ streams and conservative ARM zImage headers, without execution."""
import argparse
import hashlib
import json
import lzma
from pathlib import Path
import re
import stat
import struct
import zlib

MAX_INPUT = 16 * 1024**2
MAX_OUTPUT = 32 * 1024**2
MAX_MEMORY = 64 * 1024**2
MAX_CANDIDATES = 64
MAGIC = b'\xfd7zXZ\0'


def arm_zimage_headers(data):
    """Recognize only the conservative little-endian A32, zero-linked header form.

    Format reference: Linux v5.4 arch/arm/boot/compressed/head.S, lines 155-185,
    and vmlinux.lds.S, lines 111-114 (captured source line numbers).
    This checks file structure, never load addresses, execution or authenticity.
    """
    rows = []
    magic = struct.pack('<I', 0x016f2818)
    for hit in re.finditer(re.escape(magic), data):
        if len(rows) >= MAX_CANDIDATES:
            raise ValueError('zImage candidate budget exceeded')
        offset = hit.start() - 36
        row = {'offset': offset, 'validated': False}
        rows.append(row)
        if offset < 0 or offset % 4 or offset + 60 > len(data):
            row['rejection'] = 'header_bounds_or_alignment'
            continue
        words = struct.unpack_from('<15I', data, offset)
        if (words[:8] != (0xe1a00000,) * 8 or words[8] != 0xea000005
                or words[12:14] != (0x04030201, 0x45454545)):
            row['rejection'] = 'unsupported_entry_or_header_shape'
            continue
        start, end, table = words[10], words[11], words[14]
        # Nonzero-linked, Thumb2, BE and EFI forms need their own reviewed parser.
        if start != 0:
            row['rejection'] = 'unsupported_nonzero_link_base'
            continue
        if end < 60 or end > len(data) - offset or table < 60 or table % 4 or table >= end:
            row['rejection'] = 'image_or_table_range'
            continue
        row.update(validated=True, image_bytes=end,
                   image_sha256=hashlib.sha256(data[offset:offset + end]).hexdigest(),
                   header_form='Linux ARM A32 little-endian zero-linked candidate',
                   contained_xz_candidate_indices=[])
    return rows


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
    images = arm_zimage_headers(data)
    for image in images:
        if image['validated']:
            image['contained_xz_candidate_indices'] = [
                i for i, stream in enumerate(records) if stream['validated']
                and image['offset'] + 60 <= stream['offset']
                and stream['stored_stream_bytes'] <= image['offset'] + image['image_bytes'] - stream['offset']]
    return {'schema_version': 1, 'input_bytes': len(data),
            'input_sha256': hashlib.sha256(data).hexdigest(), 'candidates': records,
            'arm_zimage_candidates': images,
            'payload_exported': False, 'executed': False, 'device_accessed': False,
            'signature_authenticated': False, 'boot_or_recovery_qualified': False,
            'scope': 'XZ integrity/version tokens and conservative ARM zImage header/range checks only; no executable identity, '
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
