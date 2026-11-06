"""Register a sealed local input; catalog output stays in the project workspace."""
import argparse
import json
from pathlib import Path
from packages.data.preview_inputs import PreviewInputs
from packages.lifecycle.preview_spaces import PreviewSpaces


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--catalog',type=Path,default=Path('var/nyu/preview-inputs'))
    p.add_argument('--label',required=True)
    p.add_argument('--snapshot',type=Path,required=True)
    p.add_argument('--tracking',type=Path)
    p.add_argument('--format',choices=['nyu_rgbd_with_existing_poses','ros1_lidar_single_frame'],default='nyu_rgbd_with_existing_poses')
    p.add_argument('--space-id',help='Explicit space ownership; omission keeps a legacy unassigned input')
    p.add_argument('--directory',type=Path,default=Path('var/nyu/preview-directory'))
    a=p.parse_args()
    try:
        directory=PreviewSpaces(a.directory) if a.space_id else None
        record=PreviewInputs(a.catalog,directory).register(a.label,a.snapshot,a.tracking,a.space_id,a.format)
    except (ValueError,OSError,KeyError,TypeError) as exc: p.exit(2,f'input_registration_refused: {exc}\n')
    print(json.dumps(record,ensure_ascii=True))


if __name__=='__main__': main()
