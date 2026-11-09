"""Single Linux service: private file secrets, explicit empty bootstrap, real platform only."""
import argparse
import json
import os
from pathlib import Path
import stat
import uvicorn
from packages.infrastructure.platform_rp import RpConfig
from packages.infrastructure.platform_session_store import LocalRpStore
from packages.infrastructure.platform_subscription import SubscriptionConfig
from packages.infrastructure.space_policy_store import SpacePolicyStore
from packages.infrastructure.preview_service_lock import service_guard
from packages.infrastructure.preview_backup import validate_runtime
from packages.service.platform_login import PlatformLogin
from packages.service.space_access import SpaceAccessPolicy
from experiments.scripts.serve_platform_workbench import assemble

SECRETS=('COSPACE_OIDC_CLIENT_SECRET','COSPACE_SESSION_KEY','COSPACE_PLATFORM_WEBHOOK_SECRET',
         'COSPACE_PLATFORM_WEBHOOK_PREVIOUS_SECRET','COSPACE_AMAP_WEB_KEY','COSPACE_AMAP_SECURITY_JS_CODE')


def load_file_secrets():
    for name in SECRETS:
        location=os.environ.get(name+'_FILE')
        if not location:continue
        path=Path(location)
        if (os.environ.get(name) or not path.is_absolute() or path.is_symlink() or not path.is_file()
                or not 0<path.stat().st_size<=8192
                or os.name!='nt' and stat.S_IMODE(path.stat().st_mode)&0o077):
            raise ValueError('private_secret_file_required')
        value=path.read_text(encoding='utf-8').strip()
        if not value or '\n' in value or '\r' in value:raise ValueError('single_secret_value_required')
        os.environ[name]=value


def roots(business,state):
    business,state=Path(business),Path(state)
    if not business.is_absolute() or not state.is_absolute():raise ValueError('absolute_service_roots_required')
    business,state=business.resolve(),state.resolve()
    if (business.parent==business or state.parent==state or business.is_relative_to(state)
            or state.is_relative_to(business) or business.is_relative_to(Path.cwd().resolve())
            or state.is_relative_to(Path.cwd().resolve())):
        raise ValueError('independent_service_roots_required')
    return business,state


def initialize(business):
    """Explicit first-run command; never silently replaces a populated root."""
    business=Path(business)
    business.mkdir(parents=True,exist_ok=True)
    if any(business.iterdir()):raise ValueError('empty_business_root_required')
    for name in ('runtime','policy','setup'):(business/name).mkdir()
    documents={
        'sources.json':{'profile':'cospace.preview-sources/0.1','sources':[]},
        'workspace-scenes.json':{'profile':'cospace.workspace-scenes/0.1','revision':1,'workspaces':[]},
        'consumer-access.json':{'profile':'cospace.online-consumer-access/0.1','audience':'cospace','grants':[]},
        'scene-pointclouds.json':{'profile':'cospace.scene-pointcloud-bindings/0.1','bindings':[]},
        'scene-ifc.json':{'profile':'cospace.scene-ifc-bindings/0.1','bindings':[]},
    }
    for name,value in documents.items():
        (business/'setup'/name).write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8')
    SpacePolicyStore(business/'policy').replace(SpaceAccessPolicy(bindings=[],grants=[]),
        expected_revision=0,actor='production_initialization',reason='empty real platform scope; no mock data')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=['initialize','run'])
    p.add_argument('--business',type=Path,default=Path('/data'))
    p.add_argument('--state',type=Path,default=Path('/state'))
    p.add_argument('--port',type=int,default=8088)
    a=p.parse_args()
    try:
        business,state=roots(a.business,a.state)
        if a.action=='initialize':
            initialize(business);print('initialized_empty_real_platform_scope');return
        load_file_secrets()
        config=RpConfig.from_env();SubscriptionConfig.from_env()
        if (config.issuer!='https://accounts.vxture.com' or config.client_id!='cospace'
                or config.origin!='https://cospace.ruyin.work' or config.allow_loopback_http):
            raise ValueError('registered_production_configuration_required')
        validate_runtime(business)
        policies=SpacePolicyStore(business/'policy');policies.load()
        rp=PlatformLogin(config,LocalRpStore(state/'sessions',config.encryption_key.get_secret_value()))
        with service_guard(business/'runtime'):
            app=assemble(rp,policies,business/'runtime',sources_config=business/'setup/sources.json',
                workspace_config=business/'setup/workspace-scenes.json',consumer_config=business/'setup/consumer-access.json',
                scene_pointcloud_config=business/'setup/scene-pointclouds.json' if (business/'setup/scene-pointclouds.json').exists() else None,
                scene_ifc_config=business/'setup/scene-ifc.json' if (business/'setup/scene-ifc.json').exists() else None)
            # Docker publishes only the explicit tailnet interface. No proxy trust
            # is needed: public origin and callback URLs come from trusted config.
            uvicorn.run(app,host='0.0.0.0',port=a.port,access_log=False,proxy_headers=False,
                timeout_graceful_shutdown=30,limit_concurrency=32)
    except (OSError,ValueError,RuntimeError):p.exit(2,'production_configuration_or_runtime_rejected\n')


if __name__=='__main__':main()
