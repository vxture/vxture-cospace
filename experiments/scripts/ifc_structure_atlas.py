"""Render a read-only atlas of source IFC doors, openings and stair components."""
import argparse
from html import escape
from pathlib import Path

import numpy as np

from packages.construction.ifc_structure_review import structure_review
from packages.data.ifc_workspace import load_mesh, read_json, sha

COLORS = {'IfcDoor': '#176eaa', 'IfcOpeningElement': '#ab6517',
          'IfcWall': '#9caebc', 'IfcStairFlight': '#176eaa', 'IfcSlab': '#8196a6'}
MAX_TASK_FACES = 40_000


def _view(blocks, axes, title):
    arrays = [vertices[faces][..., list(axes)] for _, vertices, faces in blocks]
    flat = np.concatenate([p.reshape(-1, 2) for p in arrays])
    lo, hi = flat.min(0), flat.max(0)
    span = np.maximum(hi - lo, .001)
    scale = min(520 / span[0], 265 / span[1])
    marks = []
    for (kind, _, _), coords in zip(blocks, arrays):
        xy = (coords - (lo + hi) / 2) * scale
        xy[..., 0] += 290
        xy[..., 1] = 175 - xy[..., 1]
        path = ''.join(f'M{a:.2f},{b:.2f}L{c:.2f},{d:.2f}L{e:.2f},{f:.2f}Z'
                       for (a, b), (c, d), (e, f) in xy)
        marks.append(f'<path d="{path}" stroke="{COLORS.get(kind, "#8f9ba7")}" '
                     'fill="none" stroke-opacity=".65" stroke-width=".8"/>')
    axis = 'XYZ'
    footer = f'{axis[axes[0]]} {lo[0]:.3f}…{hi[0]:.3f} / {axis[axes[1]]} {lo[1]:.3f}…{hi[1]:.3f} m'
    return (f'<svg viewBox="0 0 580 350" role="img" aria-label="{escape(title)}">'
            '<rect width="580" height="350" rx="8" fill="#f3f7fb"/>'
            + ''.join(marks) + f'<text x="16" y="25">{escape(title)}</text>'
            f'<text x="16" y="332" font-size="12">{footer}</text></svg>')


def build_atlas(root, *, expected_catalog_sha256):
    review = structure_review(root, expected_catalog_sha256=expected_catalog_sha256)
    raw, catalog = read_json(root / 'ifc.json', 8 * 1024 * 1024)
    if sha(raw) != expected_catalog_sha256:
        raise ValueError('structure_atlas_catalog_changed')
    products = {p['global_id']: p for p in catalog['products']}
    sections = []
    for i, task in enumerate(review['tasks'], 1):
        rows = [task['source'], *task['related_geometry']]
        blocks, count = [], 0
        # Context first, then opening and focal object, all in one common scale.
        ordered = sorted(rows, key=lambda row: row['ifc_type'] in ('IfcDoor', 'IfcStairFlight'))
        for row in ordered:
            if row['geometry_status'] != 'extracted':
                continue
            product = products[row['global_id']]
            count += product['mesh']['triangles']
            if count > MAX_TASK_FACES:
                raise ValueError('structure_atlas_task_budget')
            vertices, faces = load_mesh(root, product)
            blocks.append((row['ifc_type'], vertices, faces))
        identity = task['source_entity_id']
        title = f'{i:02} · {task["source"]["name"] or task["source"]["ifc_type"]}'
        views = ''.join(_view(blocks, axes, label) for axes, label in
                        [((0, 1), 'XY 俯视'), ((0, 2), 'XZ 侧视'), ((1, 2), 'YZ 侧视')]) if blocks else '<p>没有可显示网格。</p>'
        relations = ''.join(f'<li>{escape(r["kind"])}：{escape(r["source_id"])} → {escape(r["target_id"])}</li>'
                            for r in task['source_relations'])
        sections.append(f'<section id="task-{i}"><h2>{escape(title)}</h2>'
                        f'<p class="id">{escape(identity)} · 待复核</p><div class="views">{views}</div>'
                        '<details><summary>原始关系与构件</summary><ul>' + relations + '</ul><ul>'
                        + ''.join(f'<li>{escape(r["ifc_type"])} · {escape(r["global_id"])} · {escape(r["geometry_status"])}</li>'
                                  for r in rows) + '</ul></details></section>')
    nav = ''.join(f'<a href="#task-{i}">{i:02}</a>' for i in range(1, len(sections) + 1))
    return ('<!doctype html><html lang="zh-CN"><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>SG3 · 门与楼梯结构图册</title><style>'
            '*{box-sizing:border-box}body{margin:24px auto;padding:0 24px;max-width:1472px;background:#f3f6fa;color:#19324a;font:15px system-ui}'
            'section{margin:20px 0;background:#fff;border:1px solid #d5e1ea;border-radius:12px;padding:20px}'
            'h1{font-size:28px}h2{font-size:18px}.views{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}'
            'svg{width:100%;display:block}.id,li{overflow-wrap:anywhere}.id{color:#586e82}details{margin-top:12px}'
            'nav{display:flex;gap:8px;flex-wrap:wrap}nav a{padding:8px;background:#fff;border-radius:6px;color:#176eaa}'
            '@media(max-width:800px){.views{grid-template-columns:1fr}}'
            '</style><h1>SG3 · 门与楼梯结构图册</h1>'
            '<p>原 IFC 坐标 · 蓝色：门 / 楼梯段，棕色：开口，灰色：墙 / 平台。</p>'
            '<p>同一视图中的构件共用比例；各视图分别缩放。线框投影会重叠，不能据此确认空间边界、净开口或现场连接。</p>'
            f'<p class="id">目录 SHA-256：{escape(expected_catalog_sha256)}<br>坐标系：{escape(review["frame_id"])}</p>'
            '<nav aria-label="构件索引">' + nav + '</nav>' + ''.join(sections) + '</html>')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ifc-root', type=Path, required=True)
    parser.add_argument('--ifc-sha256', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    html = build_atlas(args.ifc_root, expected_catalog_sha256=args.ifc_sha256)
    with args.output.open('x', encoding='utf-8') as stream:
        stream.write(html)


if __name__ == '__main__':
    main()
