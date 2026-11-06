"""Normalize one explicitly declared PLY input into a frozen local model."""
import argparse
import json
from pathlib import Path
from packages.construction.preview_pointcloud import build


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--snapshot',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--candidate-id',required=True);p.add_argument('--input-binding',type=Path)
    p.add_argument('--freeze-only',action='store_true',required=True)
    a=p.parse_args();job=json.loads(a.input_binding.read_bytes()) if a.input_binding else {}
    model=build(a.snapshot,a.output,a.candidate_id,job.get('input_binding'),batch_ref=job.get('batch_ref'))
    print(json.dumps({'model_id':model['id'],'stage':'model_frozen'}))


if __name__=='__main__':main()
