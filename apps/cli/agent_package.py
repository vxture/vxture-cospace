"""R0 synthetic runtime package export/check; source bundle required."""
import argparse
import json
from packages.views.agent.runtime import build, verify, PackageError


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('build', 'check'))
    parser.add_argument('directory')
    parser.add_argument('--source', required=True)
    args = parser.parse_args()
    try:
        report = build(args.source, args.directory) if args.operation == 'build' else verify(args.directory, args.source)
    except (ValueError, OSError, KeyError, TypeError) as error:
        report = {'passed': False, 'robot_ready': False, 'real_release_ready': False,
                  'error': {'code': error.code if isinstance(error, PackageError) else 'validation_error', 'message': str(error)}}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report['passed'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
