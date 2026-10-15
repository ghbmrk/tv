#!/usr/bin/env python3
"""Read-only owner-targeted Samsung identification. No discovery, credentials, root or settings writes."""
import argparse
from datetime import datetime, timezone
import http.client
import ipaddress
import json
from pathlib import Path
import re
import time


MAX_BODY = 65536
PRIVATE_NETWORKS = tuple(ipaddress.ip_network(value) for value in ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16'))
EXPECTED_MODEL = 'QN50LS03FAFXZA'
MODEL_FAMILY = {EXPECTED_MODEL, 'QN50LS03F', '50LS03F'}


def sanitize(payload):
    if not isinstance(payload, dict) or not isinstance(payload.get('device'), dict):
        raise ValueError('device object required')
    device = payload['device']
    model = device.get('modelName')
    recognized_model = model if isinstance(model, str) and model in MODEL_FAMILY else None
    firmware = device.get('firmwareVersion')
    if not isinstance(firmware, str) or not re.fullmatch(r'T-PTMFAKUC-0090-[0-9]{1,6}\.[0-9]{1,3}', firmware):
        firmware = None

    def flag(value):
        if type(value) is bool:
            return value
        if type(value) is str and value in ('0', '1', 'true', 'false'):
            return value in ('1', 'true')
        return None

    resolution = device.get('resolution')
    match = re.fullmatch(r'([0-9]{1,5})x([0-9]{1,5})', resolution) if isinstance(resolution, str) else None
    reported_resolution = [int(value) for value in match.groups()] if match else None
    if reported_resolution and not all(1 <= value <= 16384 for value in reported_resolution):
        reported_resolution = None
    return {'schema_version': 1, 'kind': 'unauthenticated_http_device_observation',
            'observed_utc': datetime.now(timezone.utc).isoformat(),
            'reported_model_code': recognized_model,
            'model_match': 'full_sku' if recognized_model == EXPECTED_MODEL else 'family_only' if recognized_model else 'unrecognized',
            'reported_software_build': firmware,
            'developer_mode_reported': flag(device.get('developerMode')),
            'frame_tv_support_reported': flag(device.get('FrameTVSupport')),
            'reported_ui_resolution': reported_resolution,
            'unique_identifiers_retained': False, 'raw_response_retained': False,
            'limit': 'Unauthenticated reported fields, not exact board/SoC/ABI, media quality, boot access or recovery evidence.'}


def identify(host, *, port=8001, allow_loopback_test=False):
    address = ipaddress.IPv4Address(host)
    if not (any(address in network for network in PRIVATE_NETWORKS)
            or (allow_loopback_test and address.is_loopback)):
        raise ValueError('an owner-supplied private LAN IPv4 address is required')
    connection = http.client.HTTPConnection(str(address), port, timeout=5)
    response = None
    started = time.monotonic()
    try:
        connection.request('GET', '/api/v2/', headers={'Accept': 'application/json', 'Connection': 'close'})
        response = connection.getresponse()
        if response.status != 200:  # Never follow a redirect or attempt authentication.
            raise ValueError('identification endpoint did not return success')
        if response.getheader('Content-Type', '').split(';')[0].strip().lower() != 'application/json':
            raise ValueError('JSON response required')
        size = response.getheader('Content-Length')
        if size is not None and not 0 <= int(size) <= MAX_BODY:
            raise ValueError('response exceeds budget')
        body = bytearray()
        while True:
            if time.monotonic() - started > 10:
                raise TimeoutError('response deadline exceeded')
            block = response.read1(min(4096, MAX_BODY + 1 - len(body)))
            if not block:
                break
            body.extend(block)
            if len(body) > MAX_BODY:
                raise ValueError('response exceeds budget')
        if size is not None and len(body) != int(size):
            raise ValueError('truncated response')
        return sanitize(json.loads(body.decode('utf-8')))
    finally:
        if response is not None:
            response.close()
        connection.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('host', help='Exact private LAN IPv4 supplied by the owner; no hostname or subnet')
    parser.add_argument('--output', type=Path, default=Path('.local/tv-identification.json'))
    args = parser.parse_args()
    try:
        observation = identify(args.host)
    except Exception:
        # Exceptions can contain raw server status lines. Do not print them or the response.
        parser.exit(1, 'Identification unavailable or refused; no raw response retained. Check the supplied TV address and ordinary developer-access prerequisites.\n')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(observation, indent=2) + '\n')
    print('Saved allowlisted identification fields; no raw response or unique identifiers retained.')


if __name__ == '__main__':
    main()
