"""Build an offline comparison from pinned IFC and point cloud catalogs."""
import argparse
from html import escape
import json
from pathlib import Path

import numpy as np

from packages.data.ifc_workspace import load_mesh, read_json, sha, validate_catalog, validate_source
from packages.data.preview_pointcloud import read_cloud

MAX_POINTS = 18_000
MAX_TRIANGLES = 6_000
STRUCTURE = {'IfcWall', 'IfcDoor', 'IfcStair', 'IfcStairFlight', 'IfcSlab'}
WIDTH, HEIGHT = 575, 262


def _sample(array, limit):
    return array[::max(1, (len(array) + limit - 1) // limit)]


def _triangles(root, catalog):
    blocks = [load_mesh(root, p) for p in catalog['products']
              if p['ifc_type'] in STRUCTURE and p['geometry_status'] == 'extracted']
    if not blocks:
        raise ValueError('comparison_structure_mesh_missing')
    return _sample(np.concatenate([vertices[faces] for vertices, faces in blocks]), MAX_TRIANGLES)


def _panel(points, axes, title, x, y, *, mesh):
    a, b = axes
    coords = points[..., [a, b]]
    flattened = coords.reshape(-1, 2)
    lo, hi = flattened.min(axis=0), flattened.max(axis=0)
    span = np.maximum(hi-lo, .001)
    scale = min((WIDTH-36)/span[0], (HEIGHT-66)/span[1])
    p = (coords - (lo+hi)/2)*scale
    p[..., 0] += WIDTH/2
    p[..., 1] = HEIGHT/2 + 7 - p[..., 1]
    if mesh:
        path = ''.join(f'M{x1:.1f},{y1:.1f}L{x2:.1f},{y2:.1f}L{x3:.1f},{y3:.1f}Z'
                       for (x1,y1),(x2,y2),(x3,y3) in p)
        marks = f'<path d="{path}" fill="none" stroke="#136a83" stroke-opacity=".29" stroke-width=".7"/>'
    else:
        marks = ''.join(f'<circle cx="{px:.1f}" cy="{py:.1f}" r=".72"/>' for px,py in p)
        marks = f'<g fill="#265d8a" fill-opacity=".58">{marks}</g>'
    axis = 'XYZ'
    footer = f'{axis[a]} {lo[0]:.2f} 到 {hi[0]:.2f} · {axis[b]} {lo[1]:.2f} 到 {hi[1]:.2f} · 原坐标数值'
    return (f'<g transform="translate({x},{y})"><rect width="{WIDTH}" height="{HEIGHT}" rx="10" '
            f'fill="#f6f9fc" stroke="#d5e1ea"/>{marks}'
            f'<text x="14" y="23" font-size="15">{escape(title)}</text>'
            f'<text x="14" y="{HEIGHT-10}" font-size="12">{footer}</text></g>')


def _read_sources(ifc_root, cloud_root, *, expected_ifc_sha256, expected_cloud_sha256):
    raw, catalog = read_json(ifc_root / 'ifc.json', 8*1024*1024)
    if sha(raw) != expected_ifc_sha256:
        raise ValueError('comparison_ifc_digest')
    validate_catalog(catalog)
    validate_source(ifc_root, catalog)
    facts, points, _, _ = read_cloud(cloud_root)
    cloud_sha = facts['cloud_sha256']
    if cloud_sha != expected_cloud_sha256:
        raise ValueError('comparison_cloud_digest')
    return catalog, facts, points


def compare_sources(ifc_root, cloud_root, *, expected_ifc_sha256, expected_cloud_sha256):
    """Read sealed inputs; return SVG and an empty, explicitly unverified worksheet."""
    catalog, facts, points = _read_sources(
        ifc_root, cloud_root, expected_ifc_sha256=expected_ifc_sha256,
        expected_cloud_sha256=expected_cloud_sha256)
    triangles = _triangles(ifc_root, catalog)
    cloud = _sample(points, MAX_POINTS)
    columns = [('IFC 结构网格', triangles, 18, True), ('LAZ 派生点云', cloud, 610, False)]
    panels = [_panel(data, pair, f'{name} · {label}', x, 86+i*275, mesh=mesh)
              for i, (pair, label) in enumerate([((0,1), 'XY'), ((0,2), 'XZ'), ((1,2), 'YZ')])
              for name, data, x, mesh in columns]
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1204 930" '
           'font-family="system-ui, sans-serif" fill="#173149">'
           '<rect width="1204" height="930" fill="#fff"/>'
           '<text x="18" y="32" font-size="23" font-weight="600">IFC / 点云 · 对应点预检</text>'
           '<text x="18" y="60" font-size="14">原坐标独立投影，面板分别缩放。不是叠合结果，不能把画面位置当作对应点。</text>'
           + ''.join(panels) + '</svg>')
    return svg, {'profile': 'cospace.ifc-control-review/0.1', 'status': 'not_aligned',
                 'ifc': {'frame_id': catalog['frame_id'], 'artifact_sha256': expected_ifc_sha256,
                         'unit': 'm'},
                 'cloud': {'frame_id': facts['frame_id'], 'artifact_sha256': expected_cloud_sha256,
                           'unit': facts['unit']},
                 'cloud_unit_verified': False, 'alignment_verified': False, 'pairs': [],
                 'rendered': {'triangles': len(triangles), 'points': len(cloud)}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ifc-root', type=Path, required=True)
    parser.add_argument('--cloud-root', type=Path, required=True)
    parser.add_argument('--ifc-sha256', required=True)
    parser.add_argument('--cloud-sha256', required=True)
    parser.add_argument('--output-dir', type=Path, required=True, help='New output directory')
    args = parser.parse_args()
    svg, report = compare_sources(args.ifc_root, args.cloud_root,
                                  expected_ifc_sha256=args.ifc_sha256,
                                  expected_cloud_sha256=args.cloud_sha256)
    args.output_dir.mkdir(parents=True, exist_ok=False)
    (args.output_dir / 'ifc-cloud-comparison.svg').write_text(svg, encoding='utf-8')
    (args.output_dir / 'control-worksheet.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
