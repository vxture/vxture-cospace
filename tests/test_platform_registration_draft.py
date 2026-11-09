"""Prepared registration must match actual RP paths and safe disabled templates."""
import json
from pathlib import Path
from cryptography.fernet import Fernet
from pydantic import SecretStr
from packages.infrastructure.platform_rp import RpConfig
from packages.service.platform_login import LOGIN_SCOPES
from packages.service.online_consumer import ConsumerConfig
from packages.lifecycle.workspace_scenes import WorkspaceSceneConfig


def test_registered_product_remains_draft_and_client_fields_match_actual_rp():
    draft=json.loads(Path('deploy/config/cospace-platform-registration.draft.json').read_bytes())
    assert draft['status']=='registered_product_draft' and draft['productDraft']['integrationMode']=='platform_managed'
    assert draft['registrationReceipt']['productState']=='draft' and draft['registrationReceipt']['clientState']=='active'
    assert draft['registrationReceipt']['secretIncluded'] is False
    assert draft['productDraft']['subscribable'] is True
    assert draft['productDraft']['surfaces']==['web','desktop']
    assert draft['issuer']=='https://accounts.vxture.com'
    assert len(draft['clientDrafts'])==1
    assert not draft['currentIntegration']['backchannelLogoutReceiverImplemented']
    assert draft['currentIntegration']['provisioningWebhookImplemented']
    assert not draft['currentIntegration']['realWebhookDeliveryVerified']
    for item in draft['clientDrafts']:
        client=item['client']
        cfg=RpConfig(issuer=draft['issuer'],backchannel=draft['issuer'],origin=item['origin'],
                     client_id=client['clientId'],client_secret=SecretStr('synthetic-test-only'),
                     encryption_key=SecretStr(Fernet.generate_key().decode()),allow_loopback_http=item['origin'].startswith('http:'))
        assert client['clientId']=='cospace' and client['releaseChannel']=='stable'
        assert item['origin']=='https://cospace.ruyin.work'
        assert client['redirectUris']==[cfg.callback,'http://127.0.0.1:8791/auth/callback']
        assert client['postLogoutRedirectUris']==[cfg.origin+'/','http://127.0.0.1:8791/']
        assert cfg.cookie_name=='__Host-cospace_rp'
        assert client['allowedScopes']==list(LOGIN_SCOPES)
        assert client['pkceRequired'] and client['tokenEndpointAuthMethod']=='client_secret_basic'
        assert item['realm']=='customer' and client['sloParticipation']=='none' and client['backChannelLogoutUri'] is None
        assert not any(key in client for key in ('secret','clientSecret','client_secret','productId'))


def test_disabled_workspace_and_consumer_templates_grant_no_access():
    workspace=json.loads(Path('deploy/config/cospace-workspace-scenes.disabled.json').read_bytes())
    assert workspace=={'profile':'cospace.workspace-scenes/0.1','revision':1,'workspaces':[]}
    assert not WorkspaceSceneConfig.model_validate(workspace).workspaces
    consumer=ConsumerConfig.model_validate_json(Path('deploy/config/cospace-consumer-access.disabled.json').read_bytes())
    assert consumer.audience=='cospace' and not consumer.grants


def test_stable_origin_and_temporary_local_env_have_no_secrets():
    draft=json.loads(Path('deploy/config/cospace-platform-registration.draft.json').read_bytes())
    for name,origin,loopback in (
            ('production','https://cospace.ruyin.work','0'),
            ('local','http://127.0.0.1:8791','1')):
        env=Path(f'deploy/config/cospace-platform-{name}.env.example').read_text()
        values=dict(line.split('=',1) for line in env.splitlines() if line and not line.startswith('#'))
        assert values['COSPACE_ORIGIN']==origin
        assert values['COSPACE_OIDC_CLIENT_ID']=='cospace'
        assert values['COSPACE_OIDC_ISSUER']==values['COSPACE_OIDC_BACKCHANNEL']==draft['issuer']
        assert values['COSPACE_OIDC_LOOPBACK_HTTP']==loopback
        assert 'COSPACE_SESSION_KEY' not in values and 'COSPACE_OIDC_CLIENT_SECRET' not in values


def test_edge_draft_and_integration_gaps_are_explicit():
    draft=json.loads(Path('deploy/config/cospace-platform-registration.draft.json').read_bytes())
    assert draft['edgeDraft']=={'edgeDomain':'cospace.ruyin.work','edgeUpstream':'100.100.197.42:8793',
        'homeUrl':'https://cospace.ruyin.work','webhookUrl':'https://cospace.ruyin.work/api/webhooks/vxture'}
    assert draft['temporaryLocalIntegration']['clientId']=='cospace'
    assert draft['temporaryLocalIntegration']['removeLoopbackCallbacksAfterProductionAcceptance']
    assert draft['currentIntegration']['subscriptionEntitlementGateImplemented']
    assert draft['currentIntegration']['realEntitlementReadVerified']
    assert draft['authenticationBoundary']['productDomainChangeDoesNotChangeIssuer']
    assert not draft['authenticationBoundary']['desktopNativeClientImplemented']
