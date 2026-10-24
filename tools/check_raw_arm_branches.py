#!/usr/bin/env python3
"""Check recorded A32 B/BL destinations in private raw bytes; never execute them."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.inspect_update_metadata import read_bounded, require

MAX_BYTES = 8 * 1024**2


def branch(raw, address):
    """Decode A32 immediate B/BL only. Conditions are reported, never evaluated.

    Reference: LLVM LLDB EmulateInstructionARM::EmulateB, encoding A1.
    BLX and Thumb encodings need separate decoders.
    """
    require(len(raw) == 4 and type(address) is int and 0 <= address < 2**32-8
            and address % 4 == 0, 'branch geometry')
    word, = struct.unpack('<I', raw)
    condition = word >> 28
    require(condition != 15 and (word >> 25) & 7 == 5, 'not A32 immediate B/BL')
    displacement = (word & 0xffffff) << 2
    if displacement & (1 << 25):
        displacement -= 1 << 26
    target = address + 8 + displacement
    require(0 <= target < 2**32, 'branch wraps address space')
    return target, bool(word & (1 << 24)), condition


def inspect(data, record):
    require(4 <= len(data) <= MAX_BYTES and len(data) == record['input_bytes'], 'input size')
    require(hashlib.sha256(data).hexdigest() == record['input_sha256'], 'input digest')
    base = record['analysis_image_base']
    require(type(base) is int and base % 4 == 0 and 0 <= base <= 2**32-len(data), 'analysis mapping')
    sites = record['branch_sites']
    require(isinstance(sites, list) and 0 < len(sites) <= 32, 'branch budget')
    seen, checked = set(), []
    for site in sites:
        offset, target = site['file_offset'], site['target_file_offset']
        require(type(offset) is int and type(target) is int and offset % 4 == target % 4 == 0
                and 0 <= offset <= len(data)-4 and 0 <= target <= len(data)-4, 'file range')
        require(offset not in seen, 'duplicate branch site')
        seen.add(offset)
        raw = data[offset:offset+4]
        require(hashlib.sha256(raw).hexdigest() == site['instruction_sha256'], 'instruction digest')
        actual, link, condition = branch(raw, base + offset)
        require(type(site['link']) is bool and type(site['condition_id']) is int
                and (actual-base, link, condition) == (target, site['link'], site['condition_id']),
                'branch destination or encoding mismatch')
        checked.append({'file_offset': offset, 'target_file_offset': target,
                        'link': link, 'condition_id': condition})
    return {'schema_version': 1, 'input_sha256': record['input_sha256'],
            'checked_branches': checked, 'executed': False, 'device_accessed': False,
            'boot_or_recovery_qualified': False,
            'scope': 'Raw-file mapping, instruction digest and A32 direct branch arithmetic only; '
                     'analysis base is imposed, not a device address. No reachability, '
                     'condition outcome, actual execution or boot-authority proof.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--file', type=Path, required=True)
    parser.add_argument('--inventory', type=Path, required=True)
    args = parser.parse_args()
    record = json.loads(read_bounded(args.inventory, 65536))['wrapper_control_flow']
    print(json.dumps(inspect(read_bounded(args.file, MAX_BYTES), record), indent=2))


if __name__ == '__main__':
    main()
