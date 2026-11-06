"""CLI for the optional offline ROS1 structural adapter; no ROS runtime."""
import argparse
import json
from pathlib import Path

from packages.data.bag_preflight import inspect_bag


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('bag',type=Path)
    parser.add_argument('--lidar-topic',default='/points_raw')
    parser.add_argument('--imu-topic',default='/imu')
    parser.add_argument('--expected-sha256')
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    if args.output.resolve()==args.bag.resolve(): parser.error('output must differ from input')
    if args.output.exists(): parser.error('output already exists')
    report = inspect_bag(args.bag,args.lidar_topic,args.imu_topic,args.expected_sha256)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('x',encoding='utf-8') as target:
        json.dump(report,target,ensure_ascii=False,indent=2,allow_nan=False)
    print(json.dumps({'structural_precheck_passed':report['structural_precheck_passed'],'errors':report['errors']}))
    return 0 if report['structural_precheck_passed'] else 2


if __name__=='__main__':
    raise SystemExit(main())
