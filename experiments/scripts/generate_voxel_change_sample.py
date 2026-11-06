"""Generate F06b2 candidates and before/after inspection, never an active runtime package."""
from pathlib import Path

from packages.spatial.changes import canonical
from packages.views.agent.voxel import VoxelSession
from packages.views.agent.voxel_changes import VoxelCandidatePreview, build_voxel_candidate
from packages.views.agent.voxel_change_sample import build_voxel_change_sample

if __name__=='__main__':
    sample=build_voxel_change_sample()
    result=build_voxel_candidate(*sample)
    preview=VoxelCandidatePreview(*sample,result)
    original=VoxelSession(sample[0],sample[1])
    root=Path('examples/voxel-change')
    root.mkdir(parents=True,exist_ok=True)
    (root/'change.json').write_bytes(canonical(sample[2]))
    for name,raw in sample[3].items():
        target=root/'input'/name
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(raw)
    for name,raw in result['files'].items():
        target=root/'candidate'/name
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(raw)
    report={k:v for k,v in result.items() if k not in ('files','evidence')}
    report['queries']=[{'point':point,'before':original.query(point),'after':preview.query(point)}
                       for point in ([5.5,5.5,.5],[.5,.5,.5],[5.5,.5,.5],[.5,5.5,.5])]
    (root/'inspection.json').write_bytes(canonical(report))
    print({'changed_chunks':result['changed_chunk_count'],'unchanged_chunks':result['unchanged_chunks'],
           'candidate_manifest_sha256':result['candidate_manifest_sha256'],'publication_status':result['publication_status']})
