"""Read a pinned review and local observation journal; no implicit login or release."""
import argparse
import json
from pathlib import Path
from types import SimpleNamespace

from experiments.scripts.ifc_review_changes import _read
from packages.construction.ifc_review_snapshot import MAX_BYTES
from packages.data.ifc_workspace import read_json
from packages.infrastructure.spatial_observation_store import ObservationJournal
from packages.service.ifc_review_observations import read_review_observations
from packages.views.agent.ifc_offline_package import MAX_BYTES as PACKAGE_BYTES


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('snapshot', 'design-package', 'source', 'query', 'journal-root', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    for name in ('issuer', 'organization', 'workspace', 'now'):
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--ontology', type=Path)
    args = parser.parse_args()
    principal = SimpleNamespace(issuer=args.issuer, org_id=args.organization, workspace_id=args.workspace)
    result = read_review_observations(
        ObservationJournal(args.journal_root), principal, _read(args.snapshot, MAX_BYTES),
        query=read_json(args.query, 64 * 1024)[1], design_package=_read(args.design_package, PACKAGE_BYTES),
        expected_source=read_json(args.source, 4096)[1], now=args.now,
        ontology_raw=_read(args.ontology, 64 * 1024) if args.ontology else None)
    with args.output.open('x', encoding='utf-8') as stream:
        stream.write(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + '\n')


if __name__ == '__main__':
    main()
