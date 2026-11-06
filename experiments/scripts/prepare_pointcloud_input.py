"""Copy a PLY into an exclusive declared-input folder; never modifies the source."""
import argparse
import json
from pathlib import Path
import shutil
from packages.construction.preview_model import digest
from packages.data.preview_pointcloud import read_cloud,Manifest


def prepare(cloud,output,*,points,frame_id,axes,scope,source_manifest,source_member_sha256,description,kind):
    cloud=Path(cloud).resolve();output=Path(output).resolve();source_manifest=Path(source_manifest).resolve()
    if output.exists() or output==cloud.parent or cloud.is_relative_to(output):raise ValueError('exclusive_output_required')
    doc={'profile':'cospace.pointcloud-input/0.1',
        'cloud':{'path':'cloud.ply','sha256':digest(cloud),'bytes':cloud.stat().st_size,'points':points},
        'coordinates':{'unit':'m','frame_id':frame_id,'axes':axes,'scope':scope,'scene_alignment':'unverified'},
        'provenance':{'kind':kind,'source_manifest_sha256':digest(source_manifest),
                      'source_member_sha256':source_member_sha256,'description':description}}
    Manifest.model_validate(doc)
    output.mkdir(parents=True);shutil.copyfile(cloud,output/'cloud.ply')
    (output/'pointcloud.json').write_text(json.dumps(doc,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    checked=read_cloud(output)[0]
    return {'snapshot':str(output),'source_unchanged':digest(cloud)==doc['cloud']['sha256'],**checked}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--cloud',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--points',type=int,required=True);p.add_argument('--frame-id',required=True)
    p.add_argument('--axes',nargs=3,required=True);p.add_argument('--scope',choices=['sensor_local','scene_local'],required=True)
    p.add_argument('--source-manifest',type=Path,required=True);p.add_argument('--source-member-sha256',required=True)
    p.add_argument('--description',required=True);p.add_argument('--kind',choices=['derived_single_frame','existing_pointcloud'],required=True)
    a=p.parse_args();args=vars(a);cloud=args.pop('cloud');output=args.pop('output')
    print(json.dumps(prepare(cloud,output,**args),ensure_ascii=False))


if __name__=='__main__':main()
