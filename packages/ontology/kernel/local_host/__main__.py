"""Start the standalone reference host or snapshot its local database."""
import argparse
from pathlib import Path
import sqlite3
import sys

from .http import server
from .identity import TokenIdentity
from .storage import initialize, snapshot


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_subparsers(dest='command', required=True)
    start = modes.add_parser('serve', help='Start the authenticated IPv4 loopback API')
    start.add_argument('--data-dir', type=Path, required=True)
    start.add_argument('--identity-config', type=Path, required=True)
    start.add_argument('--port', type=int, default=8791)
    backup = modes.add_parser('backup', help='Copy a consistent snapshot to a new directory')
    backup.add_argument('--data-dir', type=Path, required=True)
    backup.add_argument('--output-dir', type=Path, required=True)
    restore = modes.add_parser('restore', help='Restore a trusted snapshot to a new directory')
    restore.add_argument('--backup-dir', type=Path, required=True)
    restore.add_argument('--data-dir', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == 'serve':
            if not 0 <= args.port <= 65535:
                parser.error('--port must be between 0 and 65535')
            root, config = args.data_dir.resolve(), args.identity_config.resolve()
            if config.is_relative_to(root):
                parser.error('--identity-config must be outside --data-dir')
            authenticate = TokenIdentity.load(config)
            initialize(root)
            with server(root, args.port, authenticate) as service:
                print(f'Listening at http://127.0.0.1:{service.server_port}', flush=True)
                service.serve_forever()
        elif args.command == 'backup':
            snapshot(args.data_dir, args.output_dir)
        else:
            snapshot(args.backup_dir, args.data_dir)
    except KeyboardInterrupt:
        return 130
    except (OSError, sqlite3.Error, ValueError):
        print(f'Ontology host {args.command} failed. Check configuration, database format and path permissions; '
              'snapshot destinations must not exist.', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
