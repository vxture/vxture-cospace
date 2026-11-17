"""Read a downloaded declaration snapshot with independently supplied byte and source pins."""
import argparse
import json
from pathlib import Path

from packages.views.agent.ifc_structure_exchange import MAX_BYTES, inspect_structure_snapshot, snapshot_summary


def bounded_bytes(path, maximum):
    with path.open('rb') as stream:
        raw = stream.read(maximum + 1)
    if len(raw) > maximum:
        raise ValueError('snapshot_read_budget')
    return raw


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('snapshot', type=Path)
    parser.add_argument('sha256')
    parser.add_argument('trusted_source', type=Path)
    args = parser.parse_args()
    source = json.loads(bounded_bytes(args.trusted_source, 2048))
    value = inspect_structure_snapshot(bounded_bytes(args.snapshot, MAX_BYTES),
                                       expected_sha256=args.sha256, expected_source=source)
    print(json.dumps(snapshot_summary(value), ensure_ascii=False, sort_keys=True))


if __name__ == '__main__':
    main()
