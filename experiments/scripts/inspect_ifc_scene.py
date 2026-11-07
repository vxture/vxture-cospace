"""Offline IFC geometry inspection; use an isolated native-parser environment."""
import argparse
import json
from pathlib import Path
from packages.data.ifc_inspection import inspect_ifc,digest


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ifc',type=Path,required=True)
    parser.add_argument('--sha256',required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    try:
        result=inspect_ifc(args.ifc,args.output,expected_sha256=args.sha256)
        print(json.dumps(dict(state=result['state'],products=result['product_count'],geometry_counts=result['geometry_counts'],
            bounds_m=result['bounds_m'],catalog_sha256=digest(args.output/'ifc.json')),allow_nan=False))
    except (ValueError,OSError,RuntimeError,KeyError):parser.exit(2,'ifc_inspection_refused: check input, parser and budgets\n')


if __name__=='__main__':main()
