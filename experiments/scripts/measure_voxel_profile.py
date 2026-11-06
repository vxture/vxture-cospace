"""Generate a tiny F05 fixture and measure incremental Python allocations, not RSS."""
import json
import platform
import statistics
import sys
import time
import tracemalloc
from pathlib import Path

from packages.views.agent.voxel import VoxelSession
from packages.views.agent.voxel_sample import build_voxel_sample


if __name__ == '__main__':
    files,pin = build_voxel_sample()
    root = Path('examples/agent-voxel/synthetic')
    root.mkdir(parents=True,exist_ok=True)
    for name,raw in files.items():
        path = root / name
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes(raw)
    (root.parent / 'expected-source.json').write_text(json.dumps(pin,indent=2),encoding='utf-8')
    tracemalloc.start()
    started = time.perf_counter()
    session = VoxelSession(files,pin)
    load_ms = (time.perf_counter()-started)*1000
    _,peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    timings = []
    for _ in range(1000):
        started = time.perf_counter()
        session.query([1.5,.5,.5])
        timings.append((time.perf_counter()-started)*1000000)
    report = {
        'profile':'cospace.agent-voxel/0.1','data_kind':'synthetic',
        'python':sys.version,'platform':platform.platform(),'machine':platform.machine(),
        'conditions':'4-file tiny fixture; input bytes/pin allocated before timing; no payload filesystem IO or F04 validation in load interval; local Schema read is included; Python allocations exclude RSS and preallocated chunk bytes',
        'package_bytes':session.package_bytes,'loaded_chunk_bytes':session.loaded_chunk_bytes,
        'declared_full_grid_cells':100,'loaded_cells':75,'missing_chunk_cells':25,
        'load_ms':load_ms,'incremental_python_peak_bytes':peak,
        'warm_query_count':1000,'warm_query_median_us':statistics.median(timings),
        'warm_query_p95_us':sorted(timings)[949],
        'missing_chunk_query':session.query([5.5,5.5,.5]),'robot_ready':False,'authorized':False}
    output = Path('output/validation/voxel-profile-resources.json')
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))
