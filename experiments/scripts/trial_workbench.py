"""Fixed Windows trial entry. Mock is explicit; real mode never falls back to it."""
import argparse
from datetime import datetime,timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import secrets
import socket
import sys
import threading
from pydantic import BaseModel,ConfigDict,Field,model_validator,SecretStr
from cryptography.fernet import Fernet
import uvicorn
from packages.infrastructure.preview_service_lock import service_guard
from packages.infrastructure.preview_backup import validate_runtime
from packages.infrastructure.platform_rp import RpConfig
from packages.infrastructure.platform_session_store import LocalRpStore
from packages.infrastructure.space_policy_store import SpacePolicyStore
from packages.infrastructure.trial_job import bind_trial_process
from packages.service.platform_login import PlatformLogin
from experiments.scripts.serve_platform_workbench import assemble

REPO=Path(__file__).resolve().parents[2]


class TrialConfig(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True,frozen=True)
    profile:str=Field(pattern=r'^cospace.windows-trial/0\.1$')
    mode:str=Field(pattern=r'^(mock|platform)$')
    port:int=Field(ge=1024,le=65535)
    accounts_port:int=Field(ge=1024,le=65535)
    business_root:str
    state_root:str

    @model_validator(mode='after')
    def roots(self):
        business,state=Path(self.business_root),Path(self.state_root)
        if not business.is_absolute() or not state.is_absolute():raise ValueError('absolute_trial_paths_required')
        business,state=business.resolve(),state.resolve()
        protected=[REPO/'var/nyu',REPO/'var/samples',REPO/'var/validation']
        if (business.is_relative_to(state) or state.is_relative_to(business) or self.port==self.accounts_port or
            business==REPO or state==REPO or business in REPO.parents or state in REPO.parents or
            any(business.is_relative_to(p) or p.is_relative_to(business) or state.is_relative_to(p) or p.is_relative_to(state) for p in protected)):
            raise ValueError('isolated_trial_paths_required')
        return self


def load(path):return TrialConfig.model_validate_json(Path(path).read_bytes())
def stamp():return datetime.now(timezone.utc).isoformat()
def write(path,doc):
    path=Path(path);temporary=path.with_suffix('.tmp');temporary.write_text(json.dumps(doc,ensure_ascii=False,indent=2),encoding='utf-8');temporary.replace(path)


def release(config):
    files={}
    for group in ('packages','experiments/scripts','contracts/schemas','apps/workbench/dist'):
        for path in sorted((REPO/group).rglob('*')):
            if path.is_file() and '__pycache__' not in path.parts and path.suffix not in ('.pyc',):
                files[path.relative_to(REPO).as_posix()]=hashlib.sha256(path.read_bytes()).hexdigest()
    for name in ('pyproject.toml','uv.lock','apps/workbench/pnpm-lock.yaml','apps/workbench/package.json'):
        path=REPO/name;files[name]=hashlib.sha256(path.read_bytes()).hexdigest()
    if 'apps/workbench/dist/index.html' not in files:raise ValueError('compiled_workbench_required')
    versions={p:importlib.metadata.version(p) for p in ('fastapi','pydantic','uvicorn','rosbags','joserfc','cryptography')}
    # Some local NumPy wheel metadata lacks Version; pin the imported runtime.
    import numpy
    import scipy
    versions.update(numpy=numpy.__version__,scipy=scipy.__version__)
    if any(not isinstance(v,str) or not v for v in versions.values()):raise ValueError('runtime_versions_unavailable')
    return {'profile':'cospace.trial-release/0.1','repo':str(REPO),'python':sys.version,'interpreter':sys.executable,
            'packages':versions,'files':files,'deployment':config.model_dump()}


def initialize(config):
    if config.mode!='mock':raise ValueError('platform_requires_explicit_tenant_setup')
    root=Path(config.business_root);root.mkdir(parents=True,exist_ok=False)
    for name in ('runtime','policy','setup'):(root/name).mkdir()
    issuer=f'http://127.0.0.1:{config.accounts_port}'
    write(root/'setup/sources.json',{'profile':'cospace.preview-sources/0.1','sources':[]})
    write(root/'setup/workspace-scenes.json',{'profile':'cospace.workspace-scenes/0.1','revision':1,
        'workspaces':[{'issuer':issuer,'org_id':'org_mock','workspace_id':'ws_mock','allow_create':True,'creator_subjects':[],'source_bindings':{}}]})
    write(root/'setup/consumer-access.json',{'profile':'cospace.online-consumer-access/0.1','audience':'cospace','grants':[]})
    from packages.service.space_access import SpaceAccessPolicy
    SpacePolicyStore(root/'policy').replace(SpaceAccessPolicy(bindings=[],grants=[]),expected_revision=0,actor='trial_mock_setup',reason='explicit empty trial')


