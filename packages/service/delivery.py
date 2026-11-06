"""Bounded projection of a configured saved diagnostic. Never scans or authorizes."""
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from packages.infrastructure.files import safe_path
from packages.data.imports import ImportError
from packages.service.sample import read_json
from packages.data.delivery_report import ReportGeneration, validate_generation

Text = Annotated[str, Field(min_length=1, max_length=128)]
Digest = Annotated[str, Field(pattern=r'^[0-9a-f]{64}$')]


class Shape(BaseModel):
    model_config = ConfigDict(strict=True, extra='ignore')


class Binding(Shape):
    scene_id: Text
    release_id: Text
    truth_version_id: Text
    view_version_id: Text
    package_sha256: Digest
    release_sha256: Digest
    truth_sha256: Digest
    view_sha256: Digest
    profile: Text
    scope_sha256: Digest


class Observation(Shape):
    file_binding: Binding | None
    journal_binding: Binding | None
    active_revision: Annotated[int, Field(ge=0)] | None
    binding_match: bool
    journal_status: Literal['not_checked', 'proof_fields_present_unverified', 'proof_fields_missing']


class Finding(Shape):
    code: Text
    component: Literal['files', 'journal', 'binding']
    next_action: Annotated[str, Field(min_length=1, max_length=1024)]


class Component(Shape):
    complete: bool
    needs_attention: bool


class Components(Shape):
    files: Component
    journal: Component


class SavedReport(Shape):
    schema_version: Literal['cospace.test-delivery-audit/0.1', 'cospace.test-delivery-audit/0.2']
    generation: ReportGeneration | None = None
    test_only: Literal[True]
    requested_binding: Binding
    observed: Observation
    components: Components
    findings: Annotated[list[Finding], Field(max_length=400)]
    complete: bool
    needs_attention: bool
    validity: Literal['not_evaluated']
    proofs_verified: Literal[False]
    history_verified: Literal[False]
    authorized: Literal[False]
    robot_ready: Literal[False]
    repair_authorized: Literal[False]

    @model_validator(mode='after')
    def consistent(self):
        if (self.schema_version.endswith('/0.2')) != (self.generation is not None):
            raise ValueError('generation metadata required only for 0.2')
        matched = self.observed.file_binding == self.requested_binding == self.observed.journal_binding
        if self.observed.binding_match != matched or self.needs_attention != bool(self.findings):
            raise ValueError('inconsistent diagnostic flags')
        return self


class DeliveryReportError(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


class SavedDeliveryReader:
    MAX_BYTES = 2 * 1024 * 1024

    def __init__(self, path):
        # Configuration is operator owned; no client supplies a filesystem path.
        self.path = Path(path)

    def read(self, scene, release):
        try:
            path = safe_path(self.path)
            with path.open('rb') as stream:
                before = os.fstat(stream.fileno())
                if before.st_size > self.MAX_BYTES:
                    raise ValueError('report too large')
                raw = stream.read(self.MAX_BYTES + 1)
                after = os.fstat(stream.fileno())
            if len(raw) > self.MAX_BYTES or (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                raise ValueError('report changed or too large')
            document = read_json(raw)
            report = SavedReport.model_validate(document)
            validate_generation(document)
        except (OSError, ImportError, ValueError, ValidationError, RecursionError, KeyError, TypeError) as error:
            raise DeliveryReportError('delivery_report_unavailable') from error
        if (report.requested_binding.scene_id, report.requested_binding.release_id) != (scene, release):
            raise DeliveryReportError('delivery_report_target_mismatch')
        return {'schema_version': 'cospace.saved-delivery/0.1',
                'source': {'kind': 'saved_report', 'sha256': hashlib.sha256(raw).hexdigest(),
                           'bytes': len(raw), 'read_at': datetime.now(timezone.utc).isoformat(),
                           'observed_at': None},
                'report': report.model_dump()}
