"""LOCAL ACCEPTANCE ONLY: synthetic records and a loopback mock identity provider.

Run after building the workbench. All runtime, keys and receipts must be outside
this repository. This is not a deployment or a production authentication mode.
"""
import argparse
import json
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO), str(Path(__file__).resolve().parent)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True, help='New directory outside the repository')
    parser.add_argument('--port', type=int, default=18876)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.is_relative_to(REPO) or not 1024 <= args.port <= 65535:
        parser.error('new_external_runtime_and_loopback_port_required')
    if not (REPO/'apps/workbench/dist/index.html').is_file():
        parser.error('build_workbench_first')
    output.mkdir(parents=True, exist_ok=False)

    from cryptography.fernet import Fernet
    from pydantic import SecretStr
    import uvicorn
    from test_preview_workflow import prepared
    from test_preview_pointcloud import specimen
    from test_pointcloud_preparation import declared
    from experiments.scripts.pack_input_upload import pack
    from experiments.scripts.platform_auth_fixture import MockAccounts
    from experiments.scripts.serve_nyu_flow_preview import create_app
    from packages.infrastructure.platform_rp import RpConfig
    from packages.infrastructure.platform_session_store import LocalRpStore
    from packages.infrastructure.space_policy_store import SpacePolicyStore
    from packages.service.platform_login import PlatformLogin
    from packages.service.platform_auth_http import create_auth_app
    from packages.service.platform_business_http import BusinessAccess
    from packages.service.space_access import SpaceAccessPolicy

    business_root = output/'business'
    business_root.mkdir()
    initial, jobs, directory, spaces, ontologies, _, old, current = prepared(business_root)
    upload = output/'upload'
    upload.mkdir()
    cloud = specimen(upload)
    declared(cloud)
    pack(cloud, None, upload/'sample.zip', 'ply_pointcloud')

    accounts = MockAccounts().start()
    try:
        accounts.rp_origin = f'http://127.0.0.1:{args.port}'
        accounts.roles = ['workspace:member']
        accounts.profile_claims = {'email':'engineer@example.test','phone':'+8613800000000',
            'phone_verified':True,'active_org_name':'示例组织','active_workspace_name':'验收工作区'}
        accounts.identity_options = {'usr_viewer':'N6 查看者', 'usr_engineer':'N6 工程师',
                                     'usr_manager':'N6 管理者', 'usr_owner':'N6 规则维护者'}
        accounts.identity_roles = {'usr_owner':['workspace:owner']}
        config = RpConfig(issuer=accounts.issuer, backchannel=accounts.issuer,
            client_id=accounts.client_id, client_secret=SecretStr(accounts.secret),
            origin=accounts.rp_origin, allow_loopback_http=True,
            encryption_key=SecretStr(Fernet.generate_key().decode()))
        rp = PlatformLogin(config, LocalRpStore(output/'sessions', config.encryption_key.get_secret_value()))
        policies = SpacePolicyStore(output/'auth')
        policies.replace(SpaceAccessPolicy.model_validate({
            'bindings':[{'issuer':config.issuer, 'space_id':space['id'], 'org_id':'org_mock',
                         'workspace_id':'ws_mock'} for space in spaces],
            'grants':[{'issuer':config.issuer, 'subject':'usr_'+role, 'space_id':spaces[0]['id'],
                       'role':role} for role in ('viewer','engineer','manager')]}),
            expected_revision=0, actor='n6-local', reason='isolated acceptance')
        workspace_config = output/'auth/workspace-scenes.json'
        workspace_config.write_text(json.dumps({'profile':'cospace.workspace-scenes/0.1', 'revision':1,
            'workspaces':[{'issuer':config.issuer, 'org_id':'org_mock', 'workspace_id':'ws_mock',
                          'allow_create':True, 'creator_subjects':[], 'source_bindings':{}}]}), encoding='utf-8')
        business = create_app(initial, jobs, space_directory=directory, ontologies=ontologies,
                              platform_origin=config.origin)
        app = create_auth_app(rp, workbench=REPO/'apps/workbench/dist', business=business,
            access=BusinessAccess(rp, policies, directory, jobs, workspace_config=workspace_config))
        (output/'context.json').write_text(json.dumps({'origin':config.origin, 'space':spaces[0]['id'],
            'foreign':spaces[1]['id'], 'old':old['id'], 'current':current['id'],
            'candidate':current['candidate_id'], 'upload':str(upload/'sample.zip')}), encoding='utf-8')
        print(f'Local synthetic acceptance: {config.origin}/', flush=True)
        uvicorn.run(app, host='127.0.0.1', port=args.port, access_log=False)
    finally:
        accounts.stop()


if __name__ == '__main__':
    main()
