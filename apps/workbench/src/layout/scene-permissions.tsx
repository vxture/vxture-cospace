import React, { useEffect, useState } from "react";
import {
  Button,
  Drawer,
  Input,
  NativeSelect,
  Table,
  TableHeader,
  TableHead,
  TableRow,
  TableBody,
  TableCell,
} from "@vxture/design-system";
import { usePlatformSession } from "./platform-auth";
import { sessionScopeKey } from "./session-continuity";
import { businessEndpoint } from "./business-endpoint";
import { runGuarded, useUnsavedNavigation } from "./unsaved-navigation";
import "./scene-permissions.css";
import { displayText } from "./display-text";

type Role = "viewer" | "engineer" | "manager";
type Grant = {
  subject: string;
  space_id: string;
  role: Role;
  display_name: string;
  scene_name: string;
};
type Member = {
  subject: string;
  display_name: string;
  requested_at: string | null;
};
type Access = {
  workspace_id: string;
  can_manage: boolean;
  revision: number;
  requested: boolean;
  default_role: "viewer" | null;
  members?: Member[];
  scenes?: { id: string; name: string }[];
  grants?: Grant[];
  member_total?: number;
  scene_total?: number;
  grant_total?: number;
  selected_role?: Role | null;
  self_roles?: string[];
  history?: {
    display_name: string;
    scene_name: string;
    actor_name: string;
    revision: number;
    subject: string;
    space_id: string;
    role: Role | null;
    previous_role: Role | null;
    actor: string;
    reason: string;
    changed_at: string;
  }[];
};
const roleLabels: Record<string, string> = {
  viewer: "查看者",
  engineer: "工程师",
  manager: "管理者",
  none: "无权限",
};
const endpoint = businessEndpoint + "/api/scene-permissions";

export function ScenePermissionsPanel({
  initialSubject = "",
  initialRole,
  editorOnly = false,
  onBusyChange,
  onSaved,
}: {
  readonly initialSubject?: string;
  readonly initialRole?: Role;
  readonly editorOnly?: boolean;
  readonly onBusyChange?: (busy: boolean) => void;
  readonly onSaved?: () => void;
}) {
  const session = usePlatformSession();
  if (!session) return <p>登录后可查看工作区场景权限。</p>;
  return (
    <ScenePermissions
      key={sessionScopeKey(session) + initialSubject}
      {...{ initialSubject, initialRole, editorOnly, onBusyChange, onSaved }}
    />
  );
}

