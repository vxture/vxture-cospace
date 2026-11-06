"""Validate configured sources without registering inputs or starting a service."""
import argparse
import json
from pathlib import Path
from packages.data.preview_source_config import load_sources


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config', type=Path, default=Path('deploy/config/preview-sources.json'))
    p.add_argument('--project-root', type=Path, default=Path.cwd())
    p.add_argument('--full-check', action='store_true')
    a = p.parse_args()
    try: _, report = load_sources(a.config, a.project_root, a.full_check)
    except (ValueError, OSError, KeyError, TypeError, IndexError) as exc:
        p.exit(2, f'source_config_refused: {exc}\n')
    report['loaded_at_startup'] = False
    print(json.dumps(report, ensure_ascii=True))


if __name__ == '__main__': main()
