"""Serve a verified, isolated scene with LOCAL MOCK platform login on loopback.

Uses the verification's runtime, never copies or changes the existing 8769 workbench.
The new auth runtime is exclusive; credentials are generated in memory, never printed.
"""
import argparse
import json
from pathlib import Path
from cryptography.fernet import Fernet
from pydantic import SecretStr
import uvicorn
from experiments.scripts.platform_auth_fixture import MockAccounts
from experiments.scripts.serve_platform_workbench import assemble
from packages.infrastructure.platform_rp import RpConfig
from packages.infrastructure.platform_session_store import LocalRpStore
from packages.infrastructure.space_policy_store import SpacePolicyStore
from packages.lifecycle.preview_spaces import PreviewSpaces
from packages.service.space_access import SpaceAccessPolicy
from packages.service.platform_login import PlatformLogin


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence',type=Path,required=True)
    parser.add_argument('--auth-runtime',type=Path,required=True)
    parser.add_argument('--port',type=int,default=8770)
    args=parser.parse_args()
    evidence=args.evidence.resolve();runtime=args.auth_runtime.resolve()
    report=json.loads((evidence/'acceptance.json').read_bytes())
    sample=evidence/'runtime';original=Path('var/nyu').resolve()
    if (report['status']!='passed' or runtime.exists() or sample.resolve()!=Path(report['runtime']).resolve()
            or sample.is_relative_to(original) or original.is_relative_to(sample)
            or runtime.is_relative_to(sample) or sample.is_relative_to(runtime)
            or runtime.is_relative_to(original) or original.is_relative_to(runtime)):
        parser.error('exclusive_verified_demo_runtime_required')
    runtime.mkdir(parents=True)
    accounts=MockAccounts().start()
    try:
        accounts.roles=['workspace:member'];accounts.access_seconds=600
        accounts.identity_options={'usr_manager':'模拟管理员','usr_local_test':'模拟查看者'}
        accounts.rp_origin=f'http://127.0.0.1:{args.port}'
        cfg=RpConfig(issuer=accounts.issuer,backchannel=accounts.issuer,client_id=accounts.client_id,
            client_secret=SecretStr(accounts.secret),origin=accounts.rp_origin,allow_loopback_http=True,
            encryption_key=SecretStr(Fernet.generate_key().decode()))
        directory=PreviewSpaces(sample/'preview-directory')
        scenes=directory.list('space')
        policy=SpaceAccessPolicy.model_validate({
            'bindings':[{'issuer':cfg.issuer,'space_id':scene['id'],'org_id':'org_mock','workspace_id':'ws_mock'} for scene in scenes],
            'grants':[{'issuer':cfg.issuer,'subject':'usr_manager','space_id':scene['id'],'role':'manager'} for scene in scenes]
                +[{'issuer':cfg.issuer,'subject':'usr_local_test','space_id':report['space_id'],'role':'viewer'}]})
        policies=SpacePolicyStore(runtime/'policies')
        policies.replace(policy,expected_revision=0,actor='isolated_scene_demo_setup',reason='verified sample; local mock only')
        rp=PlatformLogin(cfg,LocalRpStore(runtime/'sessions',cfg.encryption_key.get_secret_value()))
        initial=sample/'preview-builds'/report['candidate_id']/'output'
        url=cfg.origin+'/build?space='+report['space_id']+'&tab=flow&job='+report['candidate_id']
        (evidence/'demo.json').write_text(json.dumps({'origin':cfg.origin,'construction_url':url,
            'publication_url':cfg.origin+'/publications/'+report['publication_id']+'/',
            'identity_provider':'local_mock_only','space_id':report['space_id']},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print('LOCAL MOCK ONLY; verified scene: '+url,flush=True)
        uvicorn.run(assemble(rp,policies,sample,initial),host='127.0.0.1',port=args.port,access_log=False)
    finally:accounts.stop()


if __name__=='__main__':main()
