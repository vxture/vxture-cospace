"""Validate local commercial proposals without publishing or granting entitlements."""
from copy import deepcopy
import json
from pathlib import Path

from jsonschema import Draft202012Validator
import pytest


ROOT = Path(__file__).resolve().parents[1]
PROPOSAL = ROOT / 'deploy/config/cospace-subscription-plans.proposal.json'
SCHEMA = ROOT / 'contracts/schemas/subscription-plan-proposal.schema.json'


def load():
    return json.loads(PROPOSAL.read_text(encoding='utf-8'))


def validator():
    schema = json.loads(SCHEMA.read_text(encoding='utf-8'))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def test_proposal_schema_and_relative_schema_link():
    value = load()
    assert (PROPOSAL.parent / value['$schema']).resolve() == SCHEMA
    validator().validate(value)


def test_confirmed_counts_and_proposed_commercial_values_are_consistent():
    value = load()
    pro, business, enterprise = value['plans']
    for plan, members, scenes, gib, credits in (
        (pro, 1, 3, 20, 500), (business, 5, 10, 100, 2500)
    ):
        quota = plan['componentQuotaProposal']
        assert quota == {'member.max': members, 'scene.max': scenes,
                         'storage.bytes': gib * 2**30, 'ai.credit': credits}
        monthly, annual = plan['prices']
        assert annual['amountFen'] == 10 * monthly['amountFen']
    assert [p['prices'][0]['amountFen'] for p in (pro, business)] == [39900, 149900]
    assert enterprise['componentQuotaProposal'] is None
    assert not value['commercialValuesApproved']


@pytest.mark.parametrize('path,replacement', [
    (('billingScope',), 'person'),
    (('platformMutationExecuted',), True),
    (('commercialValuesApproved',), True),
    (('serviceBoundary', 'groundAcquisitionEngineeringIncluded'), True),
    (('serviceBoundary', 'commissionedProcessingEngineeringIncluded'), True),
    (('serviceBoundary', 'supportedAutomatedSoftwareIncluded'), False),
    (('allSoftwareModules',), ['空间预览']),
    (('resourceRules', 'ordinaryGeometryBuildConsumesAiCredits'), True),
    (('resourceRules', 'storageContributionIsHardCap'), True),
    (('resourceRules', 'historicalVersionsConsumeSceneSlots'), True),
    (('resourceRules', 'modelUsageReporter'), 'cospace'),
    (('resourceRules', 'productSeatsAreWorkspaceMemberCount'), True),
    (('plans', 2, 'selfService'), True),
    (('plans', 2, 'prices'), [{'cycle': 'month', 'amountFen': 0}]),
    (('plans', 2, 'componentQuotaProposal'), {'member.max': -1}),
    (('plans', 0, 'componentQuotaProposal', 'storage.bytes'), -1),
    (('plans', 0, 'prices', 0, 'amountFen'), 399.5),
])
def test_unsafe_or_ambiguous_proposal_changes_are_rejected(path, replacement):
    value = deepcopy(load())
    target = value
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = replacement
    assert list(validator().iter_errors(value))


def test_free_integration_proposal_is_explicitly_superseded():
    old = json.loads((ROOT / 'deploy/config/cospace-integration-plan.proposal.json').read_text(encoding='utf-8'))
    assert old['status'] == 'superseded_not_submitted'
    assert (ROOT / old['supersededBy']).resolve() == PROPOSAL
    assert not old['platformMutationExecuted']
