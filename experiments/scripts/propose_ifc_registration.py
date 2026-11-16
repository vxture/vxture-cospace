"""Generate hypotheses from sealed source geometry under an explicit numeric-unit assumption."""
import argparse
from html import escape
import json
from pathlib import Path

import numpy as np

from experiments.scripts.ifc_control_review import _read_sources, _sample, _triangles
from packages.construction.ifc_registration_proposal import registration_proposals
from packages.construction.rgbd_tracking import transform
from packages.spatial.scene_identity import content_digest


def overlay_html(report, source, cloud):
    moved = transform(source, np.asarray(report['candidates'][0]['ifc_to_cloud_numeric']))
    panels = []
    for a, b in ((0, 1), (0, 2), (1, 2)):
        all_points = np.concatenate((moved, cloud))[:, [a, b]]
        lo, hi = all_points.min(0), all_points.max(0)
        scale = min(1000 / max(hi[0] - lo[0], .001), 480 / max(hi[1] - lo[1], .001))
        groups = []
        for points, color in ((cloud, '#557eaa'), (moved, '#d8862e')):
            xy = (_sample(points, 6000)[:, [a, b]] - lo) * scale
            marks = ''.join(f'<circle cx="{x + 40:.2f}" cy="{520 - y:.2f}" r="1.2"/>' for x, y in xy)
            groups.append(f'<g fill="{color}" fill-opacity=".45">{marks}</g>')
        panels.append(f'<h2>{"XYZ"[a]} / {"XYZ"[b]} · 共同坐标与比例</h2>'
                      '<svg viewBox="0 0 1080 560" role="img" aria-label="配准候选叠加">'
                      + ''.join(groups) + '</svg>')
    return ('<!doctype html><html lang="zh-CN"><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>SG3 · 未核验配准候选</title><style>'
            'body{max-width:1200px;margin:32px auto;padding:0 24px;font:15px system-ui;color:#19324a;background:#f3f6fa}'
            'svg{width:100%;background:white;border:1px solid #d5e1ea;border-radius:12px}p{line-height:1.7;overflow-wrap:anywhere}'
            '</style><h1>未核验配准候选 · 不可作为正式变换</h1>'
            '<p>蓝色：点云样本；橙色：变换后的 IFC 三角形中心样本。三个视图各自使用两组数据的共同范围。'
            '假设点云数值单位等于 IFC 米；没有单位依据、独立控制点或现场一致性证明。最近邻残差不是测量精度。</p>'
            f'<p>IFC：{escape(report["source_catalog_sha256"])}<br>点云：{escape(report["cloud_sha256"])}</p>'
            + ''.join(panels) + '</html>')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ifc-root', type=Path, required=True)
    parser.add_argument('--cloud-root', type=Path, required=True)
    parser.add_argument('--ifc-sha256', required=True)
    parser.add_argument('--cloud-sha256', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--overlay', type=Path, help='New static HTML overlay of the first-ranked hypothesis')
    args = parser.parse_args()
    catalog, facts, cloud = _read_sources(args.ifc_root, args.cloud_root,
        expected_ifc_sha256=args.ifc_sha256, expected_cloud_sha256=args.cloud_sha256)
    triangles = _triangles(args.ifc_root, catalog)
    # Triangle centroids are only a bounded geometry proxy, not measured control points.
    source = np.mean(triangles, axis=1)
    target = _sample(cloud, 18000)
    report = registration_proposals(source, target)
    report.update(source_catalog_sha256=args.ifc_sha256, cloud_sha256=args.cloud_sha256,
                  ifc_frame_id=catalog['frame_id'], cloud_frame_id=facts['frame_id'],
                  samples={'method': 'triangle_centroids_and_ply_stride', 'source_sha256': content_digest(source.tolist()), 'target_sha256': content_digest(target.tolist())})
    with args.output.open('x', encoding='utf-8') as stream:
        stream.write(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    if args.overlay:
        with args.overlay.open('x', encoding='utf-8') as stream:
            stream.write(overlay_html(report, source, target))


if __name__ == '__main__':
    main()
