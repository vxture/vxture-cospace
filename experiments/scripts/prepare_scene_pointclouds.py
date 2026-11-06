"""Offline full-resolution LAS format-2 intake into one scene's bounded shards."""
import argparse
import json
from pathlib import Path
from packages.data.scene_pointcloud_intake import intake


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, action='append', required=True)
    parser.add_argument('--ifc', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--scene-name', required=True)
    parser.add_argument('--tile-size', type=float, default=20.)
    parser.add_argument('--chunk-points', type=int, default=250_000)
    parser.add_argument('--unit-basis', required=True, choices=['assumed_metre_for_flow_validation', 'verified_metre'])
    args = parser.parse_args()
    def progress(value):
        if value['decoded'] == value['expected'] or value['decoded'] % 5_000_000 == 0:
            print(json.dumps(value, ensure_ascii=False), flush=True)
    result = intake(args.source, args.output, scene_name=args.scene_name, tile_size=args.tile_size,
                    chunk_points=args.chunk_points, unit_basis=args.unit_basis, ifc=args.ifc, progress=progress)
    print(json.dumps({k: result[k] for k in ('state', 'total_points', 'total_shards', 'origin')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
