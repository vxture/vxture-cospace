"""Local-only one-shot synthetic checks. No algorithm or publication commands."""
import argparse
import json
import os
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from packages.data.imports import ImportManager, ImportError
from packages.infrastructure.files import LocalFiles
from packages.infrastructure.imports import ImportStore
from packages.infrastructure.jobs import JobStore, JobError
from packages.infrastructure.runner import LocalRunner
from packages.construction.jobs import JobManager


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True)
    commands = parser.add_subparsers(dest='command', required=True)
    submit = commands.add_parser('submit')
    submit.add_argument('--dataset', required=True)
    submit.add_argument('--actor', required=True)
    submit.add_argument('--timeout', type=int, default=120)
    submit.add_argument('--log-limit', type=int, default=8388608)
    for name in ('run', 'cancel', 'status', 'report'):
        item = commands.add_parser(name)
        item.add_argument('job')
        if name in ('run', 'cancel'):
            item.add_argument('--revision', type=int, required=True)
    args = parser.parse_args()
    engine = None
    try:
        url = os.environ.get('COSPACE_DATABASE_URL')
        if not url:
            raise JobError('configuration_missing', 'COSPACE_DATABASE_URL required')
        engine = create_engine(url)
        if engine.dialect.name != 'postgresql':
            raise JobError('unsupported_database', 'CLI requires PostgreSQL')
        files = LocalFiles(args.root)
        store = JobStore(engine)
        manager = JobManager(store, ImportManager(ImportStore(engine), files), LocalRunner(files))
        if args.command == 'submit':
            result = manager.submit(args.dataset, args.actor, args.timeout, args.log_limit)
        elif args.command == 'run':
            result = manager.run(args.job, args.revision)
        elif args.command == 'cancel':
            result = store.cancel(args.job, args.revision)
        elif args.command == 'report':
            result = manager.report(args.job)
        else:
            result = store.get(args.job)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 2 if result.get('state') == 'failed' else 0
    except SQLAlchemyError:
        failure = {'code': 'storage_error', 'message': 'database failure; inspect job before retry'}
    except (OSError, ValueError) as error:
        failure = {'code': getattr(error, 'code', 'invalid_input'),
                   'message': str(error) if isinstance(error, (JobError, ImportError)) else 'input or storage invalid'}
    finally:
        if engine is not None:
            engine.dispose()
    print(json.dumps({'error': failure}, ensure_ascii=False))
    return 2


if __name__ == '__main__':
    raise SystemExit(main())
