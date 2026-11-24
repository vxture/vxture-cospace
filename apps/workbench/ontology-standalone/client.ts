import {parseLibrary, parseLibraryDirectory, type Reference} from '@vxture/ontology-ui/contract';
import {parseWorkbench, type AuthoringClient} from '@vxture/ontology-ui/authoring-contract';
import {parseGroupConfiguration, type GroupConfigurationClient} from '@vxture/ontology-ui/group-configuration';

const definitions = '/api/ontology-definitions';
const groups = '/api/ontology-configuration/groups';
const exchange = '/api/ontology-exchange/definitions';
export const maxPackageBytes = 1024 * 1024 + 4096;
export const moduleId = /^[a-z][a-z0-9_-]{0,63}$/;
export const permissions = ['read', 'read_private', 'edit', 'submit', 'review', 'publish', 'configure_groups'] as const;
type Permission = typeof permissions[number];
export type Session = {profile: 'vxture.ontology-session/0.1'; actor: string; scope: string; permissions: Permission[]};
export type DraftSummary = {module_id: string; title: string; version: string; revision: number; updated_at: string};
type Problem = {code: string; path: string};
export type Preflight = {can_import: boolean; reference: Reference; expected_revision: number;
  dependencies: {reference: Reference; state: 'published' | 'unpublished'}[]; diagnostics: Problem[]};

const messages: Record<string, string> = {
  revision_changed: '有更新的草稿，请刷新后重试。', review_stale: '送审修订已过期，请重新校验并送审。',
  self_approval_forbidden: '提交人不能审批自己的定义。',
  release_not_found: '固定版本不存在，或所需的精确依赖尚未发布。',
  validation_failed: '草稿校验未通过，请修正后再送审。',
  approval_required: '请先取得当前修订的审批。', version_exists: '版本已发布。',
  version_not_advanced: '目标版本须高于现有版本。', exchange_version_conflict: '同一标识和版本的内容不一致。',
  exchange_already_draft: '该版本已是当前草稿。', exchange_already_published: '该版本已发布。',
  bundle_digest_mismatch: '定义包摘要不匹配。', reference_mismatch: '模块引用与包内定义不匹配。',
  duplicate_key: '文件包含重复的 JSON 字段。', invalid_json: '文件不是有效的 UTF-8 JSON。',
  size_budget: '文件超过大小限制。', unsupported_profile: '不支持该定义包格式。',
  missing_dependency: '定义包缺少固定依赖。', request_conflict: '请求标识已使用，请重新打开后再操作。',
  ontology_group_name_exists: '分组名称已存在。', ontology_group_revision_changed: '分组已被更新，请刷新后再操作。',
};
export const explain = (code: string) => Object.hasOwn(messages, code) ? messages[code] : `无法完成操作（${code}）。`;
const fixed = (ref: Reference) => '?' + new URLSearchParams(ref);

export function createClient(token: string, expired?: () => void) {
  async function request(path: string, signal: AbortSignal, body?: object) {
    const response = await fetch(path, {
      signal, cache: 'no-store', credentials: 'omit', redirect: 'error',
      headers: {Authorization: 'Bearer ' + token, ...(body ? {'Content-Type': 'application/json'} : {})},
      ...(body ? {method: 'POST', body: JSON.stringify(body)} : {}),
    });
    if (response.ok) return response;
    if (response.status === 401) { expired?.(); throw Error('令牌无效，请使用本机管理员签发的令牌。'); }
    if (response.status === 403) throw Error('当前身份无权执行此操作。');
    const failure: {detail?: string; path?: string} | null = await response.json().catch(() => null);
    if (failure?.detail) throw Error(explain(failure.detail) + (failure.path && failure.path !== '/' ? ` ${failure.path}` : ''));
    throw Error('本体服务暂不可用，请重试。');
  }
  const json = async (path: string, signal: AbortSignal, body?: object) => (await request(path, signal, body)).json();
  const authoring: AuthoringClient = {
    read: async (id, signal) => parseWorkbench(await json(definitions + '?' + new URLSearchParams({module_id: id}), signal)),
    change: (body, signal) => json(definitions, signal, body),
    definition: (ref, signal) => json(definitions + fixed(ref), signal),
    review: (reviewId, signal) => json(definitions + '?' + new URLSearchParams({review_id: reviewId}), signal),
  };
  const configuration: GroupConfigurationClient = {
    load: async signal => parseGroupConfiguration(await json(groups, signal)),
    save: async (body, signal) => parseGroupConfiguration(await json(groups, signal, body)),
  };
  return {
    authoring, configuration,
    async session(signal: AbortSignal): Promise<Session> {
      const value = await json('/api/ontology-session', signal) as Session;
      if (value.profile !== 'vxture.ontology-session/0.1' || typeof value.actor !== 'string' ||
          typeof value.scope !== 'string' || !Array.isArray(value.permissions) ||
          value.permissions.some(grant => !permissions.includes(grant))) throw Error('此宿主版本不支持独立工作台。');
      return value;
    },
    directory: async (signal: AbortSignal) => parseLibraryDirectory(await json('/api/ontology-directory', signal)),
    async drafts(signal: AbortSignal): Promise<DraftSummary[]> {
      const value = await json('/api/ontology-drafts', signal);
      if (value?.profile !== 'vxture.ontology-drafts/0.1' || !Array.isArray(value.drafts) ||
          !value.drafts.every((d: DraftSummary) => d && moduleId.test(d.module_id) && typeof d.title === 'string' &&
            typeof d.version === 'string' && Number.isInteger(d.revision) && d.revision > 0 && Number.isFinite(Date.parse(d.updated_at)))) {
        throw Error('草稿清单响应无效。');
      }
      return value.drafts;
    },
    definition: async (ref: Reference, signal: AbortSignal) => parseLibrary(await authoring.definition(ref, signal)),
    export: async (ref: Reference, signal: AbortSignal) => (await request(exchange + fixed(ref), signal)).text(),
    preflight: (text: string, signal: AbortSignal): Promise<Preflight> => json(exchange, signal, {action: 'preflight', package_json: text}),
    importDraft: (text: string, revision: number, id: string, signal: AbortSignal) => json(exchange, signal, {
      action: 'import', package_json: text, expected_revision: revision, request_id: id,
    }),
  };
}

export type Client = ReturnType<typeof createClient>;
