"""Query candidate regions using a fixed local review snapshot and design package."""
import argparse
import json
from pathlib import Path

from experiments.scripts.ifc_review_changes import _read
from packages.construction.ifc_review_snapshot import MAX_BYTES
from packages.data.ifc_workspace import read_json
from packages.service.ifc_review_regions import query_review_regions
from packages.views.agent.ifc_offline_package import MAX_BYTES as PACKAGE_BYTES


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('snapshot', 'design-package', 'source', 'query', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--ontology', type=Path)
    args = parser.parse_args()
    result = query_review_regions(
        _read(args.snapshot, MAX_BYTES), query=read_json(args.query, 4096)[1],
        design_package=_read(args.design_package, PACKAGE_BYTES), expected_source=read_json(args.source, 4096)[1],
        ontology_raw=_read(args.ontology, 64 * 1024) if args.ontology else None)
    with args.output.open('x', encoding='utf-8') as stream:
        stream.write(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + '\n')


if __name__ == '__main__':
    main()
