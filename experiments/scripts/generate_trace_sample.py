"""Write reproducible F06c synthetic trace artifacts from repository root."""
from pathlib import Path
from packages.lifecycle.trace_sample import trace_sample_files

if __name__ == '__main__':
    files = trace_sample_files()
    root = Path('examples/trace-events')
    for name, raw in files.items():
        target = root/name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    print({'files':len(files),'output':str(root)})
