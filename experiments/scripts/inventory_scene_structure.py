"""Read-only, bounded IFC text inventory. Counts are declarations, not geometry."""
from collections import Counter
import argparse
import hashlib
import json
import os
from pathlib import Path
import re

from experiments.scripts.scene_input_boundary import read_source

MAX_IFC_BYTES = 128 * 1024 * 1024


def inventory(path, *, root=None):
    path = Path(path)
    if path.suffix.lower() != '.ifc':
        raise ValueError('ifc_required')
    raw = read_source(path, root=root if root is not None else os.environ.get('COSPACE_SCENE_INPUT_ROOT'),
                      suffix='.ifc', max_bytes=MAX_IFC_BYTES)
    # Deliberately not an IFC parser: ignore comments and strings before counting instances.
    text = raw.decode('utf-8-sig')
    schema = re.search(r"FILE_SCHEMA\s*\(\s*\(\s*'([^']+)'", text, re.I)
    clean = re.sub(r"/\*.*?\*/|'(?:''|[^'])*'", ' ', text, flags=re.S)
    counts = Counter(re.findall(r'#\d+\s*=\s*(IFC[A-Z0-9_]+)\s*\(', clean.upper()))
    if not schema or not counts:
        raise ValueError('ifc_declarations_not_found')
    selected = ('IFCBUILDING', 'IFCBUILDINGSTOREY', 'IFCSPACE', 'IFCDOOR', 'IFCSTAIR',
                'IFCSTAIRFLIGHT', 'IFCWALL', 'IFCSLAB', 'IFCELECTRICDISTRIBUTIONBOARD',
                'IFCPROJECTEDCRS', 'IFCMAPCONVERSION')
    return {'profile': 'cospace.ifc-structure-inventory/0.1', 'source_name': path.name,
            'source_sha256': hashlib.sha256(raw).hexdigest(), 'source_bytes': len(raw),
            'declared_schema': schema.group(1),
            'declaration_counts': {key: counts[key] for key in selected},
            'geometry_decoded': False, 'alignment_verified': False,
            'semantics_verified': False,
            'limitations': ['text_declarations_only', 'no_relationship_or_geometry_validation',
                            'absence_of_a_class_does_not_prove_absence_in_the_building']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('ifc', type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(inventory(args.ifc), ensure_ascii=False, indent=2))
    except (OSError, ValueError) as exc:
        print(json.dumps({'error': str(exc)}, ensure_ascii=False))
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
