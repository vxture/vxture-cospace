"""Read a fixed synthetic subset using a separately supplied source pin."""
import argparse
import json
from pathlib import Path

from experiments.scripts.inspect_scene_graph import unique_keys
from experiments.scripts.scene_input_boundary import read_source
from packages.spatial.scene_graph import MAX_DOCUMENT_BYTES
from packages.views.agent.scene_reader import SceneSubsetReader
from packages.views.agent.scene_subset import MAX_PACKAGE_BYTES


def load(path, root, budget):
    return json.loads(read_source(path, root=root, suffix='.json', max_bytes=budget), object_pairs_hook=unique_keys)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input-root', type=Path, required=True)
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--expected-source', type=Path, required=True, help='Trusted source pin, not taken from package')
    parser.add_argument('--source-document', type=Path, help='Optional complete source for faithful-selection verification')
    operations = parser.add_mutually_exclusive_group()
    operations.add_argument('--entity')
    operations.add_argument('--connections-for')
    operations.add_argument('--type')
    args = parser.parse_args()
    try:
        package = load(args.package, args.input_root, MAX_PACKAGE_BYTES)
        expected = load(args.expected_source, args.input_root, 4096)
        source = load(args.source_document, args.input_root, MAX_DOCUMENT_BYTES) if args.source_document else None
        reader = SceneSubsetReader(package, expected, source_document=source)
        if args.entity is not None:
            result = reader.entity(args.entity)
        elif args.connections_for is not None:
            result = reader.connections(args.connections_for)
        else:
            result = reader.list_entities(type_id=args.type)
        print(json.dumps(result, ensure_ascii=False, allow_nan=False, indent=2))
    except (OSError, ValueError) as exc:
        print(json.dumps(dict(error=str(exc)), ensure_ascii=False))
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
