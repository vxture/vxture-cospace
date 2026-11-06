"""Offline-only CLI. Requires Python and NumPy; no service or source imagery."""
import argparse
import json
import zipfile
from pathlib import Path
from packages.views.agent.preview_offline import OfflinePreview
from packages.spatial.preview_range import DEFAULT_RANGE_CELLS


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bundle', type=Path)
    parser.add_argument('--publication', required=True)
    parser.add_argument('--sha256', required=True, help='Expected delivery package SHA256')
    query=parser.add_mutually_exclusive_group(required=True)
    query.add_argument('--point', nargs=3, type=float)
    query.add_argument('--object-id',help='Read one fixed semantic object')
    query.add_argument('--objects',action='store_true',help='List fixed semantic objects')
    query.add_argument('--bounds',nargs=6,type=float,metavar=('MIN_X','MIN_Y','MIN_Z','MAX_X','MAX_Y','MAX_Z'),help='Select surface cell centers in a half-open AABB')
    parser.add_argument('--frame-id',help='Required with --bounds; must match the fixed model frame')
    parser.add_argument('--limit',type=int,help='Range-only maximum cells, 1..4096; excess returns no cells')
    args = parser.parse_args()
    if args.bounds is not None and not args.frame_id:parser.error('--bounds requires --frame-id')
    if args.bounds is None and (args.frame_id is not None or args.limit is not None):parser.error('--frame-id and --limit require --bounds')
    try:
        model = OfflinePreview.load(args.bundle, args.publication, args.sha256)
        if args.bounds is not None:
            result=model.query_range([args.bounds[:3],args.bounds[3:]],args.frame_id,args.limit if args.limit is not None else DEFAULT_RANGE_CELLS)
        else:result=model.query(args.point) if args.point is not None else model.objects(args.object_id)
        print(json.dumps(result, ensure_ascii=False, allow_nan=False))
        if result.get('status')=='limit_exceeded':parser.exit(3)
    except (ValueError, OSError, KeyError, zipfile.BadZipFile, EOFError) as exc:
        parser.exit(2, f'offline_preview_refused: {exc}\n')


if __name__ == '__main__': main()
