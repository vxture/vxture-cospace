"""Build an offline drafting page; server-side annotation checks remain required."""
import argparse
import json
from pathlib import Path

import numpy as np

from experiments.scripts.ifc_sections import _svg, cut_sections
from experiments.scripts.ifc_spatial_annotation import seed, validate_annotations
from experiments.scripts.ifc_structure_review import structure_review
from packages.spatial.scene_identity import content_digest
from packages.data.ifc_workspace import read_json


def editor_html(root, *, expected_catalog_sha256, heights, worksheet=None):
    review = structure_review(root, expected_catalog_sha256=expected_catalog_sha256)
    sections = cut_sections(root, expected_catalog_sha256=expected_catalog_sha256, heights=heights)
    views, templates = [], []
    for section in sections['sections']:
        rows = section['segments']
        if not rows:
            continue
        points = np.asarray([row['points_m'] for row in rows])[..., :2].reshape(-1, 2)
        lo, hi = points.min(0), points.max(0)
        scale = min(1100 / max(hi[0] - lo[0], .001), 650 / max(hi[1] - lo[1], .001))
        templates.append(f'<template id="section-view-{len(views)}">{_svg(section)}</template>')
        views.append(dict(z=section['z_m'], lo=lo.tolist(), scale=scale))
    if not views:
        raise ValueError('annotation_editor_empty_sections')
    document = seed(review) if worksheet is None else worksheet
    validate_annotations(document, review)
    payload = dict(worksheet=document, levels=review['declared_levels'],
                   tasks=[dict(id=t['source_entity_id'], name=t['source']['name'],
                               ifc_type=t['source']['ifc_type']) for t in review['tasks']],
                   section_sha256=content_digest(sections), views=views)
    encoded = json.dumps(payload, ensure_ascii=False, allow_nan=False).replace('<', '\\u003c')
    template = Path(__file__).with_suffix('.html').read_text(encoding='utf-8')
    return template.replace('__EDITOR_DATA__', encoded, 1).replace('__SECTION_TEMPLATES__', ''.join(templates), 1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ifc-root', type=Path, required=True)
    parser.add_argument('--ifc-sha256', required=True)
    parser.add_argument('--z', type=float, action='append', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--worksheet', type=Path, help='Validate and resume an exported worksheet')
    args = parser.parse_args()
    document = read_json(args.worksheet, 8 * 1024 * 1024)[1] if args.worksheet else None
    html = editor_html(args.ifc_root, expected_catalog_sha256=args.ifc_sha256, heights=args.z, worksheet=document)
    with args.output.open('x', encoding='utf-8') as stream:
        stream.write(html)


if __name__ == '__main__':
    main()
