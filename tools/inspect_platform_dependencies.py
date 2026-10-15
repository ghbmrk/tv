#!/usr/bin/env python3
"""Hash and locate selected dependency evidence in the private family source archive.

No extraction, compilation, device access, source redistribution, or acceptance inference.
Markers are lexical observations; their branches may be inactive on the actual TV.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import stat
import tarfile
import zipfile


SELECTED = {
    'tztv-bootmode.zip': ('tztv-bootmode.c',),
    'tztv-micom.zip': tuple('tztv-micom/tztv-micom/' + name for name in (
        'Makefile', 'sdp_micom_messagebox.c', 'sdp_micom.h',
        'tztv-micom-upgrade.c', 'rc-wt61p807.c')),
    'tztv-hdmi-sw.zip': ('include/vd_kernel-interfaces/video/frc_tcon_tztv.h',
                         'include/tztv_hdmi_switch_init.h'),
    'trustzone-drivers.tar.gz': tuple('trustzone-drivers/source/tzdev/' + name for name in (
        'smc_call.S', 'tzdev_antirollback.c', 'ssdev_rpmb.c', 'tzdev_smc.c')),
}
MARKERS = {
    'boot_mode_observation': r'\b(?:of_get_property|gpio_get_value_cansleep|readl)\b',
    'boot_mode_proc_read': r'\b(?:seq_read|single_open)\b',
    'pontus_build_branch': r'\bCHIP_PONTUSM\b',
    'controller_upgrade_build': r'\bCONFIG_UPGRADE_SUBMICOM_FIRMWARE\b',
    'controller_upgrade_reference': r'\bmicom_upgrade_(?:check_firmware|get_running_firmware_version)\b',
    'controller_transport': r'\bsdp_messagebox_write(?:_direct)?\b',
    'restart_hook': r'\barm_pm_restart(?:_standby)?\b',
    'remote_input': r'\b(?:rc_register_device|rc_allocate_device|rc_keydown|input_report_key)\b',
    'controller_power_commands': r'\b(?:SDP_MICOM_CMD_POWEROFF|SDP_MICOM_CMD_RESTART|CTM_STANDBY_REBOOT)\b',
    'panel_firmware_interface': r'\bTCON_IOCTL_UPGRADE_(?:DEMURA|FLASH)_FIRMWARE(?:_SE)?\b',
    'hdmi_firmware_interface': r'\b(?:CheckFirmwareStatus|UpgradeFirmware)\b',
    'secure_monitor_instruction': r'^\s*smc\s+#0',
    'secure_rollback_query': r'\bTZANTIROLLBACK_GET_VERSION\b',
    'rpmb_operations': r'\bMMC_RPMB_(?:READ|WRITE|WRITE_KEY|READ_CNT)\b',
}
MAX_PACKAGE = 8 * 1024**2
MAX_EXPANDED = 32 * 1024**2
MAX_MEMBERS = 4096
MAX_TEXT = 1024**2


def safe_path(name):
    path = PurePosixPath(name)
    if path.is_absolute() or '..' in path.parts or '\\' in name or any(ord(c) < 32 for c in name):
        raise ValueError('unsafe archive path')


def record(path, data):
    if len(data) > MAX_TEXT:
        raise ValueError('selected text exceeds budget')
    # Match only ASCII tokens. Preserve arbitrary legacy comment bytes in hashes.
    lines = data.split(b'\n')
    markers = {}
    for label, pattern in MARKERS.items():
        hits = [{'line': n, 'line_sha256': hashlib.sha256(line).hexdigest()}
                for n, line in enumerate(lines, 1)
                if re.search(pattern, line.decode('latin-1'))]
        if hits:
            markers[label] = hits
    return {'path': path, 'size_bytes': len(data),
            'sha256': hashlib.sha256(data).hexdigest(), 'lexical_markers': markers}


def inspect_package(name, data, selected):
    if len(data) > MAX_PACKAGE:
        raise ValueError('package exceeds budget')
    selected = set(selected)
    found = {}
    total = count = 0

    def admit(path, size, regular, read):
        nonlocal total, count
        safe_path(path)
        count += 1
        total += size
        if count > MAX_MEMBERS or size < 0 or total > MAX_EXPANDED:
            raise ValueError('archive budget exceeded')
        if path not in selected:
            return
        if path in found or not regular or size > MAX_TEXT:
            raise ValueError('selected file must be unique bounded regular text')
        content = read()
        if len(content) != size:
            raise ValueError('truncated selected file')
        found[path] = record(path, content)

    if name.endswith('.zip'):
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            for member in archive.infolist():
                mode = member.external_attr >> 16
                regular = not member.is_dir() and stat.S_IFMT(mode) in (0, stat.S_IFREG)
                admit(member.filename, member.file_size, regular,
                      lambda m=member: archive.read(m))
    else:
        with tarfile.open(fileobj=io.BytesIO(data), mode='r|gz') as archive:
            for member in archive:
                admit(member.name, member.size, member.isfile(),
                      lambda m=member: archive.extractfile(m).read(MAX_TEXT + 1))
    if set(found) != selected:
        raise ValueError('required selected file missing')
    return {'member': name, 'sha256': hashlib.sha256(data).hexdigest(),
            'size_bytes': len(data), 'member_count': count,
            'declared_expanded_bytes': total, 'selected_files': [found[p] for p in sorted(found)]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.archive.stat().st_size > 2 * 1024**3:
        raise ValueError('source archive exceeds budget')
    digest = hashlib.sha256()
    with args.archive.open('rb') as stream:
        for block in iter(lambda: stream.read(1024**2), b''):
            digest.update(block)
    packages = []
    with zipfile.ZipFile(args.archive) as archive:
        for name, selected in SELECTED.items():
            matches = [m for m in archive.infolist() if m.filename == name]
            if len(matches) != 1 or matches[0].file_size > MAX_PACKAGE:
                raise ValueError('required package must be unique and bounded')
            packages.append(inspect_package(name, archive.read(matches[0]), selected))
    result = {'schema_version': 1, 'source_archive_sha256': digest.hexdigest(),
              'packages': packages, 'files_extracted': False, 'code_executed': False,
              'source_text_redistributed': False,
              'target_applicability': 'family_source_only; exact_board_and_build_unverified',
              'marker_semantics': 'lexical locations only; not control-flow, active-branch, absence, or runtime proof'}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print('Saved selected file hashes and marker locations; no vendor source text or device access.')


if __name__ == '__main__':
    main()
