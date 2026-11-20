from test_platform_business import secured, sign_in
from test_platform_login import runtime
from packages.ontology.kernel import builtin_catalog

PATH = '/api/ontology-definitions'


def test_authoring_http_permissions_csrf_and_trusted_context(secured):
    _, client, *_ = secured
    assert client.get(PATH, params={'module_id': 'core'}).status_code == 401
    headers, _ = sign_in(secured, 'usr_engineer')
    result = client.get(PATH, params={'module_id': 'core'})
    assert result.status_code == 200 and not result.json()['can_manage']
    body = {'action': 'save', 'request_id': 'a' * 32, 'module_id': 'core', 'expected_revision': 0,
            'bundle': builtin_catalog().export('core'), 'base_reference': None}
    assert client.post(PATH, json=body, headers=headers).status_code == 403
    headers, _ = sign_in(secured, 'usr_manager')
    assert client.post(PATH, json=body).status_code == 403
    assert client.post(PATH, json={**body, 'actor': 'forged'}, headers=headers).status_code == 422
    saved = client.post(PATH, json=body, headers=headers)
    assert saved.status_code == 200, saved.text
    assert saved.json()['updated_by'] == 'usr_manager'
    assert client.post(PATH, json=body, headers=headers).json()['revision'] == 1
    assert client.get(PATH + '?module_id=core&workspace_id=forged').status_code == 422
    assert client.get(PATH + '?module_id=core&module_id=water').status_code == 403
    assert client.post(PATH,json={'action':'decide','request_id':'e'*32,'review_id':{},'decision':'approved','reason':'x'},headers=headers).status_code == 422
    submit = {'action': 'submit', 'request_id': 'b' * 32, 'module_id': 'core', 'expected_revision': 1}
    assert client.post(PATH, json=submit, headers=headers).status_code == 200
    assert client.get(PATH,params={'review_id':'b'*32}).status_code == 200
    decision = {'action': 'decide', 'request_id': 'c' * 32, 'review_id': 'b' * 32, 'decision': 'approved', 'reason': '核对通过'}
    assert client.post(PATH, json=decision, headers=headers).json()['detail'] == 'self_approval_forbidden'
    # A second trusted workspace owner can review; no body actor impersonation.
    accounts = secured[2]
    accounts.roles = ['workspace:owner']
    reviewer_headers, _ = sign_in(secured, 'usr_reviewer')
    reviewed = client.post(PATH, json=decision, headers=reviewer_headers)
    assert reviewed.status_code == 200, reviewed.text
    published = client.post(PATH, json={'action': 'publish', 'request_id': 'd' * 32,
                                     'review_id': 'b' * 32, 'expected_revision': 1}, headers=reviewer_headers)
    assert published.status_code == 200, published.text
    reference = published.json()['reference']
    assert client.get(PATH, params=reference).status_code == 200
    directory = client.get('/api/ontology-resources').json()
    item = next(i for i in directory['items'] if i['reference']['module_id'] == 'core')
    assert item['published_at'] == published.json()['published_at']
    assert client.get('/api/ontology-resources/definition', params=reference).status_code == 200
    accounts.roles = ['workspace:member']
    sign_in(secured, 'usr_engineer')
    state = client.get(PATH, params={'module_id': 'core'}).json()
    assert state['draft'] is None and state['reviews'] == [] and state['releases']
    assert client.get(PATH,params={'review_id':'b'*32}).status_code == 403
