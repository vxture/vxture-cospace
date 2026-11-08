"""Read-only provenance relationships anchored to an immutable preview publication."""
import json
import re
from packages.construction.preview_jobs import now
from packages.construction.preview_model import digest
from packages.views.agent.preview_offline import export_bundle, sha
from packages.lifecycle.preview_scope import owned


def lineage(publications, identity, *, provenance=False):
    record, model = publications.read(identity)
    source = model.manifest.get('source', {})
    binding = source.get('input_binding')
    if provenance and binding and owned(binding) != owned(record):
        raise ValueError('lineage_input_scope_mismatch')
    nodes = []

    def add(kind, title, status, identifier, detail, **extra):
        nodes.append(dict(kind=kind, title=title, status=status, id=identifier, detail=detail, **extra))

    if not binding:
        add('input', '登记资料', 'missing', None, '此历史模型未记录输入登记绑定；不按路径猜测登记资料。')
    else:
        status = 'matched'; detail = '模型保存的输入登记与当前登记记录一致；未重新预检源文件。'
        keys=(('snapshot_sha256','cloud_sha256') if binding.get('format')=='ply_pointcloud' else
              ('snapshot_sha256','bag_sha256','selected_frame') if binding.get('format') in ('ros1_lidar_single_frame','ros1_lidar_multiframe_icp') else ('snapshot_sha256','tracking_sha256'))
        if any(binding.get(k) != source.get(k) for k in keys):
            status = 'mismatch'; detail = '模型来源摘要与保存的输入绑定不一致。'
        elif publications.jobs.inputs is None:
            status = 'missing'; detail = '保存了输入绑定，但当前服务未配置资料目录。'
        else:
            try:
                registered = publications.jobs.inputs.read(binding['id'])
                if provenance and owned(registered) != owned(record):
                    raise ValueError('lineage_input_scope_mismatch')
                expected = {k:v for k,v in registered.items() if k not in ('snapshot','tracking')}
                if expected != binding:
                    status = 'mismatch'; detail = '当前登记记录与模型保存的输入绑定不一致。'
            except (ValueError, OSError, KeyError, TypeError):
                status = 'missing'; detail = '保存了输入绑定，但对应登记记录不可读。'
        add('input', '登记资料', status, binding.get('id'), detail,
            label=binding.get('label'), snapshot_sha256=binding.get('snapshot_sha256'),
            tracking_sha256=binding.get('tracking_sha256'),cloud_sha256=binding.get('cloud_sha256'),
            **({'registration_ref':binding['registration_ref']} if binding.get('registration_ref') else {}),
            **({'batch_ref':source['batch_ref']} if source.get('batch_ref') else {}))

    candidate = record['candidate_id']
    status = 'missing'; detail = '源构建任务不可读，固定发布快照仍可独立使用。'
    if re.fullmatch(r'build-[A-Za-z0-9-]+', candidate):
        root = publications.jobs.root/candidate
        try:
            job = json.loads((root/'job.json').read_bytes())
            matched = (owned(job) == owned(record) == owned(model.manifest)
                       and job['id'] == candidate and job['state'] == 'succeeded'
                       and model.manifest['id'] == candidate
                       and digest(root/'output'/'model.json') == record['model_manifest_sha256'])
            if binding:
                matched = matched and job.get('input_id') == binding.get('id') and job.get('input_binding') == binding
            matched = matched and job.get('batch_ref') == source.get('batch_ref')
            status = 'matched' if matched else 'mismatch'
            detail = ('任务、候选模型摘要及已记录的输入绑定一致。' if matched
                      else '当前构建任务或候选内容与发布保存的绑定不一致。')
        except (OSError, ValueError, KeyError, TypeError): pass
    add('build', '构建任务', status, candidate, detail)
    add('publication', '固定发布', 'matched', identity, '当前发布文件完整性已核对。',
        model_manifest_sha256=record['model_manifest_sha256'],
        source_model_sha256=record['source_model_sha256'])
    if provenance:
        add('candidate', '来源候选', nodes[1]['status'], candidate,
            '固定发布保存的来源候选；与当前工作选择无关。',
            model_manifest_sha256=record['model_manifest_sha256'])
        ref = model.manifest.get('semantic_annotation', {}).get('ontology_ref')
        add('ontology', '固定本体规则', 'matched' if ref else 'missing',
            ref.get('ontology_id') if ref else None,
            '发布快照保存的规则引用；不自动升级。' if ref else '此发布未记录本体引用。',
            **({'ontology_ref': ref} if ref else {}))
        return {'profile': 'cospace.publication-provenance/0.1', 'publication_id': identity,
                **owned(record), 'checked_at': now(), 'nodes': nodes,
                'package_generated': False, 'preflight_sequence': None,
                'notice': '核对固定发布及当前可读来源；未导出离线包、未重检源文件。构建未保存预检序号，资料历史不作为当时构建预检证据。',
                'robot_ready': False, 'production_ready': False}
    bundle = export_bundle(record, model)
    add('package', '离线交付包', 'matched', identity+'-offline.zip',
        '由此固定发布导出，包内发布及模型绑定校验通过。', sha256=sha(bundle), bytes=len(bundle),
        download_url=record['preview_url']+'offline.zip')
    return {'profile':'cospace.preview-lineage/0.1', 'publication_id':identity,
            **owned(record),
            'checked_at':now(), 'nodes':nodes,
            'relationships':[{'from':nodes[i]['kind'],'to':nodes[i+1]['kind']} for i in range(3)],
            'notice':'只核对当前本机记录与文件绑定；不重新预检原始资料，不代表精度验收或可信签名。',
            'robot_ready':False,'production_ready':False}
