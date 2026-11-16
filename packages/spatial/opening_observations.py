"""Durable reported opening states, independent of synthetic graphs and field adoption.

Trusted callers must authorize scope and producer before calling this module.
Registration binds references; it does not certify a model or observation.
"""
from datetime import datetime, timezone
from typing import Annotated, Literal

from pydantic import Field, model_validator

from packages.spatial.scene_graph import Fixed, Identity, utc
from packages.spatial.scene_identity import Digest, content_digest


class Scope(Fixed):
    issuer: Annotated[str, Field(min_length=1, max_length=512)]
    organization: Identity
    workspace: Identity
    space_id: Annotated[str, Field(pattern=r'^space-[a-f0-9]{16}$')]
    catalog_sha256: Digest


class Subject(Fixed):
    entity_id: Annotated[str, Field(min_length=1, max_length=255)]
    role: Literal['door']


class Registration(Fixed):
    profile: Literal['cospace.opening-observation-registration/0.1']
    scope: Scope
    data_kind: Literal['ifc_design_candidate', 'synthetic']
    subjects: Annotated[list[Subject], Field(min_length=1, max_length=1000)]
    producers: Annotated[list[Identity], Field(min_length=1, max_length=64)]

    @model_validator(mode='after')
    def identities(self):
        if (len({s.entity_id for s in self.subjects}) != len(self.subjects)
                or len(set(self.producers)) != len(self.producers)):
            raise ValueError('observation_registration_duplicates')
        return self


class Report(Fixed):
    profile: Literal['cospace.opening-observation-report/0.1']
    event_id: Identity
    producer: Identity
    entity_id: Annotated[str, Field(min_length=1, max_length=255)]
    operation: Literal['assert', 'retract'] = 'assert'
    value: Literal['open', 'closed', 'partially_open', 'unknown'] | None
    observed_at: Annotated[str, Field(min_length=20, max_length=40)]
    valid_until: Annotated[str, Field(min_length=20, max_length=40)]
    evidence_sha256: Annotated[list[Digest], Field(min_length=1, max_length=16)]
    supersedes: Identity | None = None

    @model_validator(mode='after')
    def temporal_bounds(self):
        if utc(self.valid_until) <= utc(self.observed_at):
            raise ValueError('observation_expiry_required')
        if len(set(self.evidence_sha256)) != len(self.evidence_sha256):
            raise ValueError('observation_duplicate_evidence')
        if self.operation == 'retract':
            if self.supersedes is None or self.value is not None:
                raise ValueError('observation_retraction_requires_target_and_null')
        elif self.value is None:
            raise ValueError('observation_assertion_requires_value')
        return self


def now_utc():
    return datetime.now(timezone.utc).isoformat(timespec='microseconds').replace('+00:00', 'Z')


def scope_key(scope):
    value = Scope.model_validate(scope)
    return content_digest(value.model_dump())


def validate_correction(report, previous, *, already_corrected=False):
    if report.supersedes is None:
        return
    if (previous is None or previous['entity_id'] != report.entity_id
            or utc(previous['observed_at']) != utc(report.observed_at)
            or already_corrected):
        raise ValueError('observation_correction_binding')


def _latest(remaining):
    latest = []
    for producer in sorted({r['report']['producer'] for r in remaining}):
        group = [r for r in remaining if r['report']['producer'] == producer]
        newest = max(utc(r['report']['observed_at']) for r in group)
        latest.extend(r for r in group if utc(r['report']['observed_at']) == newest)
    return latest


def _status(latest, live, values):
    if not latest:
        status = 'unavailable'
    elif not live:
        status = 'expired'
    elif not values:
        status = 'retracted'
    elif len(values) > 1:
        status = 'conflict'
    elif values == {'unknown'}:
        status = 'unknown'
    else:
        status = 'reported'
    return status


def resolve_reports(records, entity, when):
    visible = [r for r in records if r['report']['entity_id'] == entity
               and utc(r['report']['observed_at']) <= when]
    replaced = {(r['report']['producer'], r['report']['supersedes']) for r in visible}
    remaining = [r for r in visible if (r['report']['producer'], r['report']['event_id']) not in replaced]
    latest = _latest(remaining)
    live = [r for r in latest if utc(r['report']['valid_until']) > when]
    active = [r for r in live if r['report']['operation'] == 'assert']
    retracted = [r for r in live if r['report']['operation'] == 'retract']
    values = {r['report']['value'] for r in active}
    status = _status(latest, live, values)
    return status, next(iter(values)) if status == 'reported' else None, latest, active, retracted
