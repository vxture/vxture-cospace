"""Explicit LOCAL MOCK login demo. No real platform client or original sample data."""
import argparse
from pathlib import Path
import uvicorn
from cryptography.fernet import Fernet
from pydantic import SecretStr
from experiments.scripts.platform_auth_fixture import MockAccounts
from packages.infrastructure.platform_rp import RpConfig
from packages.infrastructure.platform_session_store import LocalRpStore
from packages.service.platform_login import PlatformLogin
from packages.service.platform_auth_http import create_auth_app


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--runtime',type=Path,required=True); p.add_argument('--port',type=int,default=8768)
    a=p.parse_args(); root=a.runtime.resolve()
    sample=Path('var/nyu').resolve()
    if root.exists() or root.is_relative_to(sample) or sample.is_relative_to(root):
        p.exit(2,'new_separate_mock_runtime_required\n')
    accounts=MockAccounts().start(); accounts.rp_origin='http://127.0.0.1:'+str(a.port)
    cfg=RpConfig(issuer=accounts.issuer,backchannel=accounts.issuer,client_id=accounts.client_id,
        client_secret=SecretStr(accounts.secret),origin=accounts.rp_origin,allow_loopback_http=True,
        encryption_key=SecretStr(Fernet.generate_key().decode()))
    store=LocalRpStore(root,cfg.encryption_key.get_secret_value())
    app=create_auth_app(PlatformLogin(cfg,store))
    print('LOCAL MOCK ONLY; no real accounts authentication; '+cfg.origin+'/workbench/layout.html',flush=True)
    try: uvicorn.run(app,host='127.0.0.1',port=a.port,access_log=False)
    finally: accounts.stop()


if __name__=='__main__':main()
