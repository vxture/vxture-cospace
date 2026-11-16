"""Read-only D0 synthetic graph inspection; no imports, writes or publication."""
import argparse
import json
from pathlib import Path

from experiments.scripts.scene_input_boundary import read_source
from packages.spatial.scene_graph import MAX_DOCUMENT_BYTES, SceneGraphReader

SOURCE_ROOT = Path(__file__).resolve().parents[2] / 'examples/scene-graph'

def unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate_json_key')
        result[key] = value
    return result


def load_graph(path, *, root=None):
    raw = read_source(path, root=SOURCE_ROOT if root is None else root,
                      suffix='.json', max_bytes=MAX_DOCUMENT_BYTES)
    return json.loads(raw, object_pairs_hook=unique_keys)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('document', type=Path)
    parser.add_argument('--entity')
    parser.add_argument('--connections-for')
    args = parser.parse_args()
    try:
        reader = SceneGraphReader(load_graph(args.document))
        result = {'validation': reader.report}
        if args.entity:
            result['entity'] = reader.entity(args.entity)
        if args.connections_for:
            result['connections'] = reader.connections(args.connections_for)
        print(json.dumps(result, ensure_ascii=False, allow_nan=False, indent=2))
    except (OSError, ValueError) as exc:
        print(json.dumps({'error': str(exc)}, ensure_ascii=False))
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
