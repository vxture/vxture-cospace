"""Local-only synthetic dataset import. Never activates a service release."""
import argparse
import json
import os
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from packages.data.imports import ImportManager, ImportError
from packages.service.sample import read_json
from packages.infrastructure.imports import ImportStore
from packages.infrastructure.files import LocalFiles, bounded_read


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True, help='Dedicated local runtime storage')
    commands = parser.add_subparsers(dest='command', required=True)
    ingest = commands.add_parser('ingest')
    ingest.add_argument('source')
    ingest.add_argument('--request', required=True, help='Fixed JSON request file')
    ingest.add_argument('--actor', required=True)
    for kind in ('status', 'dataset'):
        commands.add_parser(kind).add_argument('identity')
    args = parser.parse_args()
    engine = None
    try:
        url = os.environ.get('COSPACE_DATABASE_URL')
        if not url:
            raise ImportError('configuration_missing', 'COSPACE_DATABASE_URL required')
        engine = create_engine(url)
        if engine.dialect.name != 'postgresql':
            raise ImportError('unsupported_database', 'CLI requires PostgreSQL')
        store = ImportStore(engine)
        manager = ImportManager(store, LocalFiles(args.root))
        if args.command == 'ingest':
            request = read_json(bounded_read(args.request))
            result = manager.ingest(args.source, request, args.actor)
        elif args.command == 'status':
            result = store.get_import(args.identity)
        else:
            result = manager.dataset(args.identity)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except SQLAlchemyError:
        failure = {'code': 'storage_error', 'message': 'database failure; inspect import before retry'}
    except (OSError, ValueError) as error:
        failure = {'code': error.code if isinstance(error, ImportError) else 'invalid_input',
                   'message': str(error) if isinstance(error, ImportError) else 'input or storage invalid'}
    finally:
        if engine is not None:
            engine.dispose()
    print(json.dumps({'error': failure}, ensure_ascii=False))
    return 2


if __name__ == '__main__':
    raise SystemExit(main())
