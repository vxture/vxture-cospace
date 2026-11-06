"""Trusted local administrator applies a full policy with revision and audit reason."""
import argparse
import json
from pathlib import Path
from packages.infrastructure.space_policy_store import SpacePolicyStore
from packages.service.space_access import SpaceAccessPolicy


def main():
    p=argparse.ArgumentParser();p.add_argument('--runtime',type=Path,required=True)
    p.add_argument('--policy',type=Path,required=True);p.add_argument('--expected-revision',type=int,required=True)
    p.add_argument('--actor',required=True);p.add_argument('--reason',required=True);a=p.parse_args()
    root=a.runtime.resolve();sample=Path('var/nyu').resolve()
    if root.is_relative_to(sample) or sample.is_relative_to(root):p.exit(2,'independent_access_runtime_required\n')
    try:
        policy=SpaceAccessPolicy.model_validate_json(a.policy.read_bytes())
        revision=SpacePolicyStore(root).replace(policy,expected_revision=a.expected_revision,actor=a.actor,reason=a.reason)
    except (ValueError,OSError):p.exit(2,'policy_change_rejected\n')
    print(json.dumps({'revision':revision,'bound_spaces':len(policy.bindings),'member_grants':len(policy.grants)}))


if __name__=='__main__':main()
