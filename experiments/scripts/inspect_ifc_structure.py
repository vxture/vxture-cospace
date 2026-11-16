"""Extract IFC design structure into ignored local evidence using the isolated parser."""
import argparse
import json
import os
from pathlib import Path
import re

from packages.data.ifc_inspection import MAX_SOURCE_BYTES, digest
from packages.data.ifc_structure import inspect_ifc_structure

REPO_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_ROOT = REPO_ROOT / 'output' / 'sg2'


def source_path(relative):
    configured = os.environ.get('COSPACE_SCENE_INPUT_ROOT')
    if not configured:
        raise ValueError('source_root_not_configured')
    root = Path(configured).resolve(strict=True)
    if relative.anchor or not root.is_dir():
        raise ValueError('relative_ifc_required')
    source = (root / relative).resolve(strict=True)
    if not source.is_relative_to(root) or source.suffix.lower() != '.ifc':
        raise ValueError('source_outside_allowed_root_or_not_ifc')
    if not source.is_file() or not 1 <= source.stat().st_size <= MAX_SOURCE_BYTES:
        raise ValueError('ifc_source_invalid_or_budget')
    return source


def output_path(run_id):
    if not re.fullmatch(r'[a-z][a-z0-9-]{0,59}', run_id):
        raise ValueError('invalid_run_id')
    target = OUTPUT_ROOT / run_id
    if target.resolve() != target or target.is_symlink():
        raise ValueError('output_redirected')
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('relative_ifc', type=Path)
    parser.add_argument('run_id')
    args = parser.parse_args()
    try:
        source = source_path(args.relative_ifc)
        report = inspect_ifc_structure(source, output_path(args.run_id), expected_sha256=digest(source))
    except (OSError, ValueError, RuntimeError, KeyError) as exc:
        parser.exit(2, f'ifc_structure_refused: {type(exc).__name__}\n')
    structure = report['structure']
    print(json.dumps({'role_counts': structure['role_counts'], 'relations': len(structure['relations']),
                      'missing_declared_roles': structure['missing_declared_roles'],
                      'geometry_counts': report['geometry_counts'],
                      'alignment_verified': report['alignment_verified']}))


if __name__ == '__main__':
    main()
