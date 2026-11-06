"""Local sample lifecycle CLI. Uses COSPACE_DATABASE_URL; never a production publisher."""
import argparse
import json
import os

from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError

from packages.infrastructure.releases import ReleaseStore
from packages.lifecycle.releases import ReleaseError, ReleaseManager
from packages.service.query import QueryError


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('init-demo', help='Apply versioned migrations to a dedicated sample database')
    register = sub.add_parser('register')
    register.add_argument('package')
    for command in ('current', 'trace', 'activate', 'revoke', 'query'):
        item = sub.add_parser(command)
        item.add_argument('--scene', required=True)
        if command != 'current':
            item.add_argument('--release', required=True)
        if command in ('activate', 'revoke'):
            item.add_argument('--actor', required=True)
        if command == 'activate':
            item.add_argument('--expected-revision', type=int, required=True)
        if command == 'revoke':
            item.add_argument('--reason', required=True)
        if command == 'query':
            item.add_argument('--frame', required=True)
            item.add_argument('--point', type=float, nargs=3, required=True)
    args = parser.parse_args()
    engine = None
    try:
        url = os.environ.get('COSPACE_DATABASE_URL')
        if not url:
            raise ReleaseError('configuration_missing', 'COSPACE_DATABASE_URL is required')
        engine = create_engine(url)
        if engine.dialect.name != 'postgresql':
            raise ReleaseError('unsupported_database', 'lifecycle CLI requires PostgreSQL')
        store = ReleaseStore(engine)
        manager = ReleaseManager(store)
        if args.command == 'init-demo':
            store.initialize_demo()
            result = {'initialized': True, 'sample_only': True}
        elif args.command == 'register':
            result = manager.register(args.package)
        elif args.command == 'current':
            result = manager.current(args.scene)
        elif args.command == 'trace':
            result = manager.trace(args.scene, args.release)
        elif args.command == 'activate':
            result = manager.activate(args.scene, args.release, args.expected_revision, args.actor)
        elif args.command == 'revoke':
            result = manager.revoke(args.scene, args.release, args.actor, args.reason)
        else:
            result = manager.query(args.scene, args.release, args.frame, args.point)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except SQLAlchemyError:
        # Never echo a database URL, SQL parameters or driver exception with secrets.
        error = {'code': 'storage_error', 'message': 'database operation failed; no spatial result returned'}
    except (OSError, ValueError) as failure:
        error = {'code': failure.code if isinstance(failure, (ReleaseError, QueryError)) else 'validation_error',
                 'message': str(failure)}
    finally:
        if engine is not None:
            engine.dispose()
    print(json.dumps({'error': error}, ensure_ascii=False))
    return 2


if __name__ == '__main__':
    raise SystemExit(main())