function ScenePermissions({
  initialSubject,
  initialRole,
  editorOnly,
  onBusyChange,
  onSaved,
}: {
  readonly initialSubject: string;
  readonly initialRole?: Role;
  readonly editorOnly: boolean;
  readonly onBusyChange?: (busy: boolean) => void;
  readonly onSaved?: () => void;
}) {
  const session = usePlatformSession();
  const [data, setData] = useState<Access | null>(null),
    [refresh, setRefresh] = useState(0),
    [busy, setBusy] = useState(false),
    [loading, setLoading] = useState(true),
    [error, setError] = useState(""),
    [notice, setNotice] = useState("");
  const [subject, setSubject] = useState(initialSubject),
    [space, setSpace] = useState(""),
    [role, setRole] = useState<Role | "none">("viewer"),
    [reason, setReason] = useState("");
  useEffect(() => {
    onBusyChange?.(busy);
    return () => onBusyChange?.(false);
  }, [busy, onBusyChange]);
  const [panel, setPanel] = useState<"editor" | "details" | "history" | null>(
    null,
  );
  const [query, setQuery] = useState({
    members_q: "",
    scenes_q: "",
    member_offset: 0,
    scene_offset: 0,
    grant_offset: 0,
  });
  function browse(next: Partial<typeof query>) {
    void runGuarded(() => setQuery((value) => ({ ...value, ...next })));
  }
  const labels: Record<string, string> = {
    ...roleLabels,
    none: data?.default_role === "viewer" ? "默认查看者" : "无权限",
  };
  const current = data?.selected_role || "none";
  const dirty =
    (editorOnly || panel === "editor") &&
    (!!reason || (!!subject && !!space && current !== role));
  const acknowledge = useUnsavedNavigation(dirty, "场景权限调整", {
    discard: () => {
      setSubject(initialSubject);
      setSpace("");
      setReason("");
    },
  });
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError("");
    fetch(
      endpoint +
        "?" +
        new URLSearchParams({
          ...Object.fromEntries(
            Object.entries(query).map(([key, value]) => [key, String(value)]),
          ),
          subject,
          space,
        }),
      { cache: "no-store", signal: controller.signal },
    )
      .then(async (response) => {
        if (!response.ok) throw new Error("暂时无法读取场景权限，请重试。");
        const value: Access = await response.json();
        if (
          value.workspace_id !== session?.user?.workspace_id ||
          !Number.isSafeInteger(value.revision) ||
          typeof value.can_manage !== "boolean"
        )
          throw new Error("权限信息无法确认，请重试。");
        if (!controller.signal.aborted) {
          setData(value);
          setRole(
            initialRole ||
              value.selected_role ||
              (value.default_role === "viewer" ? "engineer" : "viewer"),
          );
        }
      })
      .catch((e) => {
        if (!controller.signal.aborted)
          setError(e instanceof Error ? e.message : "读取失败，请重试。");
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [
    refresh,
    session?.user?.workspace_id,
    query,
    subject,
    space,
    initialRole,
  ]);
  async function submit(event?: React.FormEvent) {
    event?.preventDefault();
    if (busy || loading || !data || (editorOnly && !data.can_manage)) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await savePermission(data, { subject, space, role, reason });
      acknowledge();
      setReason("");
      setSubject(initialSubject);
      setSpace("");
      if (!editorOnly) {
        setPanel(null);
      }
      setNotice(
        data.can_manage
          ? "场景权限已保存。成员刷新“我的场景”后即可看到授权结果。"
          : "协作申请已提交，请联系工作区所有者或管理者分配角色。",
      );
      setRefresh((n) => n + 1);
      if (data.can_manage) {
        onSaved?.();
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "提交失败，请重试。");
    } finally {
      setBusy(false);
    }
  }
  function closePanel() {
    if (!busy)
      void runGuarded(() => {
        setPanel(null);
        setSubject(initialSubject);
        setSpace("");
        setReason("");
      });
  }
  function choose(nextSubject: string, nextSpace: string) {
    void runGuarded(() => {
      setPanel("editor");
      setSubject(nextSubject);
      setSpace(nextSpace);
      setReason("");
      setQuery((value) => ({ ...value, grant_offset: 0 }));
    });
  }
  return (
    <div className="scene-permissions-content" aria-busy={busy || loading}>
      {error && <p role="alert">{error}</p>}
      {notice && <output>{notice}</output>}
      <Button
        size="sm"
        variant="outline"
        disabled={busy || loading}
        onClick={() => void runGuarded(() => setRefresh((n) => n + 1))}
      >
        重新读取权限
      </Button>
      {loading && <output>正在读取权限…</output>}
      {data && (
        <PermissionState
          canManage={data.can_manage}
          editorOnly={editorOnly}
          editor={
            <PermissionEditor
              lockedSubject={!!initialSubject}
              {...{
                data,
                busy: busy || loading,
                error,
                subject,
                space,
                role,
                reason,
                current,
                labels,
                choose,
                setRole,
                setReason,
                submit,
                query,
                browse,
              }}
            />
          }
          manager={
            <>
              <div className="management-card-heading">
                <p>功能角色决定可执行的操作；数据范围另行限定可见场景。</p>
                <div className="management-row-actions">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => void runGuarded(() => setPanel("details"))}
                  >
                    权限说明
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => void runGuarded(() => setPanel("history"))}
                  >
                    操作记录
                  </Button>
                  <Button
                    size="sm"
                    disabled={busy || loading}
                    onClick={() => choose("", "")}
                  >
                    分配权限
                  </Button>
                </div>
              </div>
              <PermissionGrants
                {...{
                  data,
                  busy: busy || loading,
                  labels,
                  choose,
                  query,
                  browse,
                }}
              />
              <Drawer
                open={panel === "editor"}
                onClose={closePanel}
                side="right"
                width="min(600px, 100vw)"
                title="分配场景权限"
                closeLabel="关闭权限分配"
              >
                {panel === "editor" && (
                  <div className="scene-permissions-content">
                    <p>仅可调整你管理范围内的场景权限，保存时会再次校验。</p>
                    {error && <p role="alert">{error}</p>}
                    <PermissionEditor
                      lockedSubject={!!initialSubject}
                      {...{
                        data,
                        busy: busy || loading,
                        error,
                        subject,
                        space,
                        role,
                        reason,
                        current,
                        labels,
                        choose,
                        setRole,
                        setReason,
                        submit,
                        query,
                        browse,
                      }}
                    />
                    <Button
                      variant="ghost"
                      disabled={busy}
                      onClick={closePanel}
                    >
                      取消
                    </Button>
                  </div>
                )}
              </Drawer>
              <Drawer
                open={panel === "details"}
                onClose={closePanel}
                side="right"
                width="md"
                title="权限说明"
                closeLabel="关闭权限说明"
              >
                <div className="scene-permissions-content">
                  {" "}
                  <p>
                    {data?.default_role === "viewer"
                      ? "成员默认拥有查看者功能，实际可见场景由数据范围决定。"
                      : ""}
                    查看者可预览和查询；工程师可新建、编辑、管理和发布场景，拥有全部场景操作权限；管理者增加系统高级配置和人员角色管理权限。场景权限管理由工作区所有者或对应场景管理者维护，所有者保留本工作区全部场景的管理权限。
                  </p>
                </div>
              </Drawer>
              <Drawer
                open={panel === "history"}
                onClose={closePanel}
                side="right"
                width="md"
                title="权限操作记录"
                closeLabel="关闭权限操作记录"
              >
                <div className="scene-permissions-content">
                  <PermissionHistory {...{ data, labels }} />
                </div>
              </Drawer>
            </>
          }
          request={
            <section aria-label="申请协作权限">
              <h3>申请协作权限</h3>
              <p>
                你可以查看当前数据范围内的场景。如需管理资料、构建或发布，请申请协作权限，由工作区所有者或管理者分配角色。
              </p>
              <Button
                disabled={busy || data.requested}
                onClick={() => void submit()}
              >
                {requestLabel(data.requested, busy)}
              </Button>
              {data.requested && (
                <p>
                  请联系工作区所有者或管理者处理；授权后刷新页面以使用对应功能。
                </p>
              )}
            </section>
          }
        />
      )}
    </div>
  );
}

