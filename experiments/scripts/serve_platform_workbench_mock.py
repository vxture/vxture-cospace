"""Explicit LOCAL MOCK authorized workbench using a new managed sample copy."""
import argparse
import json
from pathlib import Path
import shutil
from cryptography.fernet import Fernet
from pydantic import SecretStr
import uvicorn
from experiments.scripts.platform_auth_fixture import MockAccounts
from experiments.scripts.serve_platform_workbench import assemble
from packages.infrastructure.platform_rp import RpConfig
from packages.infrastructure.platform_session_store import LocalRpStore
from packages.infrastructure.space_policy_store import SpacePolicyStore
from packages.service.space_access import SpaceAccessPolicy
from packages.service.platform_login import PlatformLogin


def setup(root,port):
    root=Path(root).resolve();source=Path('var/nyu').resolve()
    if root.exists() or root.is_relative_to(source) or source.is_relative_to(root):raise ValueError('new_separate_mock_runtime_required')
    root.mkdir(parents=True);sample=root/'sample';sample.mkdir()
    for name in ('preview-directory','preview-builds','preview-inputs','preview-ontologies'):
        shutil.copytree(source/name,sample/name)
    accounts=MockAccounts().start();accounts.roles=['workspace:member'];accounts.access_seconds=600
    accounts.identity_options={'usr_local_test':'模拟查看者 A','usr_other':'模拟工程师 B','usr_manager':'模拟管理员'}
    accounts.rp_origin='http://127.0.0.1:'+str(port)
    cfg=RpConfig(issuer=accounts.issuer,backchannel=accounts.issuer,client_id=accounts.client_id,
        client_secret=SecretStr(accounts.secret),origin=accounts.rp_origin,allow_loopback_http=True,
        encryption_key=SecretStr(Fernet.generate_key().decode()))
    pubs=[json.loads(p.read_bytes()) for p in (sample/'preview-builds/publications').glob('*/publication.json')]
    spaces=sorted({p['space_id'] for p in pubs if p.get('space_id')})
    if len(spaces)<2:accounts.stop();raise ValueError('two_saved_spaces_required')
    policy=SpaceAccessPolicy.model_validate({'bindings':[{'issuer':cfg.issuer,'space_id':s,'org_id':'org_mock','workspace_id':'ws_mock'} for s in spaces],
        'grants':[{'issuer':cfg.issuer,'subject':'usr_local_test','space_id':spaces[0],'role':'viewer'},
                  {'issuer':cfg.issuer,'subject':'usr_other','space_id':spaces[1],'role':'engineer'}]
            +[{'issuer':cfg.issuer,'subject':'usr_manager','space_id':s,'role':'manager'} for s in spaces]})
    policies=SpacePolicyStore(root/'auth');policies.replace(policy,expected_revision=0,actor='local_mock_setup',reason='isolated process verification')
    rp=PlatformLogin(cfg,LocalRpStore(root/'auth/sessions',cfg.encryption_key.get_secret_value()))
    initial=next(p.parent/'output' for p in (sample/'preview-builds').glob('*/job.json')
        if json.loads(p.read_bytes()).get('state')=='succeeded' and (p.parent/'output/model.json').is_file())
    # Public identifiers only; no client secret, session key, cookies or tokens.
    (root/'demo.json').write_text(json.dumps({'origin':cfg.origin,'spaces':spaces,'grants':policy.model_dump()['grants'],
        'initial':str(initial),'identity_provider':'local_mock_only'},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return accounts,rp,policies,sample,initial


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--runtime',type=Path,required=True)
    p.add_argument('--port',type=int,default=8769);a=p.parse_args()
    accounts,rp,policies,sample,initial=setup(a.runtime,a.port)
    print('LOCAL MOCK ONLY; copied sample; '+rp.config.origin+'/workbench/layout.html',flush=True)
    try:uvicorn.run(assemble(rp,policies,sample,initial),host='127.0.0.1',port=a.port,access_log=False)
    finally:accounts.stop()


if __name__=='__main__':main()
