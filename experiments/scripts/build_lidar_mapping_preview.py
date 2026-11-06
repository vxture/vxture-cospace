"""Execute the laser mapping worker inside the existing frozen-model pipeline."""
import argparse
import json
from pathlib import Path
from packages.construction.preview_lidar_mapping import build

def main():
    p=argparse.ArgumentParser();p.add_argument('--snapshot',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--candidate-id',required=True)
    p.add_argument('--input-binding',type=Path,required=True);p.add_argument('--freeze-only',action='store_true',required=True)
    a=p.parse_args();job=json.loads(a.input_binding.read_bytes())
    if job['id']!=a.candidate_id or a.output.resolve().parent!=a.input_binding.resolve().parent:raise ValueError('mapping_job_binding')
    result=build(a.snapshot,a.output,job)
    print(json.dumps({'model_id':result['id'],'stage':'model_frozen','used_frames':result['construction']['used_frames']}))

if __name__=='__main__':main()
