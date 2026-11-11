"""Idempotent runtime numbering and explicitly labeled demo-time enrichment."""
import argparse
import json
from pathlib import Path
from packages.lifecycle.business_versions import BusinessVersions


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--production', action='store_true', required=True,
                        help='Operate only on the production container business mount /data/runtime')
    parser.add_argument('--demo-times', action='store_true', help='Persist estimated presentation times; keep original audit records unchanged')
    args=parser.parse_args()
    runtime=Path('/data/runtime')
    if runtime.is_symlink() or runtime.resolve()!=runtime or not (runtime/'preview-directory'/'space').is_dir():
        parser.error('existing_business_runtime_required')
    versions=BusinessVersions(runtime)
    result=versions.sync()
    if args.demo_times:
        result['demo_timelines_added']=versions.estimate_demo_times()
    print(json.dumps(result))


if __name__=='__main__':
    main()
