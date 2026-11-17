"""Read verified scene evidence and fixed workspace rules for a diagnostic proposal."""
import hashlib
import json
from typing import Annotated

from pydantic import Field

from packages.ontology.ifc_mapping import Mapping, propose_structure_types
from packages.ontology.preview_versions import MAX_BYTES
from packages.spatial.scene_graph import Fixed
from packages.spatial.scene_identity import Digest
from packages.views.agent.ifc_structure_exchange import export_structure_snapshot


class TypeProposalRequest(Fixed):
    space_id: Annotated[str, Field(pattern=r'^space-[a-f0-9]{16}$')]
    catalog_sha256: Digest
    mapping: Mapping


def type_proposals(workspace, rules, query):
    raw = export_structure_snapshot(workspace, query.space_id, query.catalog_sha256)
    ref = query.mapping.ontology_ref
    # The workspace store controls shared/private visibility and revalidates sealed content.
    rules.read(ref.ontology_id, ref.version, ref.sha256)
    with (rules.path(ref.ontology_id, ref.version) / 'definition.json').open('rb') as stream:
        ontology_raw = stream.read(MAX_BYTES + 1)
    source = json.loads(raw)['source']
    return propose_structure_types(raw, expected_structure_sha256=hashlib.sha256(raw).hexdigest(),
                                   expected_source=source, ontology_raw=ontology_raw,
                                   mapping_document=query.mapping.model_dump())
