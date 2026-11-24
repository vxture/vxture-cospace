"""Assemble a local distributable from the standalone UI build and one wheel."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--wheel', required=True, type=Path)
    parser.add_argument('--ui-dir', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    version = re.fullmatch(r'vxture_ontology-(.+)-py3-none-any\.whl', args.wheel.name)
    if not version or args.output.suffix.lower() != '.zip':
        parser.error('expected the ontology wheel and a new .zip destination')

    from packages.ontology.kernel.local_host.static import ASSET_PATH, WorkbenchAssets

    ui = WorkbenchAssets(args.ui_dir)
    index, _, _ = ui.read('/')
    members = {f'wheel/{args.wheel.name}': args.wheel.read_bytes(), 'ui/index.html': index}
    for asset in sorted((ui.root / 'assets').iterdir()):
        path = f'/assets/{asset.name}'
        if not ASSET_PATH.fullmatch(path) or asset.is_symlink() or not asset.is_file():
            parser.error(f'unexpected build member: {asset.name}')
        members['ui' + path], _, _ = ui.read(path)
    references = re.findall(r'(?:src|href)="(/assets/[^"\s]+)"', index.decode('utf-8'))
    if not any(p.endswith('.js') for p in references) or not all('ui' + p in members for p in references):
        parser.error('the workbench HTML has missing build assets')
    docs = Path(__file__).resolve().parents[2] / 'docs/architecture/本体工作台安装与回退-B09d.md'
    members['INSTALL.md'] = docs.read_bytes()
    members['manifest.json'] = (json.dumps({'profile': 'vxture.ontology-workbench-dist/0.1', 'version': version[1],
                                           'files': {name: sha256(data).hexdigest() for name, data in members.items()}},
                                          indent=2, sort_keys=True) + '\n').encode()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(args.output, 'x') as out:
        for name, data in sorted(members.items()):
            out.writestr(ZipInfo(name), data, compress_type=ZIP_DEFLATED)
    print(args.output.resolve())


if __name__ == '__main__':
    main()
