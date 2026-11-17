"""Create a new local review snapshot directory; no login, adoption or release."""
import argparse
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

from packages.construction.ifc_review_snapshot import build_review_snapshot
from packages.data.ifc_workspace import IfcWorkspace, read_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bindings', type=Path, required=True)
    parser.add_argument('--space', required=True)
    parser.add_argument('--catalog-sha256', required=True)
    parser.add_argument('--worksheet', type=Path)
    parser.add_argument('--mapping', type=Path)
    parser.add_argument('--ontology', type=Path)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    if (args.mapping is None) != (args.ontology is None):
        parser.error('--mapping and --ontology must be supplied together')
    worksheet = read_json(args.worksheet, 8 * 1024 * 1024)[1] if args.worksheet else None
    mapping = read_json(args.mapping, 1024 * 1024)[1] if args.mapping else None
    ontology = read_json(args.ontology, 64 * 1024)[0] if args.ontology else None
    # Local file tool only: this adapter performs no business authorization.
    workspace = IfcWorkspace(SimpleNamespace(read=lambda *args: None), None, args.bindings)
    result = build_review_snapshot(workspace, args.space, args.catalog_sha256,
                                   worksheet=worksheet, mapping=mapping, ontology_raw=ontology)
    args.output_dir.mkdir(parents=True, exist_ok=False)
    files = {'snapshot.json': result['snapshot'], 'design.bin': result['design_package']}
    for name, raw in files.items():
        (args.output_dir / name).write_bytes(raw)
    # Receipt last; keep its digest/pins separately in a trusted context.
    receipt = {'profile': 'cospace.ifc-review-export/0.1',
               'source': json.loads(result['snapshot'])['source'],
               'members': [{'name': name, 'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}
                           for name, raw in files.items()], 'real_release_ready': False}
    (args.output_dir / 'receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
