"""CI packaging: inventory only application files before compiling the installer."""
import hashlib
import json
from pathlib import Path
import re


def inventory(bundle, version):
    files = {}
    for path in sorted(bundle.rglob('*')):
        if path.is_symlink():
            raise ValueError('Application payload must not contain symlinks')
        if path.is_file() and path.name != 'manaforge-files.json':
            with path.open('rb') as stream:
                files[path.relative_to(bundle).as_posix()] = hashlib.file_digest(stream, 'sha256').hexdigest()
    (bundle / 'manaforge-files.json').write_text(
        json.dumps(dict(version=version, files=files), sort_keys=True), encoding='utf-8')


if __name__ == '__main__':
    root = Path(__file__).resolve().parent.parent
    version = re.search(r'^APP_VERSION = "([^"]+)"',
                        (root / 'Mtg_Projects/mtg_proxy/constants.py').read_text(), re.MULTILINE)[1]
    inventory(root / 'Mtg_Projects/dist/Manaforge', version)
