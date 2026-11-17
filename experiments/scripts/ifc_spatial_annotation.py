"""Seed and check source-bound spatial annotations; no fact adoption."""
import argparse
import json
from pathlib import Path
from packages.spatial.ifc_annotations import seed, validate_annotations
from packages.construction.ifc_structure_review import structure_review
from packages.data.ifc_workspace import read_json

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ifc-root', type=Path, required=True)
    parser.add_argument('--ifc-sha256', required=True)
    parser.add_argument('--worksheet', type=Path, help='Check this worksheet instead of seeding one')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--evidence-root', type=Path, help='Check worksheet evidence bytes; requires --worksheet')
    args = parser.parse_args()
    if args.evidence_root is not None and args.worksheet is None:
        parser.error('--evidence-root requires --worksheet')
    review = structure_review(args.ifc_root, expected_catalog_sha256=args.ifc_sha256)
    if args.worksheet:
        _, document = read_json(args.worksheet, 8 * 1024 * 1024)
        result = validate_annotations(document, review, evidence_root=args.evidence_root)
    else:
        result = seed(review)
    with args.output.open('x', encoding='utf-8') as stream:
        stream.write(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + '\n')


if __name__ == '__main__':
    main()
