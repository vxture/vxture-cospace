"""Authorized workbench; explicit platform client, policy, and isolated sample copy."""
import argparse
from pathlib import Path
import uvicorn
from packages.infrastructure.platform_rp import RpConfig
from packages.infrastructure.platform_session_store import LocalRpStore
from packages.infrastructure.space_policy_store import SpacePolicyStore
from packages.service.platform_login import PlatformLogin
from packages.service.platform_auth_http import create_auth_app
from packages.service.platform_business_http import BusinessAccess
from packages.lifecycle.preview_spaces import PreviewSpaces
from packages.data.preview_inputs import PreviewInputs
from packages.construction.preview_jobs import PreviewJobs
from packages.ontology.preview_versions import PreviewOntologies
from packages.data.preview_ledger import PreviewLedger
from packages.data.preview_source_config import load_sources
from experiments.scripts.serve_nyu_flow_preview import create_app
from packages.infrastructure.preview_service_lock import service_guard
from packages.infrastructure.platform_subscription import SubscriptionConfig,PlatformSubscriptions
from packages.infrastructure.platform_provisioning import ProvisioningReconciler
from packages.infrastructure.platform_usage import StorageInventory, StorageReporter, UsageTransport


def assemble(rp,policies,sample,initial=None,sources_config=Path('deploy/config/preview-sources.json'),workspace_config=None,consumer_config=None,scene_pointcloud_config=None,scene_ifc_config=None):
    sample=Path(sample).resolve();directory=PreviewSpaces(sample/'preview-directory')
    inputs=PreviewInputs(sample/'preview-inputs',directory)
    jobs=PreviewJobs(sample/'preview-builds',Path('.'),Path('.'),inputs)
    ontologies=PreviewOntologies(sample/'preview-ontologies')
    ledger=PreviewLedger(sample/'preview-ledger',directory)
    business=create_app(initial,jobs,space_directory=directory,ontologies=ontologies,ledger=ledger,platform_origin=rp.config.origin)
    sources,_=load_sources(sources_config,Path.cwd())
    subscriptions=PlatformSubscriptions(rp,SubscriptionConfig.from_env(),policies.path.parent) if rp.config.issuer.startswith('https://') else None
    return create_auth_app(rp,business=business,subscriptions=subscriptions,
        reconciler=ProvisioningReconciler(subscriptions) if subscriptions is not None else None,
        usage_reporter=StorageReporter(StorageInventory(policies,inputs,jobs),UsageTransport(rp,subscriptions.config)) if subscriptions is not None else None,
        access=BusinessAccess(rp,policies,directory,jobs,sources,workspace_config,consumer_config,subscriptions,scene_pointcloud_config,scene_ifc_config))


def main():
    p=argparse.ArgumentParser();p.add_argument('--runtime',type=Path,required=True)
    p.add_argument('--sample',type=Path,required=True);p.add_argument('--initial',type=Path,help='Optional existing engineering fallback; omit for a new empty business runtime')
    p.add_argument('--port',type=int,default=8769)
    p.add_argument('--workspace-scenes-config',type=Path)
    p.add_argument('--consumer-config',type=Path,help='Optional trusted service-caller scene grants; enables only /s2s fixed-version queries')
    p.add_argument('--scene-pointcloud-config',type=Path,help='Optional scene-scoped full pointcloud/LOD bindings; browser cannot set paths')
    p.add_argument('--scene-ifc-config',type=Path,help='Optional scene-scoped inspected IFC catalogs; native parsing stays offline')
    p.add_argument('--sessions',type=Path,help='Optional separate session directory; keep outside a cold-backup business root')
    p.add_argument('--sources-config',type=Path,default=Path('deploy/config/preview-sources.json'));a=p.parse_args()
    original=Path('var/nyu').resolve();sample=a.sample.resolve();runtime=a.runtime.resolve()
    if (sample.is_relative_to(original) or original.is_relative_to(sample)
            or runtime.is_relative_to(original) or original.is_relative_to(runtime)
            or runtime.is_relative_to(sample) or sample.is_relative_to(runtime)
            or a.initial is not None and not a.initial.resolve().is_relative_to(sample)):
        p.exit(2,'separate_sample_copy_and_auth_runtime_required\n')
    try:
        config=RpConfig.from_env();policies=SpacePolicyStore(runtime);policies.load()
        rp=PlatformLogin(config,LocalRpStore(a.sessions or runtime/'sessions',config.encryption_key.get_secret_value()))
        with service_guard(sample):
            app=assemble(rp,policies,sample,a.initial,a.sources_config,a.workspace_scenes_config,a.consumer_config,a.scene_pointcloud_config,a.scene_ifc_config)
            uvicorn.run(app,host='127.0.0.1',port=a.port,access_log=False)
    except (ValueError,OSError,RuntimeError):p.exit(2,'authorized_workbench_configuration_rejected\n')


if __name__=='__main__':main()
