"""CoSpace permissions under a verified Vxture workspace; owner is scope bounded.

Rules are consumed by the explicit authorized-workbench assembly. Loading this
module alone never enables authentication in the separate engineering preview.
"""
from pydantic import BaseModel, ConfigDict, Field, model_validator
from packages.infrastructure.platform_identity import PlatformPrincipal

CAPABILITIES = frozenset(('space.preview', 'space.query', 'space.export', 'data.manage',
                         'build.run', 'association.edit', 'publication.manage', 'space.manage'))
ROLE_CAPABILITIES = {
    'viewer': frozenset(('space.preview', 'space.query')),
    'engineer': frozenset(('space.preview', 'space.query', 'space.export', 'data.manage', 'build.run', 'association.edit')),
    'manager': CAPABILITIES,
}


class Binding(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, frozen=True)
    issuer: str = Field(min_length=1, max_length=2048)
    space_id: str = Field(pattern=r'^space-[a-f0-9]{16}$')
    org_id: str = Field(min_length=1, max_length=160)
    workspace_id: str = Field(min_length=1, max_length=160)


class Grant(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, frozen=True)
    issuer: str = Field(min_length=1, max_length=2048)
    subject: str = Field(pattern=r'^usr_[A-Za-z0-9_-]{1,150}$')
    space_id: str = Field(pattern=r'^space-[a-f0-9]{16}$')
    role: str = Field(pattern=r'^(viewer|engineer|manager)$')


class SpaceAccessPolicy(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, frozen=True)
    profile: str = Field(default='cospace.space-access-policy/0.1', pattern=r'^cospace\.space-access-policy/0\.1$')
    bindings: list[Binding] = Field(max_length=10_000)
    grants: list[Grant] = Field(max_length=100_000)

    @model_validator(mode='after')
    def references(self):
        spaces = [v.space_id for v in self.bindings]
        keys = [(v.issuer, v.subject, v.space_id) for v in self.grants]
        if len(set(spaces)) != len(spaces) or len(set(keys)) != len(keys):
            raise ValueError('duplicate_binding_or_member_grant')
        if any(v.space_id not in spaces for v in self.grants):
            raise ValueError('grant_requires_bound_space')
        return self

    def capabilities(self, principal: PlatformPrincipal, space_id):
        binding = next((b for b in self.bindings if b.space_id == space_id), None)
        if binding is None or (binding.issuer, binding.org_id, binding.workspace_id) != (principal.issuer, principal.org_id, principal.workspace_id):
            return frozenset()
        # Platform 080-rp §2.6: workspace owner has product owner baseline,
        # limited to explicitly bound spaces in the token's active workspace.
        if principal.workspace_owner:
            return CAPABILITIES
        grant = next((g for g in self.grants if (g.issuer, g.subject, g.space_id) ==
                      (principal.issuer, principal.subject, space_id)), None)
        return ROLE_CAPABILITIES[grant.role] if grant else frozenset()

    def require(self, principal, space_id, capability):
        if capability not in CAPABILITIES:
            raise ValueError('unknown_space_capability')
        if capability not in self.capabilities(principal, space_id):
            raise PermissionError('space_access_denied')

    def visible(self, principal, spaces):
        return [s for s in spaces if 'space.preview' in self.capabilities(principal, s['id'])]
