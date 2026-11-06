"""Generation metadata for synthetic diagnostics; checksums are not trust proofs."""
from datetime import datetime
import os
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from packages.data.imports import canonical, sha

Digest = Annotated[str, Field(pattern=r'^[0-9a-f]{64}$')]
Counter = Annotated[int, Field(ge=0, le=9007199254740991)]
Timestamp = Annotated[str, Field(pattern=r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z$')]


class Metadata(BaseModel):
    model_config = ConfigDict(strict=True, extra='forbid')


class JournalControl(Metadata):
    store_id: str
    context: Digest
    generation: Annotated[int, Field(ge=1, le=9007199254740991)]
    mode: Literal['normal', 'recovering']
    revision: Counter
    state_sha256: Digest

    @field_validator('store_id')
    @classmethod
    def uuid_string(cls, value):
        if str(UUID(value)) != value:
            raise ValueError('canonical UUID required')
        return value


class FileSource(Metadata):
    kind: Literal['file-packages']
    locator_sha256: Digest
    component_report_sha256: Digest


class JournalSource(Metadata):
    kind: Literal['recovery-journal']
    locator_sha256: Digest
    component_report_sha256: Digest
    control: JournalControl | None


class Sources(Metadata):
    files: FileSource
    journal: JournalSource


class Interval(Metadata):
    started_at: Timestamp
    finished_at: Timestamp
    elapsed_ms: Counter
    clock: Literal['system_utc_untrusted']
    wall_end_before_start: bool
    consistency: Literal['independent_readonly_snapshots']

    @field_validator('started_at', 'finished_at')
    @classmethod
    def real_calendar_time(cls, value):
        datetime.fromisoformat(value)
        return value

    @model_validator(mode='after')
    def clock_order(self):
        if self.wall_end_before_start != (self.finished_at < self.started_at):
            raise ValueError('clock order flag inconsistent')
        return self


class Producer(Metadata):
    name: Literal['cospace.delivery-audit']
    version: Literal['0.2']


class ReportGeneration(Metadata):
    schema_version: Literal['cospace.delivery-generation/0.1']
    report_id: str
    producer: Producer
    interval: Interval
    limit: Annotated[int, Field(ge=1, le=200)]
    binding_sha256: Digest
    payload_sha256: Digest
    sources: Sources

    @field_validator('report_id')
    @classmethod
    def uuid4_string(cls, value):
        parsed = UUID(value)
        if str(parsed) != value or parsed.version != 4:
            raise ValueError('canonical UUID4 required')
        return value


def locator_digest(root):
    """Local normalized locator only: relocation or replacement changes its meaning."""
    return sha(canonical(os.path.normcase(os.path.abspath(root))))


def generation_context(report, files_root, journal_root, limit):
    control = report['components']['journal'].get('control')
    try:
        control = JournalControl.model_validate(control).model_dump()
    except ValueError:
        control = None
    return {'limit': limit, 'binding_sha256': sha(canonical(report['requested_binding'])),
            'payload_sha256': sha(canonical(report)), 'sources': {
                'files': {'kind': 'file-packages', 'locator_sha256': locator_digest(files_root),
                          'component_report_sha256': sha(canonical(report['components']['files']))},
                'journal': {'kind': 'recovery-journal', 'locator_sha256': locator_digest(journal_root),
                            'component_report_sha256': sha(canonical(report['components']['journal'])),
                            'control': control}}}


def validate_generation(report):
    """Validate before projection discards raw component fields; never upgrade legacy data."""
    if report['schema_version'] == 'cospace.test-delivery-audit/0.1':
        if report.get('generation') is not None:
            raise ValueError('legacy report cannot claim generation metadata')
        return None
    generation = ReportGeneration.model_validate(report.get('generation'))
    payload = {k: v for k, v in report.items() if k != 'generation'}
    if (generation.binding_sha256 != sha(canonical(report['requested_binding']))
            or generation.payload_sha256 != sha(canonical(payload))
            or generation.sources.files.component_report_sha256 != sha(canonical(report['components']['files']))
            or generation.sources.journal.component_report_sha256 != sha(canonical(report['components']['journal']))):
        raise ValueError('generation context checksum mismatch')
    control = report['components']['journal'].get('control')
    try:
        expected = JournalControl.model_validate(control)
    except ValueError:
        expected = None
    if generation.sources.journal.control != expected:
        raise ValueError('journal observation identity differs from component')
    return generation