function PermissionState({
  canManage,
  editorOnly,
  editor,
  manager,
  request,
}: {
  readonly canManage: boolean;
  readonly editorOnly: boolean;
  readonly editor: React.ReactNode;
  readonly manager: React.ReactNode;
  readonly request: React.ReactNode;
}) {
  if (canManage) return editorOnly ? editor : manager;
  if (editorOnly)
    return <p role="alert">当前无权分配成员角色，请关闭面板并重新读取权限。</p>;
  return request;
}

type BrowseQuery = {
  members_q: string;
  scenes_q: string;
  member_offset: number;
  scene_offset: number;
  grant_offset: number;
};
type EditorProps = {
  lockedSubject?: boolean;
  query: BrowseQuery;
  browse: (next: Partial<BrowseQuery>) => void;
  data: Access;
  busy: boolean;
  error: string;
  subject: string;
  space: string;
  role: Role | "none";
  reason: string;
  current: string;
  labels: Record<string, string>;
  choose: (subject: string, space: string) => void;
  setRole: (role: Role | "none") => void;
  setReason: (reason: string) => void;
  submit: (event?: React.FormEvent) => Promise<void>;
};

function PermissionEditor({
  lockedSubject,
  data,
  busy,
  error,
  subject,
  space,
  role,
  reason,
  current,
  labels,
  choose,
  setRole,
  setReason,
  submit,
  query,
  browse,
}: Readonly<EditorProps>) {
  const members = data.members ?? [],
    scenes = data.scenes ?? [];
  return (
    <section aria-label="成员场景授权">
      <h3>分配场景权限</h3>
      <p>
        选择成员和你可管理的场景，核对角色后填写调整原因。成员默认可查看场景。
      </p>
      <div className="permission-search">
        <label>
          查找成员
          <Input
            aria-label="搜索授权成员"
            value={query.members_q}
            onChange={(e) =>
              browse({ members_q: e.target.value, member_offset: 0 })
            }
          />
        </label>
        <PageControls
          total={data.member_total || 0}
          offset={query.member_offset}
          busy={busy}
          onPage={(member_offset) => browse({ member_offset })}
        />
        <label>
          查找场景
          <Input
            aria-label="搜索授权场景"
            value={query.scenes_q}
            onChange={(e) =>
              browse({ scenes_q: e.target.value, scene_offset: 0 })
            }
          />
        </label>
        <PageControls
          total={data.scene_total || 0}
          offset={query.scene_offset}
          busy={busy}
          onPage={(scene_offset) => browse({ scene_offset })}
        />
      </div>
      <form onSubmit={submit} className="scene-permissions-form">
        <label>
          成员
          <NativeSelect
            aria-label="授权成员"
            value={subject}
            disabled={busy || lockedSubject}
            onChange={(e) => choose(e.target.value, space)}
          >
            <option value="">选择成员</option>
            {subject && !members.some((m) => m.subject === subject) && (
              <option value={subject}>已选成员</option>
            )}
            {members.map((m) => (
              <option key={m.subject} value={m.subject}>
                {displayText(m.display_name, "成员名称待补全")}
              </option>
            ))}
          </NativeSelect>
        </label>
        <label>
          场景
          <NativeSelect
            aria-label="授权场景"
            value={space}
            disabled={busy}
            onChange={(e) => choose(subject, e.target.value)}
          >
            <option value="">选择场景</option>
            {space && !scenes.some((s) => s.id === space) && (
              <option value={space}>已选场景</option>
            )}
            {scenes.map((s) => (
              <option key={s.id} value={s.id}>
                {displayText(s.name, "场景名称待补全")}
              </option>
            ))}
          </NativeSelect>
        </label>
        <label>
          角色
          <NativeSelect
            aria-label="场景角色"
            value={role}
            disabled={busy || !subject || !space}
            onChange={(e) => setRole(e.target.value as Role | "none")}
          >
            {Object.entries(labels).map(([key, label]) => (
              <option key={key} value={key}>
                {label}
              </option>
            ))}
          </NativeSelect>
        </label>
        {subject && space && (
          <p>
            当前角色：{labels[current]}。
            {data.default_role === "viewer"
              ? "选择“默认查看者”会撤销额外操作权限，仍保留场景查看。"
              : "选择“无权限”会撤销场景授权。"}
          </p>
        )}
        <label>
          调整原因
          <Input
            aria-label="权限调整原因"
            maxLength={500}
            required
            value={reason}
            disabled={busy}
            onChange={(e) => setReason(e.target.value)}
          />
        </label>
        <Button
          type="submit"
          disabled={
            busy ||
            !!error ||
            !subject ||
            !space ||
            !reason.trim() ||
            role === current
          }
        >
          {busy ? "正在保存…" : "保存场景权限"}
        </Button>
      </form>
    </section>
  );
}

