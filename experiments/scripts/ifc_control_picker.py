"""Export a standalone, offline SG3 control review page."""
import argparse
import json
from pathlib import Path

from experiments.scripts.ifc_control_review import STRUCTURE, _read_sources, _sample
from packages.data.ifc_workspace import load_mesh

POINT_BUDGET = 45_000
FACE_BUDGET = 40_000


def picker_data(ifc_root, cloud_root, *, expected_ifc_sha256, expected_cloud_sha256):
    catalog, facts, points = _read_sources(
        ifc_root, cloud_root, expected_ifc_sha256=expected_ifc_sha256,
        expected_cloud_sha256=expected_cloud_sha256)
    vertices, faces, elements = [], [], []
    for product in catalog['products']:
        if product['ifc_type'] not in STRUCTURE or product['geometry_status'] != 'extracted':
            continue
        v, f = load_mesh(ifc_root, product)
        if len(faces) + len(f) > FACE_BUDGET or len(vertices) + len(v) > 3 * FACE_BUDGET:
            raise ValueError('picker_structure_face_budget')
        elements.append({'start': len(vertices), 'global_id': product['global_id'],
                         'ifc_type': product['ifc_type']})
        faces.extend((f + len(vertices)).tolist())
        vertices.extend(v.tolist())
    if not faces:
        raise ValueError('comparison_structure_mesh_missing')
    stride = max(1, (len(points) + POINT_BUDGET - 1) // POINT_BUDGET)
    return {
        'worksheet': {
            'profile': 'cospace.ifc-control-review/0.1', 'status': 'not_aligned',
            'ifc': {'frame_id': catalog['frame_id'], 'artifact_sha256': expected_ifc_sha256, 'unit': 'm'},
            'cloud': {'frame_id': facts['frame_id'], 'artifact_sha256': expected_cloud_sha256,
                      'unit': facts['unit']},
            'cloud_unit_verified': False, 'alignment_verified': False, 'pairs': [],
        },
        'ifc': {'vertices': vertices, 'faces': faces, 'elements': elements},
        'cloud': {'vertices': _sample(points, POINT_BUDGET).tolist(), 'stride': stride,
                  'total': len(points)},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ifc-root', type=Path, required=True)
    parser.add_argument('--cloud-root', type=Path, required=True)
    parser.add_argument('--ifc-sha256', required=True)
    parser.add_argument('--cloud-sha256', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    data = picker_data(args.ifc_root, args.cloud_root,
                       expected_ifc_sha256=args.ifc_sha256, expected_cloud_sha256=args.cloud_sha256)
    # Prevent source metadata from terminating the inert JSON script element.
    payload = json.dumps(data, separators=(',', ':'), allow_nan=False).replace('<', '\\u003c')
    template = Path(__file__).with_suffix('.html').read_text(encoding='utf-8')
    with args.output.open('x', encoding='utf-8') as stream:
        stream.write(template.replace('__PICKER_DATA__', payload, 1))


if __name__ == '__main__':
    main()
