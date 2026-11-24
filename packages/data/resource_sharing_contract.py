"""Explicit version grants and reference records, within a verified workspace."""
from datetime import datetime
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator
from packages.lifecycle.workspace_projects import Change, ProjectId, SceneId

ResourceId = Annotated[str, Field(pattern=r'^resource-[a-f0-9]{32}$')]
VersionId = Annotated[str, Field(pattern=r'^[a-f0-9]{64}$')]
GrantId = Annotated[str, Field(pattern=r'^grant-[a-f0-9]{32}$')]
UseId = Annotated[str, Field(pattern=r'^use-[a-f0-9]{32}$')]


class GrantVersion(Change):
    action: Literal['grant']
    resource_id: ResourceId
    version_id: VersionId
    expected_resource_revision: int = Field(ge=1)
    target_kind: Literal['project', 'workspace'] = 'project'
    target_project_id: ProjectId | None = None
    allow_download: bool = False
    expires_at: datetime | None = None

    @model_validator(mode='after')
    def explicit_target(self):
        if (self.target_kind == 'project') != bool(self.target_project_id):
            raise ValueError('grant_target_invalid')
        if self.expires_at is not None and self.expires_at.tzinfo is None:
            raise ValueError('grant_expiry_timezone_required')
        return self


class RevokeVersion(Change):
    action: Literal['revoke']
    grant_id: GrantId


class ReferenceVersion(Change):
    action: Literal['use']
    grant_id: GrantId
    expected_grant_revision: int = Field(ge=1)
    project_id: ProjectId
    space_id: SceneId | None = None
    purpose: str = Field(min_length=1, max_length=200)
    use_mode: Literal['reference', 'spatial_application'] = 'reference'

    @model_validator(mode='after')
    def purpose_required(self):
        if not self.purpose.strip():
            raise ValueError('reference_purpose_required')
        return self


class UnlinkVersion(Change):
    action: Literal['unlink']
    use_id: UseId


class UpgradeVersion(Change):
    action: Literal['upgrade']
    use_id: UseId
    grant_id: GrantId
    expected_grant_revision: int = Field(ge=1)
    expected_version: VersionId


SharingChange = TypeAdapter(Annotated[GrantVersion | RevokeVersion | ReferenceVersion | UnlinkVersion | UpgradeVersion,
                                     Field(discriminator='action')])


class SharingQuery(BaseModel):
    model_config = ConfigDict(extra='forbid')
    view: Literal['available', 'grants', 'uses'] = 'available'
    project_id: ProjectId | None = None
    resource_id: ResourceId | None = None
    search: str = Field(default='', max_length=100)
    offset: int = Field(default=0, ge=0, le=10000)
    limit: int = Field(default=20, ge=1, le=100)

    @model_validator(mode='after')
    def explicit_scope(self):
        if self.view=='grants':
            if not self.resource_id or self.project_id:
                raise ValueError('grant_resource_scope_required')
        elif not self.project_id:
            raise ValueError('reference_project_scope_required')
        return self


class SharedDownload(BaseModel):
    model_config = ConfigDict(extra='forbid')
    grant_id: GrantId
    project_id: ProjectId
    grant_revision: int = Field(ge=1)


class StoredGrant(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    id: GrantId
    resource_id: ResourceId
    version_id: VersionId
    revision: int = Field(ge=1)
    target_kind: Literal['project', 'workspace']
    target_project_id: ProjectId | None
    allow_download: bool
    expires_at: str | None
    status: Literal['active', 'revoked']
    updated_at: str

    @model_validator(mode='after')
    def valid_times_and_target(self):
        if (self.target_kind == 'project') != bool(self.target_project_id):
            raise ValueError('grant_target_invalid')
        for value in (self.updated_at, self.expires_at):
            if value is not None and datetime.fromisoformat(value).tzinfo is None:
                raise ValueError('timestamp_timezone_required')
        return self


class StoredUse(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    id: UseId
    resource_id: ResourceId
    version_id: VersionId
    revision: int = Field(ge=1)
    grant_id: GrantId
    grant_revision: int = Field(ge=1)
    project_id: ProjectId
    space_id: SceneId | None
    purpose: str = Field(min_length=1, max_length=200)
    status: Literal['active', 'unlinked']
    updated_at: str
    use_mode: Literal['reference']
    coordinate_status: Literal['not_applied']


class SharedSourceVersion(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    version_id: VersionId
    reference_kind: Literal['source_metadata']
    created_at: str | None
    format: str | None
    bytes: int | None = Field(ge=0)


class StoredSnapshot(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    label: str = Field(min_length=1)
    kind: Literal['input', 'attachment', 'candidate', 'human_view', 'agent_view', 'resource_file']
    resource_type: Literal['acquisition', 'reference', 'result']
    source_version: SharedSourceVersion
    is_base: bool
    payload_available: bool
    filename: str | None = None
    bytes: int | None = Field(default=None, gt=0, le=32*1024*1024)
    sha256: VersionId | None = None

    @model_validator(mode='after')
    def payload_metadata(self):
        if self.payload_available and (self.kind not in ('attachment', 'resource_file') or not self.filename or self.bytes is None or self.sha256 is None):
            raise ValueError('snapshot_payload_invalid')
        if self.filename and (any(ord(c)<32 or ord(c)==127 for c in self.filename) or any(c in self.filename for c in '/\\:<>"|?*')):
            raise ValueError('snapshot_filename_invalid')
        return self
