"""Start the isolated identity pilot, using only explicit CoSpace environment config."""
import argparse
from pathlib import Path
import uvicorn
from packages.infrastructure.platform_rp import RpConfig
from packages.infrastructure.platform_session_store import LocalRpStore
from packages.service.platform_login import PlatformLogin
from packages.service.platform_auth_http import create_auth_app
from packages.infrastructure.platform_subscription import SubscriptionConfig,PlatformSubscriptions
from packages.infrastructure.platform_provisioning import ProvisioningReconciler


def main():
    p = argparse.ArgumentParser(); p.add_argument('--runtime', type=Path, required=True)
    p.add_argument('--port', type=int, default=8768)
    a = p.parse_args()
    try: config = RpConfig.from_env()
    except ValueError: p.exit(2, 'rp_configuration_incomplete_or_invalid\n')
    root = a.runtime.resolve(); sample = Path('var/nyu').resolve()
    if root.is_relative_to(sample) or sample.is_relative_to(root): p.exit(2, 'independent_auth_runtime_required\n')
    store = LocalRpStore(root, config.encryption_key.get_secret_value())
    rp=PlatformLogin(config, store)
    # Optional for the identity pilot; production business assembly requires this gate.
    import os
    subscriptions=PlatformSubscriptions(rp,SubscriptionConfig.from_env(),root.parent/'subscription-policy') if os.environ.get('COSPACE_PLATFORM_API_URL') else None
    app = create_auth_app(rp,subscriptions=subscriptions,
        reconciler=ProvisioningReconciler(subscriptions) if subscriptions is not None else None)
    # Bind locally. TLS and public-origin routing belong to the deployment proxy.
    uvicorn.run(app, host='127.0.0.1', port=a.port, access_log=False)


if __name__ == '__main__': main()
