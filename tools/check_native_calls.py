#!/usr/bin/env python3
"""Corroborate recorded Thumb BLX calls against a supplied ELF; never execute it."""
import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.inspect_update_metadata import read_bounded, require, unpack

MAX_BYTES = 8 * 1024**2


def blx_target(raw, address):
    """Decode only Thumb-2 BLX immediate (T2), including signed displacement."""
    require(len(raw) == 4 and 0 <= address < 2**32-4 and address % 2 == 0, 'call geometry')
    hi, lo = struct.unpack('<HH', raw)
    require(hi & 0xf800 == 0xf000 and lo & 0xd001 == 0xc000, 'not Thumb BLX immediate T2')
    sign, j1, j2 = (hi >> 10) & 1, (lo >> 13) & 1, (lo >> 11) & 1
    i1, i2 = 1 ^ (j1 ^ sign), 1 ^ (j2 ^ sign)
    displacement = (sign << 24) | (i1 << 23) | (i2 << 22) | ((hi & 0x3ff) << 12) | ((lo & 0x7fe) << 1)
    if sign:
        displacement -= 1 << 25
    target = ((address + 4) & ~3) + displacement
    require(0 <= target < 2**32, 'call destination outside address space')
    return target


def inspect(data, record):
    require(52 <= len(data) <= MAX_BYTES and data[:7] == b'\x7fELF\x01\x01\x01', 'needs little-endian ELF32')
    require(hashlib.sha256(data).hexdigest() == record['decoded_sha256'], 'input digest mismatch')
    kind, machine, version, _, phoff, _, _, ehsize, phsize, phcount, _, _, _ = unpack(data, 16, '<HH5I6H')
    require(kind in (2, 3) and machine == 40 and version == 1 and ehsize == 52 and phsize == 32
            and 0 < phcount <= 128 and phoff >= 52 and phoff+phcount*32 <= len(data), 'unsupported ELF header')
    loads = []
    for i in range(phcount):
        typ, offset, address, _, filesz, memsz, flags, align = unpack(data, phoff+i*32, '<8I')
        require(offset+filesz <= len(data) and filesz <= memsz and address+memsz <= 2**32, 'ELF segment bounds')
        require(align in (0, 1) or align & (align-1) == 0, 'ELF alignment')
        if typ == 1:
            loads.append((address, address+filesz, offset, flags))
    require(loads, 'no load segments')
    original_base = min(v[0] for v in loads)
    analysis_base = record['analysis_image_base']
    require(type(analysis_base) is int and 0 <= analysis_base < 2**32, 'invalid analysis image base')
    rebase = analysis_base-original_base
    calls = record['call_sites']
    require(isinstance(calls, list) and 0 < len(calls) <= 32, 'call count budget')
    seen, checked = set(), []
    for call in calls:
        address, offset, target = (int(call[k], 16) for k in ('address', 'file_offset', 'target'))
        require(address not in seen, 'duplicate call site')
        seen.add(address)
        original = address-rebase
        matches = [(off+original-begin, flags) for begin, end, off, flags in loads
                   if begin <= original and original+4 <= end]
        require(len(matches) == 1 and matches[0][0] == offset and matches[0][1] & 1, 'ambiguous or incorrect executable mapping')
        raw = data[offset:offset+4]
        require(hashlib.sha256(raw).hexdigest() == call['instruction_sha256'], 'instruction digest mismatch')
        require(blx_target(raw, address) == target, 'call destination mismatch')
        checked.append({'address': hex(address), 'file_offset': hex(offset), 'target': hex(target)})
    return {'schema_version': 1, 'input_sha256': record['decoded_sha256'], 'analysis_rebase_bytes': rebase,
            'checked_calls': checked, 'executed': False, 'device_accessed': False,
            'scope': 'ELF mapping, four-byte digest and direct branch destination only; no symbol binding, reachability or boot proof.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--file', type=Path, required=True)
    parser.add_argument('--inventory', type=Path, default=Path(__file__).resolve().parents[1]/'research/boot-verifier-inventory.json')
    args = parser.parse_args()
    record = json.loads(read_bounded(args.inventory, 65536))['verifier']
    print(json.dumps(inspect(read_bounded(args.file, MAX_BYTES), record), indent=2))


if __name__ == '__main__':
    main()
