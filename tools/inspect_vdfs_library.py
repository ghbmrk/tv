#!/usr/bin/env python3
"""Inspect an unencrypted VDFS zlib-wrapped ELF32 file without saving or executing it."""
import argparse
import hashlib
import json
import re
import struct
import sys
import zlib
from pathlib import Path

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.inspect_update_metadata import read_bounded, require, unpack

MAX_BYTES = 8 * 1024**2


def decode(data):
    require(40 < len(data) <= MAX_BYTES, 'compressed file size budget')
    d = data[-40:]
    sign, magic = d[7], d[8:12]
    count, layout = unpack(d, 12, '<HH')
    size, checksum, log = unpack(d, 16, '<QII')
    require(not any(d[:7]) and sign in (0, 1, 2) and magic[1:] == b'Zip' and magic[0] in b'IHh'
            and layout == 6 and 0 < count <= 128 and 9 <= log <= 20 and 0 < size <= MAX_BYTES, 'unsupported descriptor')
    require(count == (size+(1 << log)-1)//(1 << log), 'chunk count mismatch')
    hash_bytes = {ord('I'): 16, ord('H'): 20, ord('h'): 32}[magic[0]]
    signature_bytes = {0: 0, 1: 128, 2: 256}[sign]
    table = len(data)-40-count*16-(count+1)*hash_bytes-signature_bytes
    require(table > 0, 'compression table bounds')
    checked = bytearray(data[table:]); checked[-16:-12] = b'\0'*4
    require(zlib.crc32(checked, 0xffffffff) ^ 0xffffffff == checksum, 'compression descriptor CRC mismatch')
    hash_at = table+count*16
    hash_fn = {ord('I'): hashlib.md5, ord('H'): hashlib.sha1, ord('h'): hashlib.sha256}[magic[0]]
    descriptor = bytearray(d); descriptor[24:28] = b'\0'*4
    require(hash_fn(descriptor).digest() == data[hash_at+count*hash_bytes:hash_at+(count+1)*hash_bytes], 'descriptor hash mismatch')
    result, ranges, padding = bytearray(), [], 0
    for i in range(count):
        _, flags, length, start = unpack(data, table+i*16, '<HHIQ')
        require(flags in (0, 1), 'encrypted or unsupported chunks refused')
        require(0 < length <= 2*(1 << log) and start+length <= table, 'chunk range or budget')
        ranges.append((start, start+length))
        chunk = data[start:start+length]
        require(hash_fn(chunk).digest() == data[hash_at+i*hash_bytes:hash_at+(i+1)*hash_bytes], 'chunk hash mismatch')
        if flags == 1:
            plain = chunk
        else:
            require(start % 64 == 0 and length % 64 == 0, 'unsupported zlib alignment')
            dec = zlib.decompressobj()
            try:
                plain = dec.decompress(chunk, (1 << log)+1)
            except zlib.error as error:
                raise ValueError('invalid zlib stream') from error
            require(dec.eof and not dec.unconsumed_tail and len(dec.unused_data) < 64
                    and not any(dec.unused_data), 'invalid, oversized or trailing zlib stream')
            padding += len(dec.unused_data)
        require(len(plain) == min(1 << log, size-len(result)), 'decoded chunk size mismatch')
        result.extend(plain)
    ranges.sort()
    require(all(a[1] <= b[0] for a, b in zip(ranges, ranges[1:])), 'overlapping chunk ranges')
    require(len(result) == size, 'decoded file size mismatch')
    return bytes(result), {'layout': layout, 'chunks': count, 'descriptor_crc_matches': True, 'chunk_and_descriptor_hashes_match': True,
                           'zero_alignment_padding_bytes': padding, 'signature_type_id': sign,
                           'signature_verified': False, 'encrypted_chunks_accepted': False}


def elf32(data):
    require(52 <= len(data) <= MAX_BYTES and data[:7] == b'\x7fELF\x01\x01\x01', 'needs little-endian ELF32')
    kind, machine, version, _, phoff, _, _, ehsize, phsize, phcount, _, _, _ = unpack(data, 16, '<HH5I6H')
    require(kind == 3 and machine == 40 and version == 1 and ehsize == 52 and phsize == 32
            and 0 < phcount <= 128 and phoff >= 52 and phoff+phcount*32 <= len(data), 'unsupported ELF header')
    loads, dynamics = [], []
    for i in range(phcount):
        typ, offset, address, _, filesz, memsz, _, align = unpack(data, phoff+i*32, '<8I')
        require(offset+filesz <= len(data) and filesz <= memsz and address+memsz <= 2**32, 'ELF segment bounds')
        require(align in (0, 1) or align & (align-1) == 0, 'ELF segment alignment')
        if typ == 1:
            loads.append((address, address+filesz, offset))
        if typ == 2:
            require(filesz % 8 == 0 and filesz <= 65536, 'dynamic table bounds')
            dynamics.append((offset, filesz))
    require(loads and len(dynamics) == 1, 'needs unique dynamic table')
    offset, length = dynamics[0]
    tags, needed, ended = {}, [], False
    for at in range(offset, offset+length, 8):
        tag, value = unpack(data, at, '<iI')
        if tag == 0:
            ended = True
            break
        if tag == 1:
            needed.append(value)
        elif tag in (5, 10, 14):
            require(tag not in tags, 'ambiguous dynamic tag')
            tags[tag] = value
    require(ended and 5 in tags and 10 in tags and 0 < tags[10] <= 1024**2 and len(needed) <= 128, 'dynamic strings budget')
    candidates = [off+tags[5]-begin for begin, end, off in loads if begin <= tags[5] < tags[5]+tags[10] <= end]
    require(len(candidates) == 1, 'ambiguous or out-of-range string table')
    strings = data[candidates[0]:candidates[0]+tags[10]]
    def name(index):
        require(0 <= index < len(strings), 'dynamic string offset')
        end = strings.find(b'\0', index, min(index+257, len(strings)))
        require(end > index, 'unterminated dynamic string')
        value = strings[index:end].decode('ascii')
        require(re.fullmatch(r'[A-Za-z0-9_.+\-]{1,256}', value) is not None, 'unsafe library name')
        return value
    names = [name(v) for v in needed]
    require(len(set(names)) == len(names), 'duplicate dependency names')
    result = {'class_bits': 32, 'endianness': 'little', 'machine_id': machine,
              'type_id': kind, 'needed_libraries': sorted(names)}
    if 14 in tags:
        result['soname'] = name(tags[14])
    return result


def inspect(data):
    plain, compression = decode(data)
    return {'schema_version': 1, 'stored_bytes': len(data), 'stored_sha256': hashlib.sha256(data).hexdigest(),
            'decoded_bytes': len(plain), 'decoded_sha256': hashlib.sha256(plain).hexdigest(),
            'compression': compression, 'elf': elf32(plain), 'decoded_bytes_exported': False,
            'executed': False, 'device_accessed': False, 'signature_verified': False,
            'android_compatibility_verified': False, 'provider_or_quality_eligibility_verified': False,
            'scope': 'Static declarations in supplied file only; no runtime or secure-media qualification.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--file', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    require(args.output.suffix == '.json' and not args.output.is_symlink()
            and args.output.resolve() != args.file.resolve(), 'output must preserve input')
    if args.output.exists():
        require(args.output.is_file() and not args.output.samefile(args.file), 'output aliases input')
    result = inspect(read_bounded(args.file, MAX_BYTES))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2)+'\n')
    print('Static compressed ELF metadata inspected; no file bytes exported, code execution or device access.')


if __name__ == '__main__':
    main()
