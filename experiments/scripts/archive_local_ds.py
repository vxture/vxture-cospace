"""Archive the already installed published DS packages without modifying their contents."""
import hashlib
import json
from pathlib import Path
import tarfile

source = Path('D:/MyWebSite/vxtureagents/vx-agent-yucer')
dest = Path('apps/workbench/vendor')
dest.mkdir(exist_ok=True)
packages = {
    'design-system': source / 'portals/app/node_modules/@vxture/design-system',
    'design-ui': source / 'portals/app/node_modules/@vxture/design-ui',
    'design-tokens': next((source / 'node_modules/.pnpm').glob('@vxture+design-tokens@4.0.0*/node_modules/@vxture/design-tokens')),
}
manifest = []
for name, folder in packages.items():
    package = json.loads((folder / 'package.json').read_text(encoding='utf-8'))
    target = dest / f'vxture-{name}-{package["version"]}.tgz'
    with tarfile.open(target, 'w:gz') as archive:
        for item in sorted(folder.rglob('*')):
            if item.is_file() and 'node_modules' not in item.relative_to(folder).parts:
                archive.add(item, arcname='package/' + item.relative_to(folder).as_posix(), recursive=False)
    manifest.append({'name': package['name'], 'version': package['version'], 'archive': target.name, 'sha256': hashlib.sha256(target.read_bytes()).hexdigest(), 'source': str(folder)})
(dest / 'provenance.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps([{'name': m['name'], 'version': m['version']} for m in manifest]))
