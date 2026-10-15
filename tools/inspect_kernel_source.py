#!/usr/bin/env python3
"""Inspect selected kernel metadata inside an offline source ZIP; never extract or execute."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import tarfile
import zipfile


SELECTED = {
    'linux-5.4/Makefile',
    'linux-5.4/arch/arm/configs/PONTUSM_release_defconfig',
    'linux-5.4/arch/arm/mach-sdp/Kconfig',
    'linux-5.4/drivers/soc/sdp/Kconfig',
    'linux-5.4/arch/arm/mach-sdp/Makefile',
    'linux-5.4/arch/arm/mach-sdp/board-pontus-dt.c',
    'linux-5.4/arch/arm/mach-sdp/platsmp.c',
}
BOOT_MARKERS = ('samsung,sdp-pontusm', 'DT_MACHINE_START', 'sdp_platsmp_init',
                '_sdp_pontus_set_entry', 'sdp_secondary_startup', 'sdp_smp_boot_secondary')
SYMBOLS = ('CONFIG_ARM', 'CONFIG_ARM64', 'CONFIG_ARCH_SDP', 'CONFIG_ARCH_SDP_PONTUS',
           'CONFIG_CPU_V7', 'CONFIG_CPU_V8', 'CONFIG_CPU_ARM_CORTEX_A15', 'CONFIG_AEABI', 'CONFIG_HIGHMEM',
           'CONFIG_ANDROID', 'CONFIG_ANDROID_BINDER_IPC', 'CONFIG_ANDROID_BINDERFS',
           'CONFIG_DRM', 'CONFIG_FB', 'CONFIG_OF', 'CONFIG_MMC', 'CONFIG_MTD')


def inspect(stream, *, expanded_limit=4 * 1024**3, member_limit=200000):
    records = []
    total = count = 0
    seen = set()
    with tarfile.open(fileobj=stream, mode='r|gz') as archive:
        for member in archive:
            count += 1
            total += member.size
            path = PurePosixPath(member.name)
            if (path.is_absolute() or '..' in path.parts or '\\' in member.name
                    or any(ord(c) < 32 for c in member.name)):
                raise ValueError('unsafe nested member path')
            if count > member_limit or total > expanded_limit:
                raise ValueError('nested archive budget exceeded')
            if member.name not in SELECTED:
                continue
            if member.name in seen or not member.isfile() or member.size > 256 * 1024:
                raise ValueError('selected metadata must be unique bounded regular files')
            seen.add(member.name)
            data = archive.extractfile(member).read()
            text = data.decode('utf-8', errors='strict')
            record = {'path': member.name, 'size_bytes': len(data),
                      'sha256': hashlib.sha256(data).hexdigest()}
            if member.name.endswith('defconfig'):
                values = dict(re.findall(r'^(CONFIG_\w+)=(.*)$', text, re.MULTILINE))
                values.update({k: 'not_set' for k in re.findall(
                    r'^# (CONFIG_\w+) is not set$', text, re.MULTILINE)})
                record['selected_config_values'] = {k: values[k] for k in SYMBOLS if k in values}
                record['platform_config_values'] = {k: v for k, v in values.items()
                                                    if k.startswith(('CONFIG_SDP_', 'CONFIG_MACH_'))}
            elif member.name == 'linux-5.4/Makefile':
                record['version_fields'] = dict(re.findall(
                    r'^(VERSION|PATCHLEVEL|SUBLEVEL|EXTRAVERSION)[ \t]*=[ \t]*([^\n]*)', text, re.MULTILINE))
            elif member.name.endswith(('board-pontus-dt.c', 'platsmp.c', 'mach-sdp/Makefile')):
                lines = data.split(b'\n')
                record['lexical_markers'] = {marker: [
                    {'line': index + 1, 'line_sha256': hashlib.sha256(line).hexdigest()}
                    for index, line in enumerate(lines) if marker.encode('ascii') in line]
                    for marker in BOOT_MARKERS if marker.encode('ascii') in data}
            else:
                record['declared_symbols'] = re.findall(r'^config (\w+)', text, re.MULTILINE)
            records.append(record)
    return {'schema_version': 1, 'nested_member': 'linux.tgz', 'member_count': count,
            'declared_expanded_bytes': total, 'selected_metadata': records,
            'files_extracted': False, 'code_executed': False,
            'marker_semantics': 'Lexical locations only; manually review control flow and build applicability separately.',
            'target_board_and_installed_build_correspondence': 'unverified'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.archive.stat().st_size > 2 * 1024**3:
        raise ValueError('source archive exceeds budget')
    with zipfile.ZipFile(args.archive) as source:
        if source.namelist().count('linux.tgz') != 1:
            raise ValueError('expected exactly one linux.tgz member')
        member = source.getinfo('linux.tgz')
        if member.file_size > 512 * 1024**2:
            raise ValueError('nested compressed archive exceeds budget')
        with source.open(member) as stream:
            result = inspect(stream)
            # Complete the ZIP-member read so its CRC is checked, including padding.
            while stream.read(1024 * 1024):
                pass
    if {item['path'] for item in result['selected_metadata']} != SELECTED:
        raise ValueError('required kernel metadata is missing')
    result['nested_zip_member_crc_checked'] = True
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(f"Inspected {result['member_count']} kernel members; no files extracted or executed.")


if __name__ == '__main__':
    main()
