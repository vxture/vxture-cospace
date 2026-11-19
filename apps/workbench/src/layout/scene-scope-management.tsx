import React, { useEffect, useState, useRef } from "react";
import {
  Button,
  Drawer,
  Input,
  NativeSelect,
  Checkbox,
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
import { displayText } from "./display-text";
import { runGuarded, useUnsavedNavigation } from "./unsaved-navigation";

type Member = {
  subject: string;
  display_name: string;
  roles: string[];
  data_scope: "all" | "selected";
  scope_scene_ids: string[];
};
type ScopeData = {
  workspace_id: string;
  revision: number;
  can_manage: boolean;
  can_manage_scope: boolean;
  members?: Member[];
  member_total?: number;
  scenes?: { id: string; name: string }[];
  scene_total?: number;
  selected_member?: Member;
  directory_complete?: boolean;
};
const endpoint = businessEndpoint + "/api/scene-permissions";
export function SceneScopeManagement() {
  const session = usePlatformSession();
  if (!session) return <p>登录后可查看场景数据范围。</p>;
  return <ScopeDirectory key={sessionScopeKey(session)} />;
}
function ScopeDirectory() {
  const session = usePlatformSession();
  const [data, setData] = useState<ScopeData | null>(null),
    [query, setQuery] = useState(""),
    [offset, setOffset] = useState(0),
    [refresh, setRefresh] = useState(0),
    [error, setError] = useState("");
  const [selected, setSelected] = useState<Member | null>(null),
    [edit, setEdit] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    setData(null);
    setError("");
    fetch(
      endpoint +
        "?" +
        new URLSearchParams({
          members_q: query,
          member_offset: String(offset),
        }),
      { cache: "no-store", signal: controller.signal },
    )
      .then(async (response) => {
        if (!response.ok) throw new Error("无法读取数据范围，请重试。");
        const value: ScopeData = await response.json();
        if (value.workspace_id !== session?.user?.workspace_id)
          throw new Error("工作区范围无法确认。");
        if (!controller.signal.aborted) setData(value);
      })
      .catch((e) => {
        if (!controller.signal.aborted) setError(e.message);
      });
    return () => controller.abort();
  }, [query, offset, refresh, session?.user?.workspace_id]);
  return (
    <>
      <div className="management-card-heading">
        <h2>成员数据范围</h2>
        <span className="text-body-small text-muted-foreground">
          {data?.member_total || 0} 位{data?.directory_complete?'平台授权成员':'已记录成员'}
        </span>
      </div>
      <div className="management-member-toolbar">
        <label>
          搜索成员
          <Input
            aria-label="搜索数据范围成员"
            value={query}
            placeholder="按成员名称搜索"
            onChange={(e) => {
              setQuery(e.target.value);
              setOffset(0);
            }}
          />
        </label>
        <Button
          variant="outline"
          disabled={!data}
          onClick={() => setRefresh((value) => value + 1)}
        >
          重新读取
        </Button>
      </div>
      {error && <p role="alert">{error}</p>}
      {!data && !error && <output>正在读取数据范围…</output>}
      {data && !data.can_manage && (
        <p>当前角色无权查看成员数据范围。你的可见场景以“我的场景”列表为准。</p>
      )}
      {data?.can_manage && (
        <>
          <div className="management-member-table">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>成员</TableHead>
                  <TableHead>场景数据范围</TableHead>
                  <TableHead>覆盖</TableHead>
                  <TableHead data-table-actions>操作</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.members?.map((member) => (
                  <TableRow key={member.subject}>
                    <TableCell>
                      {displayText(member.display_name, "成员名称待补全")}
                    </TableCell>
                    <TableCell>
                      {member.data_scope === "selected"
                        ? "指定场景"
                        : "整个工作区"}
                    </TableCell>
                    <TableCell>
                      {member.data_scope === "selected"
                        ? member.scope_scene_ids.length + " 个场景"
                        : "当前及后续场景"}
                    </TableCell>
                    <TableCell data-table-actions>
                      <div className="management-row-actions">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => {
                            setSelected(member);
                            setEdit(false);
                          }}
                        >
                          查看详情
                        </Button>
                        {data.can_manage_scope &&
                          !member.roles.includes("owner") && (
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => {
                                setSelected(member);
                                setEdit(true);
                              }}
                            >
                              设置范围
                            </Button>
                          )}
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
          {!data.members?.length && <p>没有匹配的成员。</p>}
          <div className="permission-pages">
            <span>共 {data.member_total || 0} 位</span>
            <Button
              variant="ghost"
              disabled={!offset}
              onClick={() => setOffset((value) => Math.max(0, value - 25))}
            >
              上一页
            </Button>
            <Button
              variant="ghost"
              disabled={offset + 25 >= (data.member_total || 0)}
              onClick={() => setOffset((value) => value + 25)}
            >
              下一页
            </Button>
          </div>
          <p className="text-body-small text-muted-foreground">
            数据范围限定可见场景，功能角色决定可执行操作。
            {data.directory_complete?'成员名单来自平台当前产品授权。':'当前仅展示本产品已记录成员。'}
          </p>
          {!data.can_manage_scope && (
            <p className="text-body-small text-muted-foreground">
              工作区级数据范围由所有者维护；当前仅展示你可管理范围内的已知成员。
            </p>
          )}
        </>
      )}
      {selected && data?.can_manage && (
        <ScopeDrawer
          member={selected}
          edit={edit}
          canEdit={data.can_manage_scope}
          onClose={() => setSelected(null)}
          onSaved={() => {
            setSelected(null);
            setRefresh((value) => value + 1);
          }}
        />
      )}
    </>
  );
}
function ScopeDrawer({
  member,
  edit,
  canEdit,
  onClose,
  onSaved,
}: {
  readonly member: Member;
  readonly edit: boolean;
  readonly canEdit: boolean;
  readonly onClose: () => void;
  readonly onSaved: () => void;
}) {
  const session = usePlatformSession();
  const firstRead = useRef(true),
    expectedRevision = useRef(0),
    baseline = useRef(member);
  const [data, setData] = useState<ScopeData | null>(null),
    [mode, setMode] = useState(member.data_scope),
    [ids, setIds] = useState(member.scope_scene_ids),
    [reason, setReason] = useState(""),
    [query, setQuery] = useState(""),
    [offset, setOffset] = useState(0),
    [busy, setBusy] = useState(false),
    [loading, setLoading] = useState(true),
    [error, setError] = useState("");
  const changed =
    mode !== baseline.current.data_scope ||
    JSON.stringify([...ids].sort((a, b) => a.localeCompare(b))) !==
      JSON.stringify(
        [...baseline.current.scope_scene_ids].sort((a, b) =>
          a.localeCompare(b),
        ),
      );
  const acknowledge = useUnsavedNavigation(
    edit && (changed || !!reason),
    "成员数据范围",
  );
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError("");
    fetch(
      endpoint +
        "?" +
        new URLSearchParams({
          subject: member.subject,
          scenes_q: query,
          scene_offset: String(offset),
          scope_only: String(!edit),
        }),
      { cache: "no-store", signal: controller.signal },
    )
      .then(async (response) => {
        if (!response.ok) throw new Error("数据范围暂不可读。");
        const value: ScopeData = await response.json();
        if (value.workspace_id !== session?.user?.workspace_id)
          throw new Error("工作区范围无法确认。");
        if (!controller.signal.aborted) {
          if (firstRead.current) {
            if (!value.selected_member) throw new Error("成员范围无法确认。");
            baseline.current = value.selected_member;
            setMode(value.selected_member.data_scope);
            setIds(value.selected_member.scope_scene_ids);
            expectedRevision.current = value.revision;
            firstRead.current = false;
          }
          setData(value);
        }
      })
      .catch((e) => {
        if (!controller.signal.aborted) setError(e.message);
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [query, offset, member.subject, session?.user?.workspace_id, edit]);
  async function save(event: React.FormEvent) {
    event.preventDefault();
    if (busy || loading || !data?.can_manage_scope || !changed) return;
    setBusy(true);
    setError("");
    try {
      const response = await fetch(endpoint + "/scopes", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          expected_revision: expectedRevision.current,
          subject: member.subject,
          space_ids: mode === "all" ? null : ids,
          reason: reason.trim(),
        }),
      });
      if (!response.ok) throw new Error(scopeFailure(response.status));
      acknowledge();
      onSaved();
    } catch (e) {
      setError(e instanceof Error ? e.message : "保存失败。");
    } finally {
      setBusy(false);
    }
  }
  return (
    <Drawer
      open
      onClose={() => {
        if (!busy) void runGuarded(onClose);
      }}
      side="right"
      width="min(600px, 100vw)"
      title={edit ? "设置数据范围" : "数据范围详情"}
      description={displayText(member.display_name, "成员名称待补全")}
      closeLabel="关闭数据范围面板"
    >
      <div className="management-drawer-content">
        {error && <p role="alert">{error}</p>}
        {loading && <output>正在验证权限与读取范围…</output>}
        {!edit && (
          <>
            <p>
              场景数据范围：
              {mode === "all" ? "整个工作区" : `指定 ${ids.length} 个场景`}。
            </p>
            <p>
              拥有功能权限，也只能访问数据范围内的场景。整个工作区包括后续新增场景；指定场景不会自动扩展。
            </p>
            <p>
              该设置按完整场景限制访问，不支持同一场景内部按字段或对象裁剪数据。
            </p>
            {data?.can_manage_scope && (
              <>
                <label>
                  查找范围内场景
                  <Input
                    aria-label="查找范围内场景"
                    value={query}
                    onChange={(e) => {
                      setQuery(e.target.value);
                      setOffset(0);
                    }}
                  />
                </label>
                <ul>
                  {data.scenes?.map((scene) => (
                    <li key={scene.id}>
                      {displayText(scene.name, "场景名称待补全")}
                    </li>
                  ))}
                </ul>
                <div className="permission-pages">
                  <span>共 {data.scene_total || 0} 个场景</span>
                  <Button
                    variant="ghost"
                    disabled={loading || !offset}
                    onClick={() =>
                      setOffset((value) => Math.max(0, value - 25))
                    }
                  >
                    上一页
                  </Button>
                  <Button
                    variant="ghost"
                    disabled={loading || offset + 25 >= (data.scene_total || 0)}
                    onClick={() => setOffset((value) => value + 25)}
                  >
                    下一页
                  </Button>
                </div>
              </>
            )}
          </>
        )}
        {edit && canEdit && data?.can_manage_scope && (
          <form className="scene-permissions-form" onSubmit={save}>
            <label>
              场景数据范围
              <NativeSelect
                aria-label="场景数据范围"
                value={mode}
                disabled={busy}
                onChange={(e) => setMode(e.target.value as "all" | "selected")}
              >
                <option value="all">整个工作区</option>
                <option value="selected">指定场景</option>
              </NativeSelect>
            </label>
            {mode === "selected" && (
              <>
                <label>
                  搜索场景
                  <Input
                    aria-label="搜索范围场景"
                    value={query}
                    disabled={busy}
                    onChange={(e) => {
                      setQuery(e.target.value);
                      setOffset(0);
                    }}
                  />
                </label>
                <p>已选择 {ids.length} 个场景；选择零个将无法查看任何场景。</p>
                <div className="management-scope-choices">
                  {data.scenes?.map((scene) => (
                    <label key={scene.id}>
                      <Checkbox
                        checked={ids.includes(scene.id)}
                        disabled={busy || loading}
                        onCheckedChange={(checked) =>
                          setIds((value) =>
                            checked
                              ? [...value, scene.id]
                              : value.filter((id) => id !== scene.id),
                          )
                        }
                      />
                      {displayText(scene.name, "场景名称待补全")}
                    </label>
                  ))}
                </div>
                <div className="permission-pages">
                  <Button
                    type="button"
                    variant="ghost"
                    disabled={busy || loading || !offset}
                    onClick={() =>
                      setOffset((value) => Math.max(0, value - 25))
                    }
                  >
                    上一页
                  </Button>
                  <Button
                    type="button"
                    variant="ghost"
                    disabled={
                      busy || loading || offset + 25 >= (data.scene_total || 0)
                    }
                    onClick={() => setOffset((value) => value + 25)}
                  >
                    下一页
                  </Button>
                </div>
              </>
            )}
            <label>
              调整原因
              <Input
                aria-label="范围调整原因"
                required
                maxLength={500}
                value={reason}
                disabled={busy}
                onChange={(e) => setReason(e.target.value)}
              />
            </label>
            <p>此处只调整可见的数据范围，不增加查看、编辑或发布等功能权限。</p>
            <div className="management-row-actions">
              <Button
                type="button"
                variant="ghost"
                disabled={busy}
                onClick={() => void runGuarded(onClose)}
              >
                取消
              </Button>
              <Button
                type="submit"
                disabled={
                  busy || loading || !!error || !changed || !reason.trim()
                }
              >
                {busy ? "正在保存…" : "保存数据范围"}
              </Button>
            </div>
          </form>
        )}
        {edit && !loading && !data?.can_manage_scope && (
          <p>当前无权修改数据范围。</p>
        )}
      </div>
    </Drawer>
  );
}

function scopeFailure(status: number) {
  if (status === 409) return "授权已发生变更，请关闭面板后重新读取。";
  if (status === 403) return "当前无权调整此成员的数据范围。";
  return "保存失败，请重新读取后核对。";
}
