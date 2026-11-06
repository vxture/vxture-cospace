"""Derive one view from an immutable model; never reads original sensor data."""
import argparse
import json
from pathlib import Path
from packages.construction.preview_derivations import derive

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('frozen','task','output'):parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args();derive(args.frozen,args.output,json.loads(args.task.read_bytes()))
