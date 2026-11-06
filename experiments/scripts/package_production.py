"""Allowlisted software bundle; never includes local datasets, sessions or secrets."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import tarfile

PATTERNS=('packages/**/*.py','experiments/scripts/*.py','contracts/schemas/*.json',
          'configs/ontology/*.json','apps/workbench/dist/**/*','deploy/linux/*','pyproject.toml','uv.lock')


def package(root,target,identity):
    root,target=Path(root).resolve(),Path(target).resolve()
    if not re.fullmatch(r'[a-z0-9][a-z0-9.-]{0,80}',identity):raise ValueError('release_identifier_required')
    paths=sorted({p for pattern in PATTERNS for p in root.glob(pattern) if p.is_file()})
    files={}
    for path in paths:
        if path.is_symlink() or not path.resolve().is_relative_to(root):raise ValueError('bundle_link_rejected')
        name=path.relative_to(root).as_posix()
        if '__pycache__' in path.parts or path.suffix=='.pyc':continue
        files[name]={'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'bytes':path.stat().st_size}
    if 'apps/workbench/dist/layout.html' not in files or 'deploy/linux/requirements.lock' not in files:
        raise ValueError('compiled_ui_and_locked_requirements_required')
    manifest={'profile':'cospace.production-software/0.1','release':identity,'files':files,
              'secrets_included':False,'business_data_included':False}
    target.parent.mkdir(parents=True,exist_ok=True)
    with target.open('xb') as stream:
        with tarfile.open(fileobj=stream,mode='w:gz') as archive:
            for name in [*files,'release.json']:
                raw=json.dumps(manifest,ensure_ascii=False,indent=2).encode() if name=='release.json' else (root/name).read_bytes()
                entry=tarfile.TarInfo(name);entry.size=len(raw);entry.mode=0o644;entry.mtime=0
                archive.addfile(entry,io.BytesIO(raw))
    return {'release':identity,'bundle':str(target),'sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'files':len(files)}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--release',required=True)
    a=p.parse_args();print(json.dumps(package(Path.cwd(),a.output,a.release)))


if __name__=='__main__':main()
