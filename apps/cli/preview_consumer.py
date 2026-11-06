"""Offline preview consumption: install, explicitly activate, and restore a saved version."""
import argparse
import json
from pathlib import Path
import sqlite3
import zipfile

from packages.views.agent.preview_consumer_store import PersistentPreviewConsumer
from packages.spatial.preview_range import DEFAULT_RANGE_CELLS


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True, help='Dedicated local consumer store, not the server model directory')
    commands = parser.add_subparsers(dest='command', required=True)
    init = commands.add_parser('init', help='Create a new empty store for one explicit space')
    scope = init.add_mutually_exclusive_group(required=True)
    scope.add_argument('--space-id')
    scope.add_argument('--legacy', action='store_true', help='Explicitly bind to unassigned historical packages')
    commands.add_parser('status', help='Read saved metadata; does not restore or verify package bytes')
    commands.add_parser('list', help='List installed package references')
    install = commands.add_parser('install', help='Validate and save a ZIP; does not activate')
    install.add_argument('bundle', type=Path)
    for name, command in [('install', install), ('activate', commands.add_parser('activate')), ('restore', commands.add_parser('restore'))]:
        command.add_argument('--publication', required=True)
        command.add_argument('--sha256', required=True)
        if name != 'install':
            command.add_argument('--expected-revision', type=int, required=True)
        if name == 'restore':
            query = command.add_mutually_exclusive_group()
            query.add_argument('--point', nargs=3, type=float)
            query.add_argument('--objects', action='store_true')
            query.add_argument('--object-id')
            query.add_argument('--bounds', nargs=6, type=float)
            command.add_argument('--frame-id')
            command.add_argument('--limit', type=int)
    args = parser.parse_args()
    if args.command == 'restore':
        if args.bounds is not None and not args.frame_id:
            parser.error('--bounds requires --frame-id')
        if args.bounds is None and (args.frame_id is not None or args.limit is not None):
            parser.error('--frame-id and --limit require --bounds')
    try:
        if args.command == 'init':
            store = PersistentPreviewConsumer.initialize(args.root, args.space_id)
            result = store.status()
        else:
            store = PersistentPreviewConsumer(args.root)
            if args.command == 'status':
                result = store.status()
            elif args.command == 'list':
                result = {'packages': store.packages(), 'quality': 'unverified', 'robot_ready': False}
            elif args.command == 'install':
                result = store.install(args.bundle, args.publication, args.sha256)
            elif args.command == 'activate':
                store.activate(args.publication, args.sha256, args.expected_revision)
                result = store.status()
            else:
                session = store.restore(args.publication, args.sha256, args.expected_revision)
                if args.point is not None:
                    result = session.query(args.point)
                elif args.objects or args.object_id is not None:
                    result = session.objects(args.object_id)
                elif args.bounds is not None:
                    result = session.query_range([args.bounds[:3], args.bounds[3:]], args.frame_id,
                                                 args.limit if args.limit is not None else DEFAULT_RANGE_CELLS)
                else:
                    result = store.status()
        print(json.dumps(result, ensure_ascii=False, allow_nan=False))
        if result.get('status') == 'limit_exceeded':
            parser.exit(3)
    except (ValueError, OSError, KeyError, TypeError, sqlite3.Error, zipfile.BadZipFile, EOFError) as exc:
        parser.exit(2, f'preview_consumer_refused: {exc}\n')


if __name__ == '__main__':
    main()
