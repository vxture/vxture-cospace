"""Write a synthetic change and content-addressed candidate, never publish it."""
from pathlib import Path

from packages.spatial.change_sample import build_change_sample
from packages.spatial.changes import build_candidate, canonical

if __name__=='__main__':
    source,change,resources=build_change_sample()
    result=build_candidate(source,change,resources,now='2026-10-28T00:30:00Z')
    root=Path('examples/spatial-change')
    root.mkdir(parents=True,exist_ok=True)
    (root/'change.json').write_bytes(canonical(change))
    for path,raw in resources.items():
        target=root/'input'/path
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(raw)
    (root/'candidate.json').write_bytes(canonical(result['candidate']))
    for path,raw in result['blobs'].items():
        target=root/'candidate'/path
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(raw)
    print({'candidate_id':result['candidate']['candidate_id'],'blobs':len(result['blobs']),
           'publication_status':result['candidate']['publication_status'],'real_release_ready':False})
