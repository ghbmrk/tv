#!/usr/bin/env python3
"""Inspect a bounded post-zImage DEFLATE/DTB envelope without payload export."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys
import zlib

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.inspect_embedded_xz import arm_zimage_headers
from tools.inspect_update_metadata import dtb_bundle, read_bounded, require

MAX_INPUT = 8 * 1024**2
MAX_PACKED = 1024**2
MAX_DECODED = 2 * 1024**2


def envelope(data, offset):
    require(type(offset) is int and 0 <= offset <= len(data)-12, 'envelope range')
    marker, decoded_bytes, packed_bytes = struct.unpack_from('<III', data, offset)
    require(marker == 0x2020, 'unsupported envelope marker')
    require(0 < decoded_bytes <= MAX_DECODED and 0 < packed_bytes <= MAX_PACKED
            and packed_bytes <= len(data)-offset-12, 'envelope budget or truncation')
    packed = data[offset+12:offset+12+packed_bytes]
    decoder = zlib.decompressobj(-15)
    try:
        plain = decoder.decompress(packed, decoded_bytes+1)
    except zlib.error as exc:
        raise ValueError('invalid raw DEFLATE') from exc
    require(len(plain) == decoded_bytes and decoder.eof and not decoder.unused_data
            and not decoder.unconsumed_tail, 'DEFLATE size, completion or trailing data')
    trees = dtb_bundle(plain)
    return {'file_offset': offset, 'header_bytes': 12, 'packed_bytes': packed_bytes,
            'packed_sha256': hashlib.sha256(packed).hexdigest(),
            'decoded_bytes': len(plain), 'decoded_sha256': hashlib.sha256(plain).hexdigest(),
            'deflate_eof': True, 'checksum_or_signature_authenticated': False,
            'dtb_bundle': trees}


def inspect(data):
    require(60 <= len(data) <= MAX_INPUT, 'input budget')
    images = [r for r in arm_zimage_headers(data) if r['validated']]
    require(len(images) == 1, 'requires one unambiguous supported zImage header')
    image = {k: v for k, v in images[0].items() if k != 'contained_xz_candidate_indices'}
    tail = envelope(data, image['offset']+image['image_bytes'])
    return {'schema_version': 1, 'input_bytes': len(data),
            'input_sha256': hashlib.sha256(data).hexdigest(), 'zimage': image,
            'post_image_envelope': tail,
            'uninterpreted_bytes_after_envelope': len(data)-tail['file_offset']-12-tail['packed_bytes'],
            'payload_exported': False,
            'executed': False, 'device_accessed': False, 'boot_or_recovery_qualified': False,
            'scope': 'One observed envelope form and structurally valid device trees; '
                     'no executing variant, boot trust, live storage map or independent recovery proof.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--file', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if (args.output.suffix != '.json' or args.output.is_symlink()
            or args.output.resolve() == args.file.resolve()
            or (args.output.exists() and (not args.output.is_file() or args.output.samefile(args.file)))):
        raise ValueError('output must preserve input')
    result = inspect(read_bounded(args.file, MAX_INPUT))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2)+'\n')
    print('Post-image metadata inspected; no payload export, execution or device access.')


if __name__ == '__main__':
    main()
