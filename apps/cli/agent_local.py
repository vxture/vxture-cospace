"""R1a synthetic local install/activate/query; no validity authorization."""
import argparse
import json
import sqlite3
from packages.views.agent.local import LocalPackages
from packages.views.agent.runtime import PackageError


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True)
    parser.add_argument('--backend', choices=('blob', 'files'), default='blob')
    actions = parser.add_subparsers(dest='action', required=True)
    install = actions.add_parser('install')
    install.add_argument('package')
    install.add_argument('--source', required=True)
    activate = actions.add_parser('activate')
    activate.add_argument('scene')
    activate.add_argument('--digest', required=True)
    activate.add_argument('--revision', type=int, required=True)
    status = actions.add_parser('status')
    status.add_argument('scene')
    query = actions.add_parser('query')
    query.add_argument('scene')
    query.add_argument('--point', nargs=3, type=float, required=True)
    installation = actions.add_parser('installation')
    installation.add_argument('identity')
    installations = actions.add_parser('installations')
    installations.add_argument('--limit', type=int, default=20)
    recovery = actions.add_parser('recover-install')
    recovery.add_argument('identity')
    recovery.add_argument('--revision', type=int, required=True)
    audit = actions.add_parser('audit')
    audit.add_argument('--limit', type=int, default=200)
    args = parser.parse_args()
    try:
        if args.action == 'audit':
            if args.backend != 'files':
                raise PackageError('unsupported_operation', 'audit requires files backend')
            from packages.infrastructure.agent_audit import PackageAudit
            report = PackageAudit(args.root).scan(args.limit)
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return 0 if report['passed'] else 2
        if args.backend == 'files':
            from packages.infrastructure.agent_files import FilePackages
            store = FilePackages(args.root)
        else:
            store = LocalPackages(args.root)
        if args.action in ('installation', 'installations', 'recover-install') and args.backend != 'files':
            raise PackageError('unsupported_operation', 'installation recovery requires files backend')
        if args.action == 'install':
            report = store.install(args.package, args.source)
        elif args.action == 'activate':
            report = store.activate(args.scene, args.digest, args.revision)
        elif args.action == 'status':
            report = store.status(args.scene)
        elif args.action == 'installation':
            report = store.installation(args.identity)
        elif args.action == 'installations':
            report = store.installations(args.limit)
        elif args.action == 'recover-install':
            report = store.recover_installation(args.identity, args.revision)
        else:
            session = store.open_session(args.scene)
            try:
                report = session.query(args.point)
            finally:
                session.close()
        report = {'passed': True, **report}
    except (ValueError, OSError, KeyError, TypeError, sqlite3.Error) as error:
        report = {'passed': False, 'robot_ready': False,
                  'error': {'code': error.code if isinstance(error, PackageError) else 'local_error', 'message': str(error)}}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report['passed'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
