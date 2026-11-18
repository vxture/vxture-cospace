"""Run inside the IFC worker image, on an isolated synthetic runtime volume."""
import sys
from pathlib import Path

from packages.data.ifc_workspace import IfcWorkspace
from packages.data.preview_inputs import PreviewInputs
from packages.data.scene_attachments import SceneAttachments
from packages.lifecycle.preview_spaces import PreviewSpaces
from packages.lifecycle.scene_ifc_versions import SceneIfcVersions
from packages.service.ifc_reference_http import preview_version

runtime = Path('/data/runtime')
directory = PreviewSpaces(runtime/'preview-directory')
attachments = SceneAttachments(PreviewInputs(runtime/'preview-inputs', directory))
versions = SceneIfcVersions(attachments)

if sys.argv[1] == 'queue':
    project = directory.create('project', 'Container fixture')
    space = directory.create('space', 'IFC smoke', project['id'])['id']
    source = Path('/tmp/native-smoke.ifc')
    source.write_bytes(sys.stdin.buffer.read())
    identity = attachments.register(source, space, source.name, 'synthetic')['attachment']['id']
    versions.enqueue(space, identity, 'synthetic')
else:
    space = directory.list('space')[0]['id']
    state = versions.listing(space)
    task = next(iter(state['tasks'].values()))
    if task['state'] == 'failed':
        raise ValueError(task['error'])
    if task['state'] != 'ready':
        sys.exit(3)
    workspace = IfcWorkspace(directory, None, versions=versions)
    assert not workspace.directory_view(space)['configured']
    preview = preview_version(versions, space, task['id'])
    assert preview['role_counts']['wall'] > 0 and preview['assessment'] == 'unverified'
    binding = versions.activate(space, task['id'], expected_revision=0, actor='synthetic')
    assert workspace.directory_view(space)['catalog_sha256'] == binding.catalog_sha256
    print(preview['role_counts'], preview['entity_count'])
