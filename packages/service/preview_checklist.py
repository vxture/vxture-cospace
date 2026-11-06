"""Read-only workflow checks for one explicitly selected fixed publication."""
import json
from pathlib import Path
import numpy as np
from packages.construction.preview_jobs import now
from packages.views.agent.preview_offline import export_bundle, OfflinePreview, sha
from packages.lifecycle.preview_scope import owned


def checklist(publications, identity, update_evidence=None):
    record, model = publications.read(identity)
    manifest = model.manifest
    stages = []

    def add(key, title, status, detail, basis):
        stages.append(dict(id=key, title=title, status=status, detail=detail, basis=basis))

    source = manifest.get('source', {})
    construction = manifest.get('construction', {})
    count = construction.get('used_frames')
    add('input', '资料导入', 'recorded' if source.get('snapshot_sha256') else 'missing',
        f"模型清单记录使用 {count} 帧；本次未重读原始资料。" if count is not None else '未记录采集资料及帧数。',
        'model_manifest')
    add('candidate', '空间模型', 'passed', f"发布快照模型 {manifest['id']}，成员摘要核对通过。", 'live_integrity')
    has_human = bool(manifest.get('human_view', {}).get('path') in manifest['members'])
    add('views', '双视图派生', 'passed' if has_human else 'missing',
        '人视图、智能体视图成员摘要通过。' if has_human else '当前清单缺少人视图成员绑定。', 'live_integrity')
    add('publication', '固定发布', 'passed', f"{identity} · 选择修订 {record['selection_revision']}，独立快照核对通过。", 'live_integrity')
    if manifest.get('semantic_annotation'):
        objects=model.objects()
        add('semantics','对象与固定本体','recorded',f"{len(objects['objects'])}个标注的规则、模型点锚定及双视图引用已核对；语义仍待现场核实。",'live_integrity')
    if getattr(model,'business_snapshot',None) is not None:
        add('business','固定业务台账','recorded',f"{len(model.business_snapshot['bindings'])}项固定绑定及嵌入台账摘要已核对；不读取外部最新业务状态。",'live_integrity')
    if getattr(model,'relation_snapshot',None) is not None:
        add('relations','固定对象关系','recorded',f"{len(model.relation_snapshot['relations'])}条关系的端点、本体规则及对象快照绑定已核对；连接不代表可通行。",'live_integrity')
    bundle = export_bundle(record, model)
    offline = OfflinePreview(bundle, identity, sha(bundle))
    # Derive both queries from the actual payload; never infer free space.
    cell = next(iter(model.cells), None)
    if cell is None:
        add('query', '在线与离线查询', 'missing', '智能体数据没有表面单元，无法完成两类状态对照。', 'live_query')
    else:
        unknown = (max(c[0] for c in model.cells) + 2, 0, 0)
        checks = []
        for index, state in ((cell, 'surface_candidate'), (unknown, 'unknown')):
            point = ((np.asarray(index, dtype=float) + .5) * model.resolution).tolist()
            online = {**model.query(point), 'publication_id': identity,
                      'publication_model_manifest_sha256': record['model_manifest_sha256']}
            result = offline.query(point)
            checks.append(result == online and result['state'] == state)
        if manifest.get('semantic_annotation'):
            checks.append(offline.objects()=={**model.objects(),'publication_id':identity,'publication_model_manifest_sha256':record['model_manifest_sha256']})
        add('query', '在线与离线查询', 'passed' if all(checks) else 'failed',
            '同进程调用服务查询实现与离线读取器，表面候选、未知状态及可用对象/业务/关系快照逐字段对照；未发起HTTP或断网测试。', 'live_query')
    add('offline', '轻量离线交付', 'passed', f'{len(bundle):,} 字节，包完整性及发布绑定核对通过。', 'live_package')
    status = 'missing'; detail = '暂无绑定此发布的版本切换验证记录。'
    if update_evidence and Path(update_evidence).is_file():
        try:
            evidence = json.loads(Path(update_evidence).read_bytes())
            new = evidence['new_publication']
            bound = (new['id'] == identity and new['model_manifest_sha256'] == record['model_manifest_sha256']
                     and evidence['after']['package_sha256'] == sha(bundle)
                     and evidence['after']['publication_id'] == identity
                     and evidence['online_new']['publication_id'] == identity)
            passed = all(evidence.get(k) is True for k in (
                'download_only_did_not_activate', 'old_session_unchanged',
                'old_publication_unchanged', 'stale_activation_refused',
                'socket_creation_disabled_during_switch'))
            if bound:
                status = 'recorded' if passed else 'failed'
                detail = ('已有新旧版本切换及历史复查记录；刷新只核对记录绑定，不重新执行切换。'
                          if passed else '已有记录绑定此发布，但切换验证未全部通过。')
        except (ValueError, KeyError, TypeError, OSError):
            status = 'failed'; detail = '版本切换记录不可读或字段不完整。'
    add('update', '版本切换与复查', status, detail, 'saved_evidence')
    return {'profile': 'cospace.preview-checklist/0.1', 'checked_at': now(),
            **owned(record),
            'publication_id': identity, 'model_manifest_sha256': record['model_manifest_sha256'],
            'package_sha256': sha(bundle), 'stages': stages,
            'scope': 'local_preview_only', 'production_ready': False, 'robot_ready': False,
            'gaps': ['精度与完整度尚未独立验收',
                     '对象语义与锚定尚未独立核实；尚无可通行空间判定' if manifest.get('semantic_annotation') else '尚无语义对象及可通行空间判定',
                     '尚未接入真实设备采集与机器人消费', '当前服务不读取消费端的保存、激活和恢复状态；须在消费端核验固定引用',
                     '尚无生产认证、可信分发和运行授权']}
