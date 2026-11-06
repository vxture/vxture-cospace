"""Verify every full-resolution shard and generate a labelled sample overview."""
import argparse
import html
import json
from pathlib import Path

import numpy as np

from packages.data.scene_pointcloud_intake import digest
from packages.data.scene_pointcloud_verify import verify
from experiments.scripts.prepare_pointcloud_input import prepare


def overview_html(samples, total, unit_basis):
    data = [dict(name=s['name'], points=np.round(s['points'], 4).tolist(), colors=s['colors'].tolist()) for s in samples]
    encoded = json.dumps(data, ensure_ascii=False, separators=(',', ':')).replace('<', chr(92)+'u003c')
    template = Path('experiments/templates/scene-overview.html').read_text(encoding='utf-8')
    template = template.replace('__TOTAL_POINTS__', f'{total:,}').replace('__UNIT_BASIS__', html.escape(unit_basis))
    return template.replace('__SCENE_DATA__', encoded)


def generate(root, output, *, source_root=None, sample_limit=20_000):
    root = Path(root).resolve()
    output = Path(output).resolve()
    if output.exists() or root.is_relative_to(output):
        raise ValueError('exclusive_overview_output_required')
    report, samples = verify(root, source_root=source_root, sample_limit=sample_limit)
    scene = json.loads((root/'scene.json').read_bytes())
    output.mkdir(parents=True, exist_ok=False)
    for i, (sample, source, receipt) in enumerate(zip(samples, scene['sources'], report['sources'])):
        source_dir = output/f'source-{i:02d}'
        source_dir.mkdir()
        count = len(sample['points'])
        vertices = np.empty(count, dtype=[(n, '<f4') for n in ('x', 'y', 'z')]+[(n, 'u1') for n in ('red', 'green', 'blue')])
        for axis, name in enumerate(('x', 'y', 'z')):
            vertices[name] = sample['points'][:, axis]
        for axis, name in enumerate(('red', 'green', 'blue')):
            vertices[name] = sample['colors'][:, axis]
        header = ('ply\nformat binary_little_endian 1.0\nelement vertex '+str(count)+'\n'
                  'property float x\nproperty float y\nproperty float z\n'
                  'property uchar red\nproperty uchar green\nproperty uchar blue\nend_header\n').encode()
        cloud = source_dir/'overview.ply'
        cloud.write_bytes(header+vertices.tobytes())
        description = (f"工程概览抽样；{source['name']}；完整来源{source['points']}点；按源序号每"
                       f"{receipt['overview_stride']}点取1点，保留{count}点。共同原点{scene['origin']}；"
                       f"单位依据{scene['unit_basis']}，CRS与设备对齐未核验；不是全量构建模型。")
        prepare(cloud, source_dir/'snapshot', points=count, frame_id='anoeta_scene_local',
                axes=['source_x', 'source_y', 'source_z'], scope='scene_local',
                source_manifest=root/'scene.json', source_member_sha256=source['sha256'],
                description=description, kind='existing_pointcloud')
        # Source indices are explicit so the deterministic overview is auditable.
        np.save(source_dir/'overview-source-indices.npy', sample['source_indices'], allow_pickle=False)
    (output/'index.html').write_text(overview_html(samples, scene['total_points'], scene['unit_basis']), encoding='utf-8')
    report.update(overview_points=sum(len(s['points']) for s in samples),
                  overview_sampling='source ordinal % ceil(source count / per-source limit) == 0',
                  product_full_resolution_build_completed=False,
                  unit_verified=scene['unit_verified'], alignment_verified=False,
                  source_manifest_sha256=digest(root/'scene.json'))
    (output/'verification.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--source-root', type=Path)
    parser.add_argument('--sample-limit', type=int, default=20_000)
    args = parser.parse_args()
    print(json.dumps(generate(args.root, args.output, source_root=args.source_root,
                              sample_limit=args.sample_limit), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
