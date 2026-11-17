"""Compare two fixed review snapshots without modifying either input."""
import argparse
import json
from pathlib import Path

from packages.construction.ifc_review_snapshot import MAX_BYTES
from packages.data.ifc_workspace import read_json
from packages.service.ifc_review_changes import compare_review_snapshots
from packages.views.agent.ifc_offline_package import MAX_BYTES as PACKAGE_BYTES


def _read(path, limit):
    with path.open('rb') as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise ValueError('review_input_budget')
    return raw


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('base', 'target', 'design-package', 'source', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    for name in ('base-sha256', 'target-sha256'):
        parser.add_argument('--' + name, required=True)
    for name in ('base-ontology', 'target-ontology'):
        parser.add_argument('--' + name, type=Path)
    args = parser.parse_args()
    result = compare_review_snapshots(
        _read(args.base, MAX_BYTES), _read(args.target, MAX_BYTES),
        base_sha256=args.base_sha256, target_sha256=args.target_sha256,
        design_package=_read(args.design_package, PACKAGE_BYTES), expected_source=read_json(args.source, 4096)[1],
        base_ontology=_read(args.base_ontology, 64 * 1024) if args.base_ontology else None,
        target_ontology=_read(args.target_ontology, 64 * 1024) if args.target_ontology else None)
    with args.output.open('x', encoding='utf-8') as stream:
        stream.write(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + '\n')


if __name__ == '__main__':
    main()
