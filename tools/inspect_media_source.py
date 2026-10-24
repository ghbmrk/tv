#!/usr/bin/env python3
"""Bounded offline media dependency evidence; no vendor text or device access."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import stat
import zipfile

PREFIX = 'tztv-media-sec/tztv-media-sec/sdp_vdsp/pontusm/'
SELECTED = ('Makefile', 'sdp_vdsp_init.c', 'sdp_cm7_top.c', 'sdp_vdsp_tzdev.c',
            'sdp_cm7_ucode_core0.h', 'sdp_cm7_ucode_core1.h')
GPU_PREFIX = 'tztv-media-sec/tztv-media-sec/sdp_gpu/drivers/gpu/arm/midgard/'
GPU_SELECTED = ('mali_kbase_core_linux.c', 'platform/sdp/mali_kbase_config_sdp.c',
                'platform/sdp/mali_kbase_config_platform.h', 'platform/sdp/mali_kbase_platform_sdp.c')
GPU_MARKERS = {
    'generic_gpu_compatible': rb'"arm,mali-midgard"',
    'gpu_product_label': rb'\bGPU_ID_PRODUCT_[A-Z0-9_]+\b.*\.name\s*=',
    'pontus_gpu_build_branch': rb'\bCONFIG_SOC_CHIP_PONTUSM\b',
    'gpu_power_callback': rb'\b(?:power_on_callback|power_off_callback|power_runtime_on_callback)\b',
    'gpu_clock_reset_interface': rb'\b(?:sdp_set_clkrst_mux|sdp_read_clkrst_mux)\b',
}
MARKERS = {
    'microcode_include': rb'^#include "sdp_cm7_ucode_core[01]\.h"',
    'microcode_transfer': rb'\bmemcpy_toio\(',
    'debug_read_callback': rb'\bcm7_dbg_ew_test_show\(',
    'debug_attribute_binding': rb'\bDEFINE_SIMPLE_ATTRIBUTE\(cm7_dbg_ew_test_fops,',
    'read_permission_debug_entry': rb'\bdebugfs_create_file\("ew_test", 0444,',
    'secure_world_call': rb'\b(?:symbol_get\(tzdev_scm_watch\)|_vdspext_tzdev_scm_watch\()',
    'controller_initialization': rb'\bsdp_cm7_driver_init\(',
}


def inspect(archive):
    return inspect_selected(archive, PREFIX, SELECTED, MARKERS)


def inspect_gpu(archive):
    return inspect_selected(archive, GPU_PREFIX, GPU_SELECTED, GPU_MARKERS)


def inspect_selected(archive, prefix, selected, markers):
    records = []
    for name in selected:
        path = prefix + name
        matches = [m for m in archive.infolist() if m.filename == path]
        if len(matches) != 1:
            raise ValueError('selected member must be unique and present')
        m = matches[0]
        mode = m.external_attr >> 16
        if m.file_size > 2 * 1024**2 or m.is_dir() or stat.S_IFMT(mode) not in (0, stat.S_IFREG):
            raise ValueError('selected member must be a bounded regular file')
        data = archive.read(m)  # Complete member read checks ZIP CRC; no extraction.
        records.append({'path': path, 'size_bytes': len(data),
                        'sha256': hashlib.sha256(data).hexdigest(),
                        'lexical_markers': {label: [
                            {'line': n, 'line_sha256': hashlib.sha256(line).hexdigest()}
                            for n, line in enumerate(data.split(b'\n'), 1) if re.search(pattern, line)]
                            for label, pattern in markers.items() if re.search(pattern, data, re.M)}})
    return {'schema_version': 1, 'selected_files': records, 'selected_crc_checked': True,
            'files_extracted': False, 'code_executed': False, 'device_accessed': False,
            'target_applicability': 'family source only; exact board and build unverified',
            'marker_semantics': 'Lexical evidence; control flow and applicability require manual review.'}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('archive', type=Path)
    p.add_argument('--output', required=True, type=Path)
    p.add_argument('--gpu', action='store_true', help='Inspect four fixed GPU source files instead of VDSP files')
    args = p.parse_args()
    if args.archive.stat().st_size > 2 * 1024**3:
        raise ValueError('source archive exceeds budget')
    digest = hashlib.sha256()
    with args.archive.open('rb') as stream:
        for block in iter(lambda: stream.read(1024**2), b''):
            digest.update(block)
    with zipfile.ZipFile(args.archive) as archive:
        result = inspect_gpu(archive) if args.gpu else inspect(archive)
    result['source_archive_sha256'] = digest.hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print('Saved bounded source hashes and marker locations; no device access or vendor text.')


if __name__ == '__main__':
    main()
