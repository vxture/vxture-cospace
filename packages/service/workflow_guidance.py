"""Recommended scene handoffs over saved facts; never a publication admission gate."""
from datetime import datetime, timezone
import sqlite3
from packages.service.scene_registrations import instant


def _action(space, module, label, **values):
    return {'module': module, 'label': label, 'values': {'space': space, **values}}


def _step(identity, title, status, detail, action):
    return {'id': identity, 'title': title, 'status': status, 'detail': detail, 'action': action}


def _saved_registration(registrations, space, job, at):
    try:
        state = registrations.read(registrations.source(space, job))
        adopted = state['adopted']
        now = instant(at) if at else datetime.now(timezone.utc)
        valid = adopted and instant(adopted['approval']['valid_from']) <= now < instant(adopted['approval']['valid_until'])
        if state['review_status'] == 'approved' and state['approved_revision'] == state['adopted_revision'] and valid:
            return 'complete', '当前模型已显式采用有效期内的核准配准修订。'
        if state['review_status'] == 'submitted':
            return 'in_progress', '配准资料已提交，等待独立审核后显式采用。'
        if state['review_status'] == 'approved':
            return 'pending', '核对核准有效期，并显式采用该配准修订。'
        if state['review_status'] in ('draft', 'rejected'):
            return 'pending', '继续核对配准资料、独立检查点及基准依据，完成后提交审核。'
    except (OSError, sqlite3.Error, KeyError, TypeError, ValueError):
        return 'needs_attention', '当前模型的配准来源或记录需要处理，请进入空间配准核查。'
    return 'pending', '构建核对后录入配准资料，完成独立审核并显式采用核准修订。'


def _registration_status(context, registrations, at):
    if context['viewing'] or context['following']:
        return 'unknown', '只核对当前跟进目标，不借用其他模型的配准记录。'
    if context['publication']:
        return 'unknown', '已有固定发布保持独立；此处不追认其配准状态。'
    if context['job'] and context['build_ready']:
        return _saved_registration(registrations, context['space'], context['job'], at)
    return 'pending', '构建核对后录入配准资料，完成独立审核并显式采用核准修订。'


def _primary(context, report, steps):
    by_id = {item['id']: item for item in steps}
    summary = report['summary']
    if context['viewing']:
        return ('services', by_id['services']['action']) if context['available'] else ('delivery', summary['primary_action'])
    if context['following'] or not context['job'] or not context['build_ready']:
        current = summary['journey']['current_step']
        return ('build' if current == 'review' else current), summary['primary_action']
    if context['publication']:
        return ('services', by_id['services']['action']) if context['available'] else ('delivery', by_id['delivery']['action'])
    if by_id['registration']['status'] != 'complete':
        return 'registration', by_id['registration']['action']
    if by_id['association']['status'] != 'complete':
        return 'association', by_id['association']['action']
    return 'delivery', by_id['delivery']['action']


def _context(report):
    summary = report['summary']
    viewing = summary['viewing_publication']
    publication = report['publication_ref']
    stages = {item['id']: item for item in report['stages']}
    review = next(item for item in summary['journey']['steps'] if item['id'] == 'review')
    candidate = report['candidate_ref']
    tracked = summary['tracked_job']
    input_target = summary['journey']['target']['kind'] == 'input'
    job = (viewing['candidate_id'] if viewing else tracked['job_id'] if tracked else
           candidate['candidate_id'] if candidate and not input_target else None)
    following = input_target or bool(tracked and not tracked['is_current'])
    release_id = viewing['publication_id'] if viewing else publication['publication_id'] if publication else None
    available = bool(release_id and (viewing['status'] == 'available' if viewing else stages['delivery']['status'] == 'recorded'))
    return {'space': report['space_id'], 'job': job, 'viewing': viewing, 'publication': publication,
            'following': following, 'release_id': release_id, 'available': available,
            'build_ready': stages['build']['status'] == 'ready' and review['status'] == 'complete'}


def workflow_guidance(report, registrations, *, at=None):
    context = _context(report)
    journey = report['summary']['journey']
    previous = {item['id']: item for item in journey['steps']}
    build = previous['review'] if previous['build']['status'] == 'complete' else previous['build']
    model_values = {'job': context['job']} if context['job'] else {}
    registration_status, registration_detail = _registration_status(context, registrations, at)
    association_recorded = any(report['counts'].get(key, 0) for key in ('objects', 'business_bindings', 'object_relations'))
    association_status = 'unknown' if context['viewing'] or context['following'] else 'complete' if association_recorded else 'pending'
    service_values = {'publication': context['release_id']} if context['release_id'] else {}
    space = context['space']
    steps = [previous['data'], {**build, 'id': 'build', 'title': '构建与核对'},
             _step('registration', '空间配准', registration_status, registration_detail,
                   _action(space, 'registration', '前往空间配准', **model_values) if context['job'] else None),
             _step('association', '空间关联', association_status,
                   '按业务需要核对对象、关系与台账；可在关联工作面继续发布准备。',
                   _action(space, 'association', '前往空间关联', tab='overview', **model_values) if context['job'] else None),
             {**previous['delivery'], 'title': '服务发布'},
             _step('services', '空间服务', 'complete' if context['available'] else 'pending',
                   '接入与交付绑定指定固定发布；设备使用状态仍需实际验证。',
                   _action(space, 'services', '前往空间服务', section='directory', tab='overview', **service_values))]
    current, primary = _primary(context, report, steps)
    return {'profile': 'cospace.workflow-guidance/0.1', 'target': journey['target'],
            'steps': steps, 'current_step': current, 'primary_action': primary,
            'basis': 'saved_records_not_publication_gate'}
