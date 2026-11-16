"""Reproducible synthetic SG4/SG5 consumption trial, not a production acceptance."""
import argparse
from copy import deepcopy
from html import escape
import json
from pathlib import Path
import platform
import shutil
import subprocess
import time

import numpy as np

from experiments.scripts.scene_graph_sample import sample
from experiments.scripts.scene_sg1_samples import identity_samples
from packages.spatial.scene_changes import compare_snapshots
from packages.spatial.scene_identity import snapshot_ref
from packages.spatial.scene_matching import propose_identity_matches
from packages.spatial.scene_states import resolve_opening_state
from packages.views.agent.scene_exchange import write_exchange
from packages.views.agent.scene_reader import SceneSubsetReader
from packages.views.agent.scene_subset import build_scene_subset
from packages.infrastructure.local_output import new_output_directory, write_member


def _write(root, name, document):
    write_member(root, name, (json.dumps(document, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode('utf-8'))


def _state_cases():
    base = sample()
    cases = {}
    for name in ('known', 'expired', 'unavailable', 'unknown', 'conflict'):
        graph = deepcopy(base)
        graph['snapshot_id'] = 'trial-' + name
        as_of = '2026-11-16T00:06:00Z' if name == 'expired' else '2026-11-16T00:03:00Z'
        known = '2026-11-16T00:00:00Z' if name == 'unavailable' else '2026-11-16T00:06:00Z'
        if name == 'unknown':
            graph['observations'][0]['value'] = 'unknown'
        if name == 'conflict':
            graph['sources'].append({'id': 'alternative', 'kind': 'synthetic_fixture'})
            graph['observations'].append(dict(graph['observations'][0], id='other-observation',
                                               source_id='alternative', value='open'))
        cases[name] = resolve_opening_state(graph, 'door-l1', as_of=as_of, known_at=known)
    return cases


def run_trial(output, *, allowed_root=None):
    node = shutil.which('node')
    if node is None:
        raise ValueError('independent_node_consumer_required')
    root = new_output_directory(output, allowed_root=allowed_root)
    source = sample()
    pin = snapshot_ref(source)
    package = build_scene_subset(source, ['corridor-l1'])
    write_exchange(package, pin, root / 'exchange', allowed_root=root)
    _write(root, 'source-ref.json', pin)
    _write(root, 'source.synthetic.json', source)
    reader = SceneSubsetReader(package, pin, source_document=source)
    python_result = reader.connections('corridor-l1')
    command = [str(Path(node).resolve()), '--', str(Path('examples/scene-graph/consumers/read-subset.mjs').resolve()), str(root / 'exchange'),
               str(root / 'source-ref.json'), 'connections', 'corridor-l1']
    independent = subprocess.run(command, shell=False, check=True, capture_output=True, text=True, encoding='utf-8', timeout=15)
    node_result = json.loads(independent.stdout)
    if python_result['items'] != node_result['items']:
        raise ValueError('independent_consumer_results_differ')
    _write(root, 'python-consumer.json', python_result)
    _write(root, 'node-consumer.json', node_result)
    cases = _state_cases()
    _write(root, 'states.synthetic.json', cases)
    base, target, proposals = identity_samples()
    changes = compare_snapshots(base, target, identity_changes=proposals['unresolved'])
    matches = propose_identity_matches(base, target, maximum_distance_m=10)
    _write(root, 'changes.synthetic.json', changes)
    _write(root, 'matches.synthetic.json', matches)
    timings = []
    for _ in range(100):
        started = time.perf_counter()
        reader.connections('corridor-l1')
        timings.append((time.perf_counter() - started) * 1000)
    report = {'data_kind': 'synthetic', 'real_release_ready': False, 'independent_consumers_agree': True, 'entities': len(source['entities']), 'package_bytes': sum(p.stat().st_size for p in (root / 'exchange').iterdir()), 'python': platform.python_version(), 'platform': platform.platform(), 'samples': 100, 'in_memory_query_ms': {'p50': float(np.percentile(timings, 50)), 'p95': float(np.percentile(timings, 95))}, 'state_statuses': {name: result['status'] for name, result in cases.items()}, 'limitations': ['tiny_synthetic_fixture_only', 'no_network_authorization_or_io_benchmark',
                               'no_peak_memory_measurement', 'not_a_production_performance_target']}
    _write(root, 'report.json', report)
    rows = ''.join(f'<tr><td>{escape(name)}</td><td>{escape(result["status"])}</td></tr>' for name, result in cases.items())
    html = (
        '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>SG4 / SG5 合成验收试验</title>'
        '<style>body{max-width:1000px;margin:40px auto;padding:0 24px;font:16px system-ui;color:#19324a;background:#f3f6fa}'
        'section{background:white;border:1px solid #d5e1ea;border-radius:12px;padding:24px;margin:20px 0}'
        'td,th{text-align:left;padding:10px 24px 10px 0}a{color:#176eaa}p{line-height:1.8}</style>'
        '<h1>SG4 / SG5 合成验收试验</h1><p>仅验证软件行为；不是已核实的真实底图或正式发布。</p>'
        '<section><h2>两个独立消费端</h2><p>Python 与 Node 读取相同结构连接。Node 校验原始字节，'
        '仅声明完整性与引用闭合，不声明完整领域验证或源选择完整性。</p>'
        '<a href="python-consumer.json">Python 结果</a> · <a href="node-consumer.json">Node 结果</a></section>'
        '<section><h2>状态时效与冲突</h2><table><tr><th>用例</th><th>结果</th></tr>' + rows + '</table>'
        '<a href="states.synthetic.json">完整状态记录</a></section>'
        '<section><h2>跨版变化与身份候选</h2><p>拆分候选保持未决；近似范围重叠不构成身份确认。</p>'
        '<a href="changes.synthetic.json">变化清单</a> · <a href="matches.synthetic.json">匹配提案</a></section>'
        '<section><h2>测试条件与性能记录</h2><p>11 个合成实体，100 次内存查询；不代表网络服务性能。</p>'
        '<a href="report.json">完整记录</a></section></html>')
    write_member(root, 'index.html', html.encode('utf-8'))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run_trial(args.output_dir), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
