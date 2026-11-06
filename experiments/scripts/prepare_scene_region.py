"""Read selected sources/region into a bounded PLY with a portable composition receipt."""
import argparse
import json
from pathlib import Path
from packages.data.scene_pointcloud_region import SceneRegions


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--scene-sha256', required=True)
    parser.add_argument('--source', action='append', required=True)
    parser.add_argument('--bounds', type=float, nargs=6, required=True, metavar=('X0','Y0','Z0','X1','Y1','Z1'))
    parser.add_argument('--limit', type=int, default=250_000)
    parser.add_argument('--voxel-size', type=float, default=0.)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = SceneRegions(args.root, args.scene_sha256).prepare(args.output, args.source,
              [args.bounds[:3], args.bounds[3:]], limit=args.limit, voxel_size=args.voxel_size)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
