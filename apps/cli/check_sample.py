"""Run from the repository root: python -m apps.cli.check_sample PACKAGE."""
import argparse
import json

from packages.service.sample import validate_package
from packages.data.structure import StructureError


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('package')
    parser.add_argument('--channel', choices=['sample', 'real'], default='sample')
    args = parser.parse_args()
    try:
        report = validate_package(args.package, args.channel)
    except StructureError as error:
        report = {'passed': False, 'real_release_ready': False,
                  'error': {'code': 'structure_error', 'file': error.file,
                            'path': error.path, 'message': error.message}}
    except (OSError, ValueError, KeyError, TypeError, IndexError) as error:
        report = {'passed': False, 'real_release_ready': False,
                  'error': {'code': 'validation_error', 'message': str(error)}}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report['passed'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
