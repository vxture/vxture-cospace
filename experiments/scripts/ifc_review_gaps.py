"""Inventory fixed review-input gaps; does not approve adoption or release."""
import argparse
import json
from pathlib import Path

from experiments.scripts.ifc_review_changes import _read
from packages.construction.ifc_review_snapshot import MAX_BYTES
from packages.data.ifc_workspace import read_json
from packages.service.ifc_review_gaps import assess_review_gaps
from packages.views.agent.ifc_offline_package import MAX_BYTES as PACKAGE_BYTES


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('snapshot', 'design-package', 'source', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--snapshot-sha256', required=True)
    parser.add_argument('--ontology', type=Path)
    parser.add_argument('--evidence-root', type=Path)
    args = parser.parse_args()
    result = assess_review_gaps(
        _read(args.snapshot, MAX_BYTES), expected_sha256=args.snapshot_sha256,
        design_package=_read(args.design_package, PACKAGE_BYTES), expected_source=read_json(args.source, 4096)[1],
        ontology_raw=_read(args.ontology, 64 * 1024) if args.ontology else None, evidence_root=args.evidence_root)
    with args.output.open('x', encoding='utf-8') as stream:
        stream.write(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + '\n')


if __name__ == '__main__':
    main()
