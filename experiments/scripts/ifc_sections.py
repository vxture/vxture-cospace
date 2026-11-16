"""Cut source IFC meshes at explicitly chosen source-Z heights for review."""
import argparse
from html import escape
import json
import math
from pathlib import Path

import numpy as np

from packages.data.ifc_workspace import load_mesh, read_json, sha, validate_catalog, validate_source

SECTION_TYPES = {'IfcWall', 'IfcDoor', 'IfcOpeningElement', 'IfcSlab', 'IfcStairFlight'}
MAX_SEGMENTS = 100_000
COLORS = {'IfcWall': '#6d8091', 'IfcDoor': '#176eaa', 'IfcOpeningElement': '#ae701c',
          'IfcStairFlight': '#4176a4', 'IfcSlab': '#9daab4'}


def triangle_section(triangle, z):
    """Return a segment, a point touch, coplanar face, or no intersection."""
    distances = triangle[:, 2] - z
    on = distances == 0
    if on.all():
        return 'coplanar', None
    points = [triangle[i].tolist() for i in range(3) if on[i]]
    for i, j in ((0, 1), (1, 2), (2, 0)):
        a, b = distances[i], distances[j]
        if a * b < 0:
            point = triangle[i] + (a / (a - b)) * (triangle[j] - triangle[i])
            point[2] = z
            points.append(point.tolist())
    points = list({tuple(point): point for point in points}.values())
    if len(points) == 2 and points[0] != points[1]:
        return 'segment', points
    return ('touch' if points else 'none'), None


def cut_sections(root, *, expected_catalog_sha256, heights):
    if (not 1 <= len(heights) <= 8 or len(set(heights)) != len(heights)
            or any(type(z) not in (float, int) or not math.isfinite(z) or abs(z) > 1_000_000 for z in heights)):
        raise ValueError('ifc_section_heights')
    raw, catalog = read_json(root / 'ifc.json', 8 * 1024 * 1024)
    if sha(raw) != expected_catalog_sha256:
        raise ValueError('ifc_section_catalog_digest')
    validate_catalog(catalog)
    validate_source(root, catalog)
    sections = [dict(z_m=z, segments=[], coplanar_triangles=0, point_touches=0) for z in heights]
    missing = []
    for product in catalog['products']:
        if product['ifc_type'] not in SECTION_TYPES:
            continue
        if product['geometry_status'] != 'extracted':
            missing.append(product['global_id'])
            continue
        vertices, faces = load_mesh(root, product)
        triangles = vertices[faces]
        lower, upper = triangles[:, :, 2].min(1), triangles[:, :, 2].max(1)
        for section in sections:
            z = section['z_m']
            for index in np.flatnonzero((lower <= z) & (upper >= z)):
                kind, points = triangle_section(triangles[index], z)
                if kind == 'segment':
                    if len(section['segments']) >= MAX_SEGMENTS:
                        raise ValueError('ifc_section_segment_budget')
                    section['segments'].append(dict(
                        source_entity_id=product['global_id'], ifc_type=product['ifc_type'],
                        triangle_index=int(index), points_m=points))
                elif kind == 'coplanar':
                    section['coplanar_triangles'] += 1
                elif kind == 'touch':
                    section['point_touches'] += 1
    return dict(profile='cospace.ifc-sections/0.1', source_catalog_sha256=expected_catalog_sha256,
                frame_id=catalog['frame_id'], unit='m', plane_definition='source_z_constant',
                sections=sections, missing_geometry_ids=missing, assessment='unverified',
                alignment_verified=False, confirmed_spaces=[],
                limitations=['design_mesh_only', 'source_z_not_verified_gravity', 'selected_ifc_classes_only',
                             'coplanar_faces_and_point_touches_not_rendered',
                             'no_polygon_stitching_or_space_inference', 'no_ontology_binding'])


def _svg(section):
    rows = section['segments']
    if not rows:
        return '<p>此切面无截线。</p>'
    points = np.asarray([row['points_m'] for row in rows])[..., :2]
    lo, hi = points.reshape(-1, 2).min(0), points.reshape(-1, 2).max(0)
    scale = min(1100 / max(hi[0] - lo[0], .001), 650 / max(hi[1] - lo[1], .001))

    def screen(point):
        return (50 + (point[0] - lo[0]) * scale, 700 - (point[1] - lo[1]) * scale)

    lines = []
    for row in rows:
        (x, y), (u, v) = map(screen, row['points_m'])
        title = f'{row["ifc_type"]} · {row["source_entity_id"]} · triangle {row["triangle_index"]}'
        lines.append(f'<path d="M{x:.2f},{y:.2f}L{u:.2f},{v:.2f}" fill="none" '
                     f'stroke="{COLORS[row["ifc_type"]]}" stroke-width="1.2">'
                     f'<title>{escape(title)}</title></path>')
    # A physical 1 m scale in the same source units as the segment coordinates.
    ruler = (f'<path d="M50,730h{scale:.3f}" stroke="#19324a" stroke-width="2"/>'
             '<text x="50" y="755">1 m · IFC 声明单位</text>') if scale <= 1100 else ''
    return ('<svg viewBox="0 0 1200 780" role="img" aria-label="IFC 原坐标剖面">'
            '<rect width="1200" height="780" fill="#f3f7fb"/>'
            + ''.join(lines) + ruler + '</svg>')


def section_html(report):
    panels = []
    for section in report['sections']:
        panels.append(f'<section><h2>Z = {section["z_m"]:.3f} m</h2>'
                      f'<p>{len(section["segments"])} 条截线 · '
                      f'{section["coplanar_triangles"]} 个共面三角形、{section["point_touches"]} 个点接触未画出</p>'
                      + _svg(section) + '</section>')
    return ('<!doctype html><html lang="zh-CN"><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>SG3 · IFC 空间剖面</title><style>'
            'body{max-width:1472px;margin:24px auto;padding:0 24px;font:15px system-ui;color:#19324a;background:#f3f6fa}'
            'section{background:white;padding:20px;margin:20px 0;border:1px solid #d5e1ea;border-radius:12px}'
            'svg{width:100%;display:block}h2{font-size:20px}.source{overflow-wrap:anywhere}'
            '</style><h1>SG3 · IFC 空间剖面</h1>'
            '<p>灰：墙 / 楼板，蓝：门 / 楼梯段，棕：开口。悬停截线可查实体与原网格三角形索引。</p>'
            '<p>按指定原坐标 Z 高度求交；不是已确认平面图，不自动推断房间、楼道或连接。投影中重合的截线保留。</p>'
            f'<p class="source">坐标系：{escape(report["frame_id"])}<br>目录摘要：{escape(report["source_catalog_sha256"])}</p>'
            + ''.join(panels) + '</html>')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ifc-root', type=Path, required=True)
    parser.add_argument('--ifc-sha256', required=True)
    parser.add_argument('--z', type=float, action='append', required=True)
    parser.add_argument('--output-dir', type=Path, required=True, help='New output directory')
    args = parser.parse_args()
    result = cut_sections(args.ifc_root, expected_catalog_sha256=args.ifc_sha256, heights=args.z)
    args.output_dir.mkdir(parents=True, exist_ok=False)
    (args.output_dir / 'sections.json').write_text(
        json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    (args.output_dir / 'index.html').write_text(section_html(result), encoding='utf-8')


if __name__ == '__main__':
    main()
