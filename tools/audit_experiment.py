#!/usr/bin/env python3
"""Audit an offline experiment review packet. Never connects to or writes a device.

Completeness and hashes are not evidence authenticity, safety or authorization.
Exit 0: structurally complete packet; 2: missing evidence; 3: invalid packet.
"""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import stat

GATES = ('identity', 'boot_trust', 'software_provenance', 'build_reproduction',
         'bench_rehearsal', 'recovery', 'stock_baseline', 'provider_route')
TARGET_FIELDS = {'model', 'installed_build', 'board_id', 'board_revision'}


def fields(value, expected):
    if not isinstance(value, dict) or set(value) != set(expected):
        raise ValueError('unexpected or missing schema fields')


def digest_file(root, record, limit):
    fields(record, {'path', 'bytes', 'sha256'})
    name, size, expected = record['path'], record['bytes'], record['sha256']
    if not isinstance(name, str) or not name or '\\' in name or any(ord(c) < 32 for c in name):
        raise ValueError('invalid evidence path')
    path = PurePosixPath(name)
    if path.is_absolute() or '..' in path.parts or str(path) != name:
        raise ValueError('evidence must use a canonical relative path')
    if type(size) is not int or not 0 < size <= limit or not isinstance(expected, str) or not re.fullmatch('[0-9a-f]{64}', expected):
        raise ValueError('invalid evidence size or digest')
    current = root
    for part in path.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError('symlink evidence is forbidden')
    info = current.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_size != size:
        raise ValueError('evidence type or size mismatch')
    digest = hashlib.sha256()
    count = 0
    with current.open('rb') as stream:
        for block in iter(lambda: stream.read(1024**2), b''):
            count += len(block)
            if count > size:
                raise ValueError('evidence grew during audit')
            digest.update(block)
    if count != size or digest.hexdigest() != expected:
        raise ValueError('evidence digest mismatch')


def audit(packet, root):
    fields(packet, {'schema_version', 'target', 'artifact', 'gates'})
    if type(packet['schema_version']) is not int or packet['schema_version'] != 1:
        raise ValueError('unsupported schema version')
    target = packet['target']
    fields(target, TARGET_FIELDS)
    if any(v is not None and (not isinstance(v, str) or not v.strip()) for v in target.values()):
        raise ValueError('invalid target identity')
    blockers = ['target:' + k for k in sorted(TARGET_FIELDS) if target[k] is None]
    artifact = packet['artifact']
    if artifact is None:
        blockers.append('artifact:missing')
    else:
        digest_file(root, artifact, 8 * 1024**3)
    gates = packet['gates']
    if not isinstance(gates, list) or len(gates) != len(GATES):
        raise ValueError('all experiment gates must occur exactly once')
    seen = set()
    for gate in gates:
        fields(gate, {'id', 'status', 'scope', 'evidence'})
        ident = gate['id']
        if not isinstance(ident, str) or ident not in GATES or ident in seen:
            raise ValueError('unknown or duplicate gate')
        seen.add(ident)
        if gate['status'] == 'unverified':
            if gate['scope'] is not None or gate['evidence'] != []:
                raise ValueError('unverified gates must not carry acceptance evidence')
            blockers.append(ident + ':unverified')
            continue
        if gate['status'] != 'documented' or any(target[k] is None for k in TARGET_FIELDS) or artifact is None:
            raise ValueError('documented gate requires exact identity and artifact')
        fields(gate['scope'], {'target', 'artifact_sha256'})
        if gate['scope'] != {'target': target, 'artifact_sha256': artifact['sha256']}:
            raise ValueError('stale or different experiment scope')
        evidence = gate['evidence']
        if not isinstance(evidence, list) or not evidence or len(evidence) > 16:
            raise ValueError('documented gate requires bounded evidence')
        for record in evidence:
            digest_file(root, record, 16 * 1024**2)
    return {'schema_version': 1, 'review_packet_complete': not blockers,
            'blockers': blockers, 'hardware_safety_verified': False,
            'authorization_granted': False, 'device_accessed': False,
            'limit': 'Hashes and schema only. Independent technical review and separate owner authorization are required; this tool never authorizes a hardware experiment.'}


def unique_object(pairs):
    result = {}
    for k, v in pairs:
        if k in result:
            raise ValueError('duplicate JSON field')
        result[k] = v
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('packet', type=Path)
    parser.add_argument('--evidence-root', type=Path)
    args = parser.parse_args()
    try:
        info = args.packet.stat()
        if not stat.S_ISREG(info.st_mode) or info.st_size > 512 * 1024:
            raise ValueError('packet must be a bounded regular file')
        packet = json.loads(args.packet.read_text(), object_pairs_hook=unique_object)
        result = audit(packet, (args.evidence_root or args.packet.parent).resolve())
    except (ValueError, OSError, TypeError, KeyError, RecursionError):
        print(json.dumps({'review_packet_complete': False, 'authorization_granted': False,
                          'hardware_safety_verified': False, 'device_accessed': False,
                          'error': 'invalid packet or unavailable/mismatched evidence'}))
        raise SystemExit(3)
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result['review_packet_complete'] else 2)


if __name__ == '__main__':
    main()
