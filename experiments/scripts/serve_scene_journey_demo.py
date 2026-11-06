"""Scene journey acceptance with local mock accounts and saved artifacts.

Does not run builds, select candidates or publish during setup. By default copies
the source runtime. --existing-runtime explicitly continues an isolated runtime.
"""
import argparse
import json
import shutil
from pathlib import Path
from cryptography.fernet import Fernet
from pydantic import SecretStr
import uvicorn
from experiments.scripts.platform_auth_fixture import MockAccounts
from experiments.scripts.serve_platform_workbench import assemble
from experiments.scripts.verify_preview_workflow import inventory
from packages.infrastructure.platform_rp import RpConfig
from packages.infrastructure.platform_session_store import LocalRpStore
from packages.infrastructure.space_policy_store import SpacePolicyStore
from packages.lifecycle.preview_spaces import PreviewSpaces
from packages.service.space_access import SpaceAccessPolicy
from packages.service.platform_login import PlatformLogin


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--candidate',required=True)
    parser.add_argument('--port',type=int,default=8772)
    parser.add_argument('--existing-runtime',action='store_true',help='Continue the named isolated source runtime without copying it')
    parser.add_argument('--with-workspace-owner',action='store_true',help='Add an explicit local mock workspace owner for rule-authoring acceptance')
    parser.add_argument('--accounts-port',type=int,default=0,help='Stable local mock issuer port for restart acceptance; zero allocates a temporary port')
    args=parser.parse_args();source=args.source.resolve();output=args.output.resolve()
    initial=source/'preview-builds'/args.candidate/'output'
    if (not initial.is_dir() or not initial.resolve().is_relative_to(source) or output.exists()
            or output.is_relative_to(source) or source.is_relative_to(output)):
        parser.error('exclusive_output_and_existing_source_candidate_required')
    original=Path('var/nyu').resolve()
    if args.existing_runtime and (source.is_relative_to(original) or original.is_relative_to(source)):
        parser.error('existing_runtime_must_be_isolated_from_original')
    output.mkdir(parents=True);sample=source if args.existing_runtime else output/'runtime'
    if not args.existing_runtime:sample.mkdir()
    baseline=inventory(args.source)
    if not args.existing_runtime:
        for folder in source.glob('preview-*'):
            if folder.is_dir():shutil.copytree(folder,sample/folder.name)
    (output/'source-before.json').write_text(json.dumps(baseline,indent=2)+'\n',encoding='utf-8')
    accounts=MockAccounts(port=args.accounts_port).start()
    try:
        accounts.roles=['workspace:member'];accounts.access_seconds=3600
        accounts.identity_options={'usr_manager':'模拟场景管理员','usr_local_test':'模拟查看者'}
        if args.with_workspace_owner:
            accounts.identity_options['usr_owner']='模拟工作区所有者'
            accounts.identity_roles['usr_owner']=['workspace:owner']
        accounts.rp_origin=f'http://127.0.0.1:{args.port}'
        cfg=RpConfig(issuer=accounts.issuer,backchannel=accounts.issuer,client_id=accounts.client_id,
            client_secret=SecretStr(accounts.secret),origin=accounts.rp_origin,allow_loopback_http=True,
            encryption_key=SecretStr(Fernet.generate_key().decode()))
        directory=PreviewSpaces(sample/'preview-directory');scenes=directory.list('space')
        viewer_space=json.loads((initial/'model.json').read_bytes()).get('space_id') if args.existing_runtime else scenes[0]['id']
        if viewer_space not in {s['id'] for s in scenes}:raise ValueError('initial_candidate_scene_required')
        policy=SpaceAccessPolicy.model_validate({
            'bindings':[{'issuer':cfg.issuer,'space_id':s['id'],'org_id':'org_mock','workspace_id':'ws_mock'} for s in scenes],
            'grants':[{'issuer':cfg.issuer,'subject':'usr_manager','space_id':s['id'],'role':'manager'} for s in scenes]
                +[{'issuer':cfg.issuer,'subject':'usr_local_test','space_id':viewer_space,'role':'viewer'}]})
        policies=SpacePolicyStore(output/'auth/policies')
        policies.replace(policy,expected_revision=0,actor='local_mock_journey_setup',reason='isolated copied scene acceptance')
        rp=PlatformLogin(cfg,LocalRpStore(output/'auth/sessions',cfg.encryption_key.get_secret_value()))
        print('LOCAL MOCK journey acceptance: '+cfg.origin+'/workbench/layout.html',flush=True)
        uvicorn.run(assemble(rp,policies,sample,sample/'preview-builds'/args.candidate/'output'),
                    host='127.0.0.1',port=args.port,access_log=False)
    finally:accounts.stop()


if __name__=='__main__':main()