def current(config):
    state=Path(config.state_root)
    try:
        with service_guard(state/'control'):return {'status':'stopped'}
    except ValueError:
        path=state/'run.json'
        if not path.is_file():return {'status':'starting'}
        doc=json.loads(path.read_bytes())
        return {k:doc[k] for k in ('status','instance','started_at','origin','mode')}


def serve(config):
    if Path.cwd().resolve()!=REPO:raise ValueError('run_from_repository_root')
    state=Path(config.state_root);root=Path(config.business_root)
    expected=json.loads((state/'release.json').read_bytes())
    if release(config)!=expected:raise ValueError('trial_release_changed_reseal_after_acceptance')
    validate_runtime(root)
    if config.mode=='platform':
        rp_config=RpConfig.from_env()
        if rp_config.origin not in (f'http://127.0.0.1:{config.port}',) and not rp_config.origin.startswith('https://'):
            raise ValueError('platform_origin_requires_https_or_exact_loopback')
    # Check bind availability before creating accounts/session state.
    ports=(config.port,config.accounts_port) if config.mode=='mock' else (config.port,)
    for port in ports:
        with socket.socket() as probe:probe.bind(('127.0.0.1',port))
    with service_guard(state/'control'),service_guard(root/'runtime'):
        bind_trial_process()
        instance=secrets.token_hex(16);session_root=state/'sessions'/instance;session_root.mkdir(parents=True)
        accounts=None
        try:
            if config.mode=='mock':
                from experiments.scripts.platform_auth_fixture import MockAccounts
                accounts=MockAccounts(port=config.accounts_port).start();accounts.rp_origin=f'http://127.0.0.1:{config.port}'
                accounts.roles=['workspace:member'];accounts.access_seconds=3600
                accounts.identity_options={'usr_owner':'模拟工作区所有者','usr_manager':'模拟场景管理员','usr_local_test':'模拟查看者','usr_unassigned':'模拟未授权成员'}
                accounts.identity_roles={'usr_owner':['workspace:owner']}
                service_fixture=os.environ.get('COSPACE_MOCK_SERVICE_CONFIG')
                if service_fixture:
                    fixture=Path(service_fixture).resolve()
                    if fixture.is_relative_to(root):raise ValueError('mock_credentials_outside_business_backup_required')
                    accounts.service_clients=json.loads(fixture.read_bytes())
                rp_config=RpConfig(issuer=accounts.issuer,backchannel=accounts.issuer,client_id=accounts.client_id,
                    client_secret=SecretStr(accounts.secret),origin=accounts.rp_origin,allow_loopback_http=True,
                    encryption_key=SecretStr(Fernet.generate_key().decode()))
            rp=PlatformLogin(rp_config,LocalRpStore(session_root,rp_config.encryption_key.get_secret_value()))
            app=assemble(rp,SpacePolicyStore(root/'policy'),root/'runtime',None,root/'setup/sources.json',root/'setup/workspace-scenes.json',root/'setup/consumer-access.json')
            server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=config.port,access_log=False,timeout_graceful_shutdown=15))
            record={'status':'running','instance':instance,'started_at':stamp(),'origin':rp_config.origin,'mode':config.mode}
            write(state/'run.json',record)
            done=threading.Event()
            def watch():
                while not done.wait(.25):
                    try:
                        if json.loads((state/'stop.json').read_bytes()).get('instance')==instance:
                            server.should_exit=True;return
                    except (OSError,ValueError):pass
            thread=threading.Thread(target=watch,daemon=True);thread.start()
            print(('LOCAL MOCK ONLY ' if config.mode=='mock' else 'PLATFORM TRIAL ')+rp_config.origin+'/',flush=True)
            try:server.run()
            finally:done.set();thread.join(timeout=1);write(state/'run.json',record|{'status':'stopped','stopped_at':stamp()})
        finally:
            if accounts:accounts.stop()


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',choices=['initialize','seal','run','status','stop'])
    p.add_argument('--config',type=Path,required=True);a=p.parse_args()
    try:
        cfg=load(a.config);state=Path(cfg.state_root)
        if a.command=='initialize':initialize(cfg);result={'status':'initialized_empty_mock'}
        elif a.command=='seal':
            state.mkdir(parents=True,exist_ok=True)
            with service_guard(state/'control'):
                with (state/'release.json').open('x',encoding='utf-8') as stream:json.dump(release(cfg),stream,ensure_ascii=False,indent=2)
            result={'status':'sealed','release':str(state/'release.json')}
        elif a.command=='run':serve(cfg);return
        elif a.command=='status':result=current(cfg)
        else:
            result=current(cfg)
            if result['status']=='running':write(state/'stop.json',{'instance':result['instance']});result={'status':'stop_requested'}
        print(json.dumps(result,ensure_ascii=False))
    except Exception:p.exit(2,'trial_command_rejected; check fixed configuration, release, credentials, ports, and service locks\n')


if __name__=='__main__':main()
