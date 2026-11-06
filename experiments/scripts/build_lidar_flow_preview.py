"""Build a local LiDAR frame candidate; no SLAM, poses or global transforms."""
import argparse
import json
from pathlib import Path
from packages.construction.preview_lidar import build


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--snapshot',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--candidate-id',required=True);p.add_argument('--input-binding',type=Path)
    p.add_argument('--freeze-only',action='store_true')
    a=p.parse_args();binding=json.loads(a.input_binding.read_bytes())['input_binding'] if a.input_binding else None
    model=build(a.snapshot,a.output,a.candidate_id,binding,freeze_only=a.freeze_only,
        batch_ref=json.loads(a.input_binding.read_bytes()).get('batch_ref') if a.input_binding else None)
    if a.freeze_only:
        print(json.dumps({'model_id':model['id'],'stage':'model_frozen'}));return
    if a.input_binding and (batch_ref:=json.loads(a.input_binding.read_bytes()).get('batch_ref')):
        model['source']['batch_ref']=batch_ref
        (a.output/'model.json').write_text(json.dumps(model,indent=2),encoding='utf-8')
    print(json.dumps({'model_id':model['id'],**model['construction']}))


if __name__=='__main__':main()