function PermissionGrants({
  data,
  busy,
  labels,
  choose,
  query,
  browse,
}: Readonly<
  Pick<EditorProps, "data" | "busy" | "labels" | "choose" | "query" | "browse">
>) {
  return (
    <section aria-label="场景授权记录">
      <PageControls
        total={data.grant_total || 0}
        offset={query.grant_offset}
        busy={busy}
        onPage={(grant_offset) => browse({ grant_offset })}
      />
      <div className="management-member-table">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>成员</TableHead>
              <TableHead>场景范围</TableHead>
              <TableHead>角色</TableHead>
              <TableHead data-table-actions>操作</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {data.grants?.map((g) => (
              <TableRow key={g.subject + g.space_id}>
                <TableCell>
                  {displayText(g.display_name, "成员名称待补全")}
                </TableCell>
                <TableCell>
                  {displayText(g.scene_name, "场景名称待补全")}
                </TableCell>
                <TableCell>{labels[g.role]}</TableCell>
                <TableCell data-table-actions>
                  <Button
                    size="sm"
                    variant="ghost"
                    disabled={busy}
                    onClick={() => choose(g.subject, g.space_id)}
                  >
                    调整授权
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
      {!data.grants?.length && (
        <p>暂无额外授权；成员默认查看者 · 受数据范围限制。</p>
      )}
    </section>
  );
}

function PermissionHistory({
  data,
  labels,
}: Readonly<Pick<EditorProps, "data" | "labels">>) {
  return (
    <section aria-label="权限操作记录">
      <h3>最近操作</h3>
      {!data.history?.length ? (
        <p>暂无权限调整记录。</p>
      ) : (
        <ul>
          {data.history.map((h) => (
            <li key={h.revision}>
              <span>
                {displayText(h.display_name, "成员名称待补全")} ·{" "}
                {displayText(h.scene_name, "场景名称待补全")}：
                {labels[h.previous_role || "none"]} → {labels[h.role || "none"]}
                <br />
                {displayText(h.reason, "已记录调整原因")}
                <br />
                <small>
                  操作人 {displayText(h.actor_name, "操作人名称待补全")} ·{" "}
                  {new Date(h.changed_at).toLocaleString("zh-CN", {
                    timeZone: "Asia/Shanghai",
                    hour12: false,
                  })}
                </small>
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function permissionFailure(status: number) {
  if (status === 409) return "权限已被其他管理员调整，请重新读取后核对。";
  if (status === 403) return "当前无权执行此操作，请重新读取权限。";
  return "提交结果暂无法确认，请重新读取后核对。";
}
async function savePermission(
  data: Access,
  {
    subject,
    space,
    role,
    reason,
  }: Readonly<Pick<EditorProps, "subject" | "space" | "role" | "reason">>,
) {
  const response = await fetch(
    endpoint + (data.can_manage ? "/grants" : "/requests"),
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(
        data.can_manage
          ? {
              expected_revision: data.revision,
              subject,
              space_id: space,
              role: role === "none" ? null : role,
              reason: reason.trim(),
            }
          : {},
      ),
    },
  );
  if (!response.ok) throw new Error(permissionFailure(response.status));
}

function PageControls({
  total,
  offset,
  busy,
  onPage,
}: {
  readonly total: number;
  readonly offset: number;
  readonly busy: boolean;
  readonly onPage: (offset: number) => void;
}) {
  return (
    <div className="permission-pages">
      <span>共 {total} 项</span>
      <Button
        size="sm"
        variant="ghost"
        disabled={busy || offset === 0}
        onClick={() => onPage(Math.max(0, offset - 25))}
      >
        上一页
      </Button>
      <Button
        size="sm"
        variant="ghost"
        disabled={busy || offset + 25 >= total}
        onClick={() => onPage(offset + 25)}
      >
        下一页
      </Button>
    </div>
  );
}

function requestLabel(requested: boolean, busy: boolean) {
  if (requested) return "已申请协作权限";
  return busy ? "正在提交…" : "申请协作权限";
}
