"""Keep the bundled JRE's old VC runtime from shadowing Qt's runtime."""
from pathlib import Path
import shutil
import sys

import pefile


def version(path):
    with pefile.PE(str(path), fast_load=True) as image:
        image.parse_data_directories(
            directories=[pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_RESOURCE']]
        )
        info = image.VS_FIXEDFILEINFO[0]
        return (info.FileVersionMS >> 16, info.FileVersionMS & 65535,
                info.FileVersionLS >> 16, info.FileVersionLS & 65535)


def align(bundle):
    internal = bundle / '_internal'
    qt = internal / 'PyQt6/Qt6/bin'
    # Qt uses the Windows ICU ABI (ucnv_open), whereas developer tools such as
    # Poppler can provide a same-named ICU with versioned exports (ucnv_open_78).
    # Let Windows resolve its own system DLL instead of shipping a PATH copy.
    system_icu = internal / 'icuuc.dll'
    if system_icu.exists():
        system_icu.unlink()
        print('Removed shared icuuc.dll; Qt uses the Windows system ICU')
    # Compare with the already collected Python runtime as well: a newer Python
    # may need a newer VC runtime than Qt. Never touch the pinned JRE payload.
    for name in ('MSVCP140.dll', 'MSVCP140_1.dll', 'MSVCP140_2.dll',
                 'VCRUNTIME140.dll', 'VCRUNTIME140_1.dll'):
        source = qt / name
        if not source.is_file():
            raise ValueError(f'Qt runtime DLL is missing: {source}')
        destination = internal / name
        if not destination.is_file() or version(source) > version(destination):
            shutil.copy2(source, destination)
        print(f'{name}: {".".join(map(str, version(destination)))}')


if __name__ == '__main__':
    align(Path(sys.argv[1]))
