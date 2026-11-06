"""LOCAL MOCK ONLY: empty scene journey, no copied inputs, models or publications.

Keeps policies/configuration across restarts; the auth session is deliberately new.
Optional one-shot worker failure is exclusive acceptance setup, never a UI feature.
"""
import argparse
import json
from pathlib import Path
import subprocess
from cryptography.fernet import Fernet
from pydantic import SecretStr
import uvicorn
from experiments.scripts.platform_auth_fixture import MockAccounts
from experiments.scripts.serve_platform_workbench import assemble
from packages.infrastructure.platform_rp import RpConfig
from packages.infrastructure.platform_session_store import LocalRpStore
from packages.infrastructure.space_policy_store import SpacePolicyStore
from packages.service.platform_login import PlatformLogin
from packages.service.space_access import SpaceAccessPolicy
from packages.infrastructure.preview_service_lock import service_guard


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,required=True)
    p.add_argument('--auth-output',type=Path,required=True)
    p.add_argument('--port',type=int,default=8786)
    p.add_argument('--accounts-port',type=int,default=19122)
    p.add_argument('--resume',action='store_true')
    a=p.parse_args();root=a.root.resolve();auth=a.auth_output.resolve()
    original=Path('var/nyu').resolve()
    if (auth.exists() or auth.is_relative_to(root) or root.is_relative_to(auth)
            or root.is_relative_to(original) or original.is_relative_to(root)):
        p.error('exclusive_auth_and_isolated_business_runtime_required')
    if a.resume:
        if not (root/'setup/workspace-scenes.json').is_file():p.error('existing_empty_journey_setup_required')
    else:root.mkdir(parents=True,exist_ok=False)
    auth.mkdir(parents=True)
    accounts=MockAccounts(port=a.accounts_port).start()
    try:
        accounts.roles=['workspace:member'];accounts.access_seconds=3600
        accounts.identity_options={'usr_owner':'模拟工作区所有者','usr_manager':'模拟场景管理员',
                                  'usr_local_test':'模拟查看者','usr_unassigned':'模拟未授权成员'}
        accounts.identity_roles={'usr_owner':['workspace:owner']}
        accounts.rp_origin=f'http://127.0.0.1:{a.port}'
        cfg=RpConfig(issuer=accounts.issuer,backchannel=accounts.issuer,client_id=accounts.client_id,
            client_secret=SecretStr(accounts.secret),origin=accounts.rp_origin,allow_loopback_http=True,
            encryption_key=SecretStr(Fernet.generate_key().decode()))
        setup=root/'setup';policies=SpacePolicyStore(root/'policy')
        if not a.resume:
            setup.mkdir()
            (setup/'sources.json').write_text(json.dumps({'profile':'cospace.preview-sources/0.1','sources':[]}),encoding='utf-8')
            (setup/'workspace-scenes.json').write_text(json.dumps({'profile':'cospace.workspace-scenes/0.1','revision':1,
                'workspaces':[{'issuer':accounts.issuer,'org_id':'org_mock','workspace_id':'ws_mock','allow_create':True,
                               'creator_subjects':[],'source_bindings':{}}]}),encoding='utf-8')
            policies.replace(SpaceAccessPolicy(bindings=[],grants=[]),expected_revision=0,
                             actor='local_mock_empty_journey_setup',reason='P22 starts with zero scenes and zero business artifacts')
        else:
            config=json.loads((setup/'workspace-scenes.json').read_bytes())
            if any(w['issuer']!=accounts.issuer for w in config['workspaces']):raise ValueError('original_mock_issuer_required')
            policies.load()
        rp=PlatformLogin(cfg,LocalRpStore(auth/'sessions',cfg.encryption_key.get_secret_value()))
        with service_guard(root/'runtime'):
            app=assemble(rp,policies,root/'runtime',None,setup/'sources.json',setup/'workspace-scenes.json')
            real_popen=subprocess.Popen
            def launch(command,*args,**kwargs):
                # Explicitly created local marker, consumed only for the next actual model worker.
                marker=setup/'fail-next-model'
                if isinstance(command,list) and len(command)>2 and command[2]=='experiments.scripts.build_pointcloud_flow_preview' and marker.is_file():
                    marker.unlink();command=[command[0],'-c','raise SystemExit(23)']
                return real_popen(command,*args,**kwargs)
            subprocess.Popen=launch
            print('LOCAL MOCK empty journey: '+cfg.origin+'/workbench/layout.html',flush=True)
            uvicorn.run(app,host='127.0.0.1',port=a.port,access_log=False)
    finally:accounts.stop()


if __name__=='__main__':main()
