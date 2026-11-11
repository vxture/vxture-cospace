"""Idempotent runtime numbering and explicitly labeled demo-time enrichment."""
import argparse
import json
from pathlib import Path
from packages.lifecycle.business_versions import BusinessVersions


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--demo-times', action='store_true', help='Persist estimated presentation times; keep original audit records unchanged')
    args=parser.parse_args()
    if not (args.runtime/'preview-directory'/'space').is_dir():
        parser.error('existing_business_runtime_required')
    versions=BusinessVersions(args.runtime)
    result=versions.sync()
    if args.demo_times:
        result['demo_timelines_added']=versions.estimate_demo_times()
    print(json.dumps(result))


if __name__=='__main__':
    main()
