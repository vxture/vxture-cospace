"""Prepare source-frame structural review tasks without inventing connections."""
import argparse
import json
from pathlib import Path
from packages.construction.ifc_structure_review import structure_review

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ifc-root', type=Path, required=True)
    parser.add_argument('--ifc-sha256', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = structure_review(args.ifc_root, expected_catalog_sha256=args.ifc_sha256)
    with args.output.open('x', encoding='utf-8') as stream:
        stream.write(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + '\n')


if __name__ == '__main__':
    main()
