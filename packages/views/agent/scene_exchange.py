"""Materialize exact component bytes for independent synthetic consumers."""
from packages.infrastructure.local_output import new_output_directory, write_member
from packages.spatial.scene_identity import canonical
from packages.views.agent.scene_subset import ROLES, validate_scene_subset


def write_exchange(package, expected_source, output, *, allowed_root=None):
    report = validate_scene_subset(package, expected_source)
    root = new_output_directory(output, allowed_root=allowed_root)
    for role in ROLES:
        write_member(root, role + '.json', canonical(package['payloads'][role]))
    # Written last: consumers require this marker and all exact component bytes.
    write_member(root, 'manifest.json', canonical({'profile': 'cospace.synthetic-subset-files/0.1', 'manifest': package['manifest']}))
    return report
