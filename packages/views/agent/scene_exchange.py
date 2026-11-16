"""Materialize exact component bytes for independent synthetic consumers."""
from pathlib import Path

from packages.spatial.scene_identity import canonical
from packages.views.agent.scene_subset import ROLES, validate_scene_subset


def write_exchange(package, expected_source, output):
    report = validate_scene_subset(package, expected_source)
    root = Path(output)
    root.mkdir(parents=True, exist_ok=False)
    for role in ROLES:
        (root / (role + '.json')).write_bytes(canonical(package['payloads'][role]))
    # Written last: consumers require this marker and all exact component bytes.
    (root / 'manifest.json').write_bytes(canonical(dict(
        profile='cospace.synthetic-subset-files/0.1', manifest=package['manifest'])))
    return report
