#!/usr/bin/env python3
"""Hash an offline source ZIP and list research candidates. Never extract/execute."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import zipfile


def index(path):
    if path.stat().st_size > 2 * 1024**3:
        raise ValueError('archive exceeds 2 GiB research budget')
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    with zipfile.ZipFile(path) as archive:
        members = archive.infolist()
        if len(members) > 200000:
            raise ValueError('archive member budget exceeded')
        candidates = []
        for member in members:
            name = member.filename
            parts = PurePosixPath(name)
            if parts.is_absolute() or '..' in parts.parts or '\\' in name or any(ord(c) < 32 for c in name):
                raise ValueError('unsafe archive member path')
            lower = name.lower()
            if any(term in lower for term in ('defconfig', '.dts', 'board', 'readme', 'manifest', 'version', 'config.gz')):
                candidates.append({'path': name, 'compressed_bytes': member.compress_size,
                                   'expanded_bytes': member.file_size, 'encrypted': bool(member.flag_bits & 1)})
        return {'schema_version': 1, 'sha256': digest.hexdigest(), 'size_bytes': path.stat().st_size,
                'member_count': len(members), 'candidate_count': len(candidates), 'candidates': candidates,
                'extracted': False, 'executed': False, 'installed_firmware_correspondence': 'unverified'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = index(args.archive)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(f"Indexed {result['member_count']} members; no files extracted or executed.")


if __name__ == '__main__':
    main()
