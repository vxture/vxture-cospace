"""Prepare immutable, bounded display LODs from a verified full scene intake."""
import argparse
import json
from pathlib import Path
from packages.data.scene_pointcloud_tiles import prepare_tiles


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,required=True)
    p.add_argument('--scene-sha256',required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    value=prepare_tiles(a.root,a.scene_sha256,a.output,lambda v:print(json.dumps(v),flush=True))
    print(json.dumps({'tiles':len(value['tiles']),'complete':True}))


if __name__=='__main__':main()
