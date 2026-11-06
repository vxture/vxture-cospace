"""Package an existing supported acquisition snapshot for browser upload; source is read-only."""
import argparse
import json
from pathlib import Path
import zipfile
from packages.data.input_uploads import FORMATS,MAX_UPLOAD,MAX_EXPANDED,MAX_FILES
from packages.data.preview_inputs import inspect


def pack(snapshot,tracking,output,format=None):
    snapshot=Path(snapshot).resolve();tracking=Path(tracking).resolve() if tracking else None;output=Path(output)
    format=format or (FORMATS[0] if tracking else FORMATS[1])
    if output.exists() or output.resolve().is_relative_to(snapshot):raise ValueError('exclusive_output_outside_source_required')
    inspect(snapshot,tracking,format)
    if tracking:
        report=json.loads((snapshot/'report.json').read_bytes())
        files=[(snapshot/'report.json','snapshot/report.json'),(tracking,'tracking.json')]
        for name in report['members']:
            if not isinstance(name,str) or '/' in name or '\\' in name or ':' in name or not (snapshot/'raw'/name).resolve().is_relative_to(snapshot/'raw'):
                raise ValueError('input_member_outside_source')
        files += [(snapshot/'raw'/name,'snapshot/raw/'+name) for name in sorted(report['members'])]
    elif format=='ply_pointcloud':
        files=[(snapshot/'pointcloud.json','snapshot/pointcloud.json'),(snapshot/'cloud.ply','snapshot/cloud.ply')]
        if json.loads((snapshot/'pointcloud.json').read_bytes()).get('source_receipt_path')=='source.json':
            files.append((snapshot/'source.json','snapshot/source.json'))
    else:files=[(snapshot/'sample.json','snapshot/sample.json'),(snapshot/'sample.bag','snapshot/sample.bag')]
    if len(files)+1>MAX_FILES or sum(p.stat().st_size for p,_ in files)>MAX_EXPANDED-1024:raise ValueError('upload_package_budget')
    with output.open('xb') as stream,zipfile.ZipFile(stream,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=3) as archive:
        archive.writestr('input.json',json.dumps({'profile':'cospace.input-upload/0.1','format':format}))
        for path,name in files:archive.write(path,name)
    if output.stat().st_size>MAX_UPLOAD:raise ValueError('upload_package_budget')
    return {'format':format,'output':str(output),'bytes':output.stat().st_size,'source_unchanged':True}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--snapshot',type=Path,required=True)
    p.add_argument('--tracking',type=Path);p.add_argument('--output',type=Path,required=True);p.add_argument('--format',choices=FORMATS);a=p.parse_args()
    print(json.dumps(pack(a.snapshot,a.tracking,a.output,a.format),ensure_ascii=False))


if __name__=='__main__':main()
