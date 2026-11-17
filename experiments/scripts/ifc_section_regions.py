"""Propose enclosed raster voids from pinned IFC sections at explicit resolutions."""
import argparse
from html import escape
import json
from pathlib import Path

from experiments.scripts.ifc_sections import cut_sections
from packages.construction.section_regions import enclosed_section_regions
from packages.spatial.scene_identity import content_digest


def propose_regions(root, *, expected_catalog_sha256, heights, resolutions, minimum_area=1.):
    if not 1 <= len(resolutions) <= 3 or len(set(resolutions)) != len(resolutions):
        raise ValueError('section_region_resolution_count')
    sections = cut_sections(root, expected_catalog_sha256=expected_catalog_sha256, heights=heights)
    trials = [enclosed_section_regions(section, resolution=resolution, minimum_area=minimum_area)
              for section in sections['sections'] for resolution in resolutions]
    return dict(profile='cospace.ifc-section-region-candidates/0.1',
                source_catalog_sha256=expected_catalog_sha256, source_sections_sha256=content_digest(sections),
                frame_id=sections['frame_id'], unit='m', algorithm='supercover_8_connected_voids/0.1',
                sections=sections['sections'], trials=trials, missing_geometry_ids=sections['missing_geometry_ids'],
                assessment='unverified', alignment_verified=False, ontology_bound=False,
                real_release_ready=False, confirmed_spaces=[], confirmed_connections=[],
                limitations=['ifc_design_sections_only', 'source_z_not_verified_gravity',
                             'no_gap_repair_but_raster_can_close_subcell_gaps', 'only_ifcwall_sections_are_barriers',
                             'voids_can_be_wall_interior_or_courtyard', 'no_room_or_corridor_classification',
                             'no_height_extent_or_level_assignment', 'no_automatic_annotation_adoption'])


def _trial_svg(trial, section):
    if trial['origin_xy_m'] is None:
        return '<p>无截线。</p>'
    rows, cols = trial['shape_rows_columns']
    resolution = trial['resolution_m']
    ox, oy = trial['origin_xy_m']
    paths = []
    for candidate in trial['candidates']:
        commands = [f'M{a},{r}h{b-a}v1h{a-b}z' for r, a, b in candidate['runs']]
        title = f'{candidate["id"]} · 栅格面积 {candidate["raster_area_m2"]:.2f} m² · {len(candidate["source_segment_indices"])} 条邻接截线'
        paths.append(f'<path d="{"".join(commands)}" fill="#bfdbfe" fill-opacity=".7"><title>{escape(title)}</title></path>')
    for segment in section['segments']:
        a, b = segment['points_m']
        command = f'M{(a[0]-ox)/resolution:.5f},{(a[1]-oy)/resolution:.5f}L{(b[0]-ox)/resolution:.5f},{(b[1]-oy)/resolution:.5f}'
        title = f'{segment["ifc_type"]} · {segment["source_entity_id"]} · triangle {segment["triangle_index"]}'
        opacity = '1' if segment['ifc_type'] == 'IfcWall' else '.25'
        paths.append(f'<path d="{command}" fill="none" stroke="#475569" stroke-opacity="{opacity}" stroke-width=".5"><title>{escape(title)}</title></path>')
    return (f'<svg viewBox="0 0 {cols} {rows}" role="img" aria-label="闭合栅格空隙候选">'
            f'<g transform="translate(0,{rows}) scale(1,-1)">{"".join(paths)}</g></svg>')


def report_html(report):
    sections = {row['z_m']: row for row in report['sections']}
    panels = []
    for trial in report['trials']:
        panels.append(f'<section><h2>Z {trial["z_m"]:g} m · 分辨率 {trial["resolution_m"]:g} m</h2>'
                      f'<p>{len(trial["candidates"])} 个闭合空隙候选 · 不是房间或楼道判定</p>'
                      + _trial_svg(trial, sections[trial['z_m']]) + '</section>')
    return ('<!doctype html><html lang="zh-CN"><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>SG3 · 闭合区域候选</title><style>'
            'body{max-width:1472px;margin:24px auto;padding:0 24px;font:15px system-ui;color:#19324a;background:#f3f6fa}'
            'section{background:white;padding:20px;margin:20px 0;border:1px solid #d5e1ea;border-radius:12px}'
            'svg{width:100%;max-height:650px;display:block}h2{font-size:20px}code{overflow-wrap:anywhere}'
            '</style><h1>SG3 · 闭合区域候选</h1>'
            '<p>浅蓝：栅格闭合空隙；深灰：墙截线，浅灰：其他参照。仅墙截线作屏障，不用门扇或虚拟开口封闭空间。</p>'
            '<p>网格会封住较小缝隙，墙内空腔和天井也可能被选中。</p>'
            '<p>比较各分辨率的数量与形状；一致不代表真实空间。没有楼层、高度、本体或连接采用。</p>'
            f'<p>固定目录：<code>{escape(report["source_catalog_sha256"])}</code></p>'
            + ''.join(panels) + '</html>')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ifc-root', type=Path, required=True)
    parser.add_argument('--ifc-sha256', required=True)
    parser.add_argument('--z', type=float, action='append', required=True)
    parser.add_argument('--resolution', type=float, action='append', required=True)
    parser.add_argument('--minimum-area', type=float, default=1.)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    report = propose_regions(args.ifc_root, expected_catalog_sha256=args.ifc_sha256, heights=args.z,
                             resolutions=args.resolution, minimum_area=args.minimum_area)
    raw = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)
    if len(raw.encode('utf-8')) > 32 * 1024 * 1024:
        raise ValueError('section_region_report_budget')
    args.output_dir.mkdir(parents=True, exist_ok=False)
    (args.output_dir / 'regions.json').write_text(raw + '\n', encoding='utf-8')
    (args.output_dir / 'index.html').write_text(report_html(report), encoding='utf-8')


if __name__ == '__main__':
    main()
