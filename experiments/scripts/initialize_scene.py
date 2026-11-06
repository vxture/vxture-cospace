"""Trusted local administrator: review and apply one Workspace sample scene.

This is NOT a platform login, an HTTP creation endpoint, or inferred owner authority.
"""
import argparse
import json
from pathlib import Path
import sqlite3
from packages.data.preview_source_config import load_sources
from packages.infrastructure.space_policy_store import SpacePolicyStore
from packages.lifecycle.scene_initialization import InitializationRequest,SceneInitialization


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime',type=Path,required=True)
    parser.add_argument('--policy-root',type=Path,required=True)
    parser.add_argument('--request',type=Path,required=True)
    parser.add_argument('--sources-config',type=Path,default=Path('deploy/config/preview-sources.json'))
    parser.add_argument('--presets',type=Path,default=Path('configs/samples/scene-presets.json'))
    commands=parser.add_subparsers(dest='command',required=True)
    commands.add_parser('plan',help='Read-only source and binding checks; emits reviewable plan and digest')
    apply=commands.add_parser('apply',help='Apply exactly the reviewed plan; explicit resume uses a fresh plan')
    apply.add_argument('--expected-revision',type=int,required=True)
    apply.add_argument('--plan-sha256',required=True)
    args=parser.parse_args()
    try:
        request=InitializationRequest.model_validate_json(args.request.read_bytes())
        sources,_=load_sources(args.sources_config,Path.cwd())
        service=SceneInitialization(args.runtime,SpacePolicyStore(args.policy_root),sources,json.loads(args.presets.read_bytes()))
        result=service.plan(request) if args.command=='plan' else service.apply(request,args.expected_revision,args.plan_sha256)
        print(json.dumps(result,ensure_ascii=False,allow_nan=False))
    except (ValueError,OSError,KeyError,TypeError,sqlite3.Error,RuntimeError,ImportError) as exc:
        parser.exit(2,'scene_initialization_refused: '+type(exc).__name__+': '+str(exc)[:500]+'\n')


if __name__=='__main__':main()
