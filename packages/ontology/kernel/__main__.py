"""Portable definition export and consumer-owned instance validation CLI."""
import argparse
import json
from pathlib import Path
import sys
from .catalog import Catalog, CatalogError, MAX_BYTES, builtin_catalog
from .instances import MAX_INSTANCE_BYTES, validate_instances


def main():
    parser = argparse.ArgumentParser(description='Export portable definitions or validate consumer-owned instances.')
    parser.add_argument('--library', type=Path, help='Validate a library JSON file instead of built-in drafts')
    parser.add_argument('--module', help='Export this module and its exact dependency closure')
    parser.add_argument('--instances', type=Path, help='Validate a consumer-owned instance JSON package')
    parser.add_argument('--rules', choices=['park-baseline'], help='Explicit candidate domain rules for instance validation')
    args = parser.parse_args()
    if args.instances and args.module or args.rules and not args.instances:
        parser.error('--instances cannot combine with --module; --rules requires --instances')
    try:
        if args.library:
            with args.library.open('rb') as stream:
                catalog = Catalog.from_bytes(stream.read(MAX_BYTES + 1))
        else:
            catalog = builtin_catalog()
        if args.instances:
            with args.instances.open('rb') as stream:
                report = validate_instances(stream.read(MAX_INSTANCE_BYTES + 1), catalog, rule_set=args.rules)
            print(json.dumps(report, ensure_ascii=True, indent=2))
            return 0 if report['valid'] else 1
        print(json.dumps(catalog.export(args.module), ensure_ascii=True, indent=2))
    except (CatalogError, OSError) as exc:
        print(json.dumps({'error': getattr(exc, 'code', 'library_unavailable'),
                          'path': getattr(exc, 'path', '/')}), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
