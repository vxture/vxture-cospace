"""Inspect a captured NCLT ms25 CSV, keeping units and frames separate."""
import argparse
import json
from pathlib import Path
from packages.data.nclt_input import MAX_BYTES, inspect_ms25


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('csv',type=Path)
    parser.add_argument('--expected-sha256')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists() or args.output.resolve()==args.csv.resolve(): parser.error('output must be a new file')
    with args.csv.open('rb') as source: raw=source.read(MAX_BYTES+1)
    if len(raw)>MAX_BYTES: parser.error('input exceeds file budget; no partial digest report written')
    report=inspect_ms25(raw,args.expected_sha256)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('x',encoding='utf-8') as target:
        json.dump(report,target,ensure_ascii=False,indent=2,allow_nan=False)
    print(json.dumps({k:report[k] for k in ('rows_seen','valid_rows','structural_precheck_passed','time','errors')}))
    return 0 if report['structural_precheck_passed'] else 2


if __name__=='__main__': raise SystemExit(main())
