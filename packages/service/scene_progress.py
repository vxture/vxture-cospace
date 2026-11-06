"""Read-only presentation of saved workflow records; never an admission gate."""
import json
import re
from packages.lifecycle.preview_scope import scope, match


def progress(publications, report, catalog, job_id=None, publication_id=None, preparation=None):
    jobs = publications.jobs
    space_id = report['space_id']
    ownership = scope(jobs.directory, space_id)
    stages = {stage['id']: stage for stage in report['stages']}
    selected = report['candidate_ref']
    selected_id = selected['candidate_id'] if selected else None

    def action(module, label, **values):
        return {'module': module, 'label': label, 'values': {'space': space_id, **values}}

    releases = []
    for item in catalog['items']:
        if item['kind'] != 'publication':
            continue
        # Never treat unreadable metadata as an available fixed version.
        relation = next((r for r in catalog['relations'] if r['from'] == item['key'] and r['relation'] == 'published_from'), None)
        candidate_id = relation['to'].split(':', 1)[1] if relation and relation['to'] else None
        releases.append({'publication_id': item['record_id'], 'candidate_id': candidate_id,
                         'status': 'unavailable' if item['integrity'] != 'snapshot_verified' else
                         'paused' if item['lifecycle_state'] in ('paused','retired') else 'available',
                         'matches_current': bool(selected_id and candidate_id == selected_id and
                                                 item.get('model_manifest_sha256') == selected['model_manifest_sha256'])})
    viewing = None
    if publication_id:
        # Resolve only within the requested scene. Do not substitute a newer release.
        viewing = next((r for r in releases if r['publication_id'] == publication_id), None)
        if viewing is None:
            raise ValueError('workflow_publication_not_in_space')

    complete = all(s['status'] in ('recorded', 'ready') for s in report['stages']
                   if not s.get('optional') and s['id'] != 'consumer')
    base = stages[report['next_stage']]
    state = 'complete' if complete else 'needs_attention' if base['status'] == 'blocked' else 'in_progress' if base['status'] == 'in_progress' else 'pending'
    work = {'status': state, 'label': '服务端流程已完成' if complete else
            '当前候选待发布' if base['id'] == 'delivery' and base['status'] == 'pending' else
            '候选待核对' if base['id'] == 'build' and base['status'] == 'pending' and report['counts']['candidate'] else
            '资料待准备' if base['id'] == 'data' else '当前工作需处理' if state == 'needs_attention' else '当前工作待继续',
            'detail': '固定模型、双视图及匹配发布已具备；现场质量仍待验收。' if complete else base['detail'],
            'action': report['next_action']}
    tracked = None
    if job_id:
        if not re.fullmatch(r'build-[A-Za-z0-9-]+', job_id):
            raise ValueError('invalid_workflow_job')
        saved = json.loads((jobs.root / job_id / 'job.json').read_bytes())
        match(saved, ownership)
        if saved.get('id') != job_id:
            raise ValueError('workflow_job_binding_mismatch')
        state = saved.get('state', 'unknown')
        candidate = next((i for i in catalog['items'] if i['kind'] == 'candidate' and i['record_id'] == job_id), None)
        tracked = {'job_id': job_id, 'state': state, 'is_current': job_id == selected_id}
        if state != 'succeeded' or job_id != selected_id:
            labels = {'queued': '构建排队中', 'running': '构建进行中', 'failed': '构建失败，需恢复',
                      'interrupted': '构建中断，需恢复', 'views_failed': '视图待恢复', 'succeeded': '候选待核对'}
            valid = state == 'succeeded' and candidate and candidate['integrity'] == 'snapshot_verified'
            work = {'status': 'in_progress' if state in ('queued', 'running') else 'pending' if valid else 'needs_attention',
                    'label': labels.get(state, '任务状态需核查') if state != 'succeeded' or valid else '候选成果不可读',
                    'detail': '正在跟进指定任务；不会改变当前选择或既有固定发布。',
                    'action': action('build', '查看指定构建', job=job_id, tab='flow')}
            if valid and any(r['candidate_id'] == job_id for r in releases):
                work.update(status='recorded', label='指定候选已有固定发布')
    elif preparation and preparation['selected_input_id']:
        item = next(r for r in preparation['inputs'] if r['input_id'] == preparation['selected_input_id'])
        ready = preparation.get('can_submit', item['check_status'] == 'passed' and item['lifecycle_state'] == 'active')
        work = {'status': 'pending' if ready else 'needs_attention', 'label': '资料可用于构建' if ready else '资料待准备',
                'detail': preparation['detail'], 'action': preparation['next_action']}
    elif preparation and not selected_id and not report['counts']['candidate'] and not catalog['job_counts']:
        work = {'status': 'pending', 'label': '资料待准备', 'detail': preparation['detail'], 'action': preparation['next_action']}

    primary = work['action']
    if viewing:
        primary = action('space', '打开当前查看版本', publication=publication_id) if viewing['status'] == 'available' else action('delivery', '查看目标发布', publication=publication_id)
    return {'profile': 'cospace.scene-progress/0.1', 'work': work, 'candidate_ref': selected,
            'service_status': 'complete' if complete else 'needs_attention' if any(s['status'] == 'blocked' for s in report['stages'] if not s.get('optional')) else 'pending',
            'tracked_job': tracked, 'viewing_publication': viewing, 'publications': releases,
            'available_publication_count': sum(r['status'] == 'available' for r in releases),
            'primary_action': primary, 'consumer_status': 'unobserved', 'consumer_state_checked': False}
