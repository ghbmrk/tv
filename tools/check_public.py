#!/usr/bin/env python3
"""Check tracked public files, not ignored private research or local state."""
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parent.parent


def main():
    result = subprocess.run(['git', 'ls-files', '-z'], cwd=ROOT, capture_output=True, check=True)
    errors = []
    # Only these generated product images may be public; owner photos/vendor binaries remain forbidden.
    manifest = json.loads((ROOT / 'docs/STORYBOOK_ASSETS.json').read_text())
    expected = {'android/app/src/main/assets/storybook/background.png', 'android/app/src/main/assets/storybook/posters.png'}
    generated = {item['path']: item for item in manifest['assets']}
    if set(generated) != expected:
        errors.append('unexpected generated product asset set')
    for raw in result.stdout.split(b'\0'):
        if not raw:
            continue
        name = raw.decode()
        path = ROOT / name
        if name in expected:
            record = generated.get(name, {})
            if path.stat().st_size > 8 * 1024**2 or path.stat().st_size != record.get('bytes') or hashlib.sha256(path.read_bytes()).hexdigest() != record.get('sha256'):
                errors.append(f'generated product asset digest/size mismatch: {name}')
            continue
        if any(part in {'.local', '.gradle', '.kotlin', '__pycache__', 'build'} for part in path.relative_to(ROOT).parts) or name.startswith(('reference/firmware/', 'reference/source/')) or name.endswith(('.jks', '.keystore', '.jpg', '.png', '.zip', '.bin', '.msd')):
            errors.append(f'private/binary artifact tracked: {name}')
        if path.stat().st_size > 1024 * 1024:
            errors.append(f'large public artifact: {name}')
            continue
        text = path.read_text()
        if re.search(r'gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----', text):
            errors.append(f'credential pattern: {name}')
        if name.endswith('.json'):
            json.loads(text)
    if (ROOT / 'examples/experience.json').read_bytes() != (ROOT / 'android/app/src/main/assets/experience.json').read_bytes():
        errors.append('Android and host example documents differ')
    if (ROOT / 'examples/storybook.json').read_bytes() != (ROOT / 'android/app/src/main/assets/storybook.json').read_bytes():
        errors.append('Android and host storybook documents differ')
    if errors:
        raise SystemExit('\n'.join(errors))
    print('Tracked-file publication checks passed (not a comprehensive secret audit).')


if __name__ == '__main__':
    main()
