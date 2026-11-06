"""python -m apps.cli.query_sample PACKAGE --scene ID --release ID --frame ID --point X Y Z"""
import argparse
import json

from packages.service.query import QueryError, SampleService


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('package')
    for name in ('scene', 'release', 'frame'):
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--point', nargs=3, type=float, required=True)
    args = parser.parse_args()
    try:
        result = SampleService(args.package).query(args.scene, args.release, args.frame, args.point)
    except (OSError, ValueError) as error:
        print(json.dumps({'error': {'code': error.code if isinstance(error, QueryError) else 'invalid_package_or_point',
                                   'message': str(error)}}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
