"""Offline surface queries with an explicit publication, scene and index digest."""
import argparse
import json
from pathlib import Path
import zipfile
from packages.views.agent.partitioned_preview import PartitionedPreview
from packages.spatial.preview_range import DEFAULT_RANGE_CELLS


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bundle',type=Path)
    parser.add_argument('--publication',required=True)
    parser.add_argument('--index-sha256',required=True,help='Expected index SHA256 from the authorized delivery record')
    ownership=parser.add_mutually_exclusive_group(required=True)
    ownership.add_argument('--space-id')
    ownership.add_argument('--legacy',action='store_true',help='Explicitly accept an unassigned legacy publication')
    parser.add_argument('--frame-id',required=True)
    query=parser.add_mutually_exclusive_group(required=True)
    query.add_argument('--point',nargs=3,type=float)
    query.add_argument('--bounds',nargs=6,type=float,metavar=('MIN_X','MIN_Y','MIN_Z','MAX_X','MAX_Y','MAX_Z'))
    parser.add_argument('--limit',type=int)
    args=parser.parse_args()
    if args.point is not None and args.limit is not None:parser.error('--limit requires --bounds')
    try:
        model=PartitionedPreview(args.bundle,args.publication,args.index_sha256,args.space_id)
        result=(model.query(args.point,args.frame_id) if args.point is not None else
                model.query_range([args.bounds[:3],args.bounds[3:]],args.frame_id,
                                  args.limit if args.limit is not None else DEFAULT_RANGE_CELLS))
        print(json.dumps(result,ensure_ascii=False,allow_nan=False))
        if not result['result_complete']:parser.exit(3)
    except (ValueError,OSError,KeyError,TypeError,OverflowError,zipfile.BadZipFile,EOFError):
        parser.exit(2,'partitioned_preview_refused: invalid binding, archive or query\n')


if __name__=='__main__':main()
