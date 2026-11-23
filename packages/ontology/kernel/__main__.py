"""Portable definition export and consumer-owned instance validation CLI."""
import argparse
import json
from pathlib import Path
import sys
from .catalog import Catalog, CatalogError, MAX_BYTES, builtin_catalog, canonical_bytes
from .exchange import MAX_EXCHANGE_BYTES, catalog_from_exchanges, export_closure, parse_closure, project_owl_classes
from .instances import MAX_INSTANCE_BYTES, validate_instances


def read_limited(path, limit):
    with path.open('rb') as stream:
        return stream.read(limit + 1)


def main():
    parser = argparse.ArgumentParser(description='Export portable definitions or validate consumer-owned instances.')
    sources = parser.add_mutually_exclusive_group()
    sources.add_argument('--library', type=Path, help='Validate a library JSON file instead of built-in drafts')
    sources.add_argument('--exchange', type=Path, action='append',
                         help='Verify a native exchange closure; repeat for multi-root instances')
    parser.add_argument('--module', help='Export this module and its exact dependency closure')
    parser.add_argument('--pack-closure', action='store_true', help='With --module, emit the digested native exchange package')
    parser.add_argument('--owl-classes', action='store_true', help='Project an --exchange package to OWL classes with a loss report')
    parser.add_argument('--instances', type=Path, help='Validate a consumer-owned instance JSON package')
    parser.add_argument('--rules', choices=['park-baseline'], help='Explicit candidate domain rules for instance validation')
    args = parser.parse_args()
    if args.instances and args.module or args.rules and not args.instances:
        parser.error('--instances cannot combine with --module; --rules requires --instances')
    if args.pack_closure and not args.module or args.exchange and args.module:
        parser.error('--pack-closure requires --module; --exchange cannot combine with --module')
    if args.owl_classes and (not args.exchange or args.instances):
        parser.error('--owl-classes requires --exchange and cannot combine with --instances')
    if args.exchange and len(args.exchange) > 1 and not args.instances:
        parser.error('multiple --exchange inputs require --instances')
    try:
        if args.exchange:
            packages = (read_limited(path, MAX_EXCHANGE_BYTES) for path in args.exchange)
            if not args.instances:
                raw = next(packages)
                if args.owl_classes:
                    print(json.dumps(project_owl_classes(raw), ensure_ascii=True, indent=2))
                else:
                    sys.stdout.buffer.write(canonical_bytes(parse_closure(raw)) + b'\n')
                return 0
            catalog = catalog_from_exchanges(packages)
        elif args.library:
            catalog = Catalog.from_bytes(read_limited(args.library, MAX_BYTES))
        else:
            catalog = builtin_catalog()
        if args.instances:
            report = validate_instances(read_limited(args.instances, MAX_INSTANCE_BYTES), catalog, rule_set=args.rules)
            print(json.dumps(report, ensure_ascii=True, indent=2))
            return 0 if report['valid'] else 1
        bundle = catalog.export(args.module)
        if args.pack_closure:
            reference = next(entry['reference'] for entry in catalog.describe()['modules']
                             if entry['reference']['module_id'] == args.module)
            sys.stdout.buffer.write(canonical_bytes(export_closure(bundle, reference)) + b'\n')
        else:
            print(json.dumps(bundle, ensure_ascii=True, indent=2))
    except (CatalogError, OSError) as exc:
        print(json.dumps({'error': getattr(exc, 'code', 'library_unavailable'),
                          'path': getattr(exc, 'path', '/')}), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
