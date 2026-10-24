#!/usr/bin/env python3
"""Inspect nested XZ/newc recovery metadata; never extract or execute members."""
import argparse
import hashlib
import json
import lzma
from pathlib import Path, PurePosixPath
import re
import stat
import struct
import sys

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.inspect_update_metadata import read_bounded, require

MAX_INPUT = 8 * 1024**2
MAX_DECODED = 4 * 1024**2
MAX_MEMBERS = 512
SELECTED = {'init', 'sbin/init', 'bin/sh', 'bin/toybox', 'bin/upgrade_mgr',
            'etc/inittab', 'etc/init.d/rcS'}
TYPES = {stat.S_IFREG: 'regular', stat.S_IFDIR: 'directory', stat.S_IFLNK: 'symlink',
         stat.S_IFCHR: 'character_device', stat.S_IFBLK: 'block_device',
         stat.S_IFIFO: 'fifo', stat.S_IFSOCK: 'socket'}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def newc(data):
    """Conservative single-archive subset; hardlinked nondirectories are refused."""
    require(110 <= len(data) <= MAX_DECODED, 'archive budget')
    position, count, seen, selected, counts = 0, 0, set(), [], {}
    while True:
        require(position+110 <= len(data), 'missing complete header or trailer')
        header = data[position:position+110]
        require(header[:6] == b'070701' and re.fullmatch(rb'[0-9a-fA-F]{104}', header[6:]),
                'unsupported or malformed newc header')
        fields = [int(header[6+i*8:14+i*8], 16) for i in range(13)]
        mode, links, size, namesize, checksum = fields[1], fields[4], fields[6], fields[11], fields[12]
        require(checksum == 0 and 1 < namesize <= 1024, 'newc checksum or name size')
        name_start, name_end = position+110, position+110+namesize
        require(name_end <= len(data), 'truncated name')
        name_bytes = data[name_start:name_end]
        require(name_bytes[-1:] == b'\0' and b'\0' not in name_bytes[:-1], 'invalid name termination')
        name = name_bytes[:-1].decode('ascii', errors='strict')
        start = (name_end+3) & ~3
        end = start+size
        require(end <= len(data) and not any(data[name_end:start]), 'data bounds or name padding')
        following = (end+3) & ~3
        require(following <= len(data) and not any(data[end:following]), 'data padding')
        if name == 'TRAILER!!!':
            require(size == 0 and not any(data[following:]), 'trailer data or unsupported concatenation')
            return {'bytes': len(data), 'sha256': digest(data), 'members': count,
                    'member_type_counts': counts, 'selected_members': selected,
                    'complete_trailer': True, 'remaining_bytes_zero': True,
                    'hardlinked_nondirectories_supported': False}
        count += 1
        require(count <= MAX_MEMBERS, 'member count budget')
        kind = stat.S_IFMT(mode)
        if name.endswith('/') and kind == stat.S_IFDIR:
            name = name[:-1]
        path = PurePosixPath(name)
        require((name == '.' and kind == stat.S_IFDIR) or (name != '.' and not path.is_absolute() and name == str(path)
                and '..' not in path.parts and '\\' not in name
                and all(32 <= ord(c) < 127 for c in name)), 'unsafe or noncanonical member name')
        require(name not in seen, 'duplicate member')
        seen.add(name)
        require(kind in TYPES and links > 0, 'unsupported member type or link count')
        require(kind == stat.S_IFDIR or links == 1, 'hardlinked nondirectory unsupported')
        require(kind in (stat.S_IFREG, stat.S_IFLNK) or size == 0, 'non-file member data')
        require(kind != stat.S_IFLNK or size > 0, 'empty symlink')
        counts[TYPES[kind]] = counts.get(TYPES[kind], 0)+1
        if name in SELECTED:
            payload = data[start:end]
            row = {'path': name, 'type': TYPES[kind], 'bytes': size, 'sha256': digest(payload)}
            if kind == stat.S_IFLNK:
                # Fixed target comparison only; unknown target strings never leave the inspector.
                row['targets_bin_toybox'] = payload in (b'/bin/toybox', b'/bin/toybox\0')
            if kind == stat.S_IFREG and payload.startswith(b'\x7fELF'):
                require(len(payload) >= 52 and payload[4:7] == b'\x01\x01\x01'
                        and struct.unpack_from('<H', payload, 40)[0] == 52, 'unsupported ELF header')
                row['elf_header'] = {'class_bits': 32, 'little_endian': True,
                                     'machine_id': struct.unpack_from('<H', payload, 18)[0]}
            if kind == stat.S_IFREG and name == 'etc/init.d/rcS':
                row['standalone_upgrade_mgr_line'] = re.search(rb'(?m)^upgrade_mgr[ \t]*\r?$', payload) is not None
                row['classification'] = 'Lexical script observation, not execution or side-effect proof'
            if kind == stat.S_IFREG and name == 'etc/inittab':
                row['sysinit_rcs_line'] = b'::sysinit:-/etc/init.d/rcS' in payload.splitlines()
            selected.append(row)
        position = following


def inspect(data):
    require(0 < len(data) <= MAX_INPUT, 'input budget')
    marker, offsets, offset = b'\xfd7zXZ\0', [], 0
    while True:
        offset = data.find(marker, offset)
        if offset < 0:
            break
        offsets.append(offset)
        require(len(offsets) <= 16, 'candidate budget')
        offset += len(marker)
    records, total = [], 0
    for offset in offsets:
        row = {'file_offset': offset, 'validated': False}
        records.append(row)
        try:
            decoder = lzma.LZMADecompressor(memlimit=64*1024**2)
            plain = decoder.decompress(data[offset:], max_length=MAX_DECODED+1)
        except lzma.LZMAError:
            row['rejection'] = 'invalid_or_memory_limited_xz'
            continue
        total += len(plain)
        require(total <= 16*1024**2, 'aggregate decoded budget')
        if not decoder.eof or len(plain) > MAX_DECODED:
            row['rejection'] = 'incomplete_or_output_limited_xz'
            continue
        if decoder.check not in (lzma.CHECK_CRC32, lzma.CHECK_CRC64, lzma.CHECK_SHA256):
            row['rejection'] = 'integrity_check_required'
            continue
        row.update(validated=True, stored_bytes=len(data)-offset-len(decoder.unused_data),
                   decoded_bytes=len(plain), decoded_sha256=digest(plain),
                   integrity_check_id=decoder.check)
        if plain.startswith(b'070701'):
            row['archive'] = newc(plain)
    return {'schema_version': 1, 'input_bytes': len(data), 'input_sha256': digest(data),
            'xz_candidates': records, 'payload_exported': False, 'executed': False,
            'device_accessed': False, 'recovery_qualified': False,
            'scope': 'Bounded nested XZ and a conservative single newc archive subset. '
                     'No filesystem creation, code execution, boot reachability or recovery proof.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--file', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    require(args.output.suffix == '.json' and not args.output.is_symlink()
            and args.output.resolve() != args.file.resolve()
            and not (args.output.exists() and args.output.samefile(args.file)), 'output must preserve input')
    result = inspect(read_bounded(args.file, MAX_INPUT))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2)+'\n')
    print('Recovery archive metadata inspected; no extraction, execution or device access.')


if __name__ == '__main__':
    main()
