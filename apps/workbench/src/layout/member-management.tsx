import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  Button,
  Drawer,
  Input,
  NativeSelect,
  TableTitleCell,
} from "@vxture/design-system";
import { usePlatformSession } from "./platform-auth";
import { sessionScopeKey } from "./session-continuity";
import { businessEndpoint } from "./business-endpoint";
import { displayText } from "./display-text";
import { runGuarded } from "./unsaved-navigation";
import { ScenePermissionsPanel } from "./scene-permissions";
import { productRoleDefinitions } from "./management-contract";
import { RoleDefinitions } from "./management-overview";
import { ManagementList, MemberTitle, RoleBadges } from "./management-list";

type Role = "viewer" | "engineer" | "manager";
type Member = {
  subject: string;
  display_name: string;
  requested_at: string | null;
  last_seen?: string;
  roles: (Role | "owner")[];
  scene_count: number;
};
type Directory = {
  workspace_id: string;
  can_manage: boolean;
  members?: Member[];
  member_total?: number;
  role_counts?: Partial<Record<Role, number>>;
  directory_complete?: boolean;
};
const labels: Record<Role, string> = {
  viewer: "查看者",
  engineer: "工程师",
  manager: "管理者",
};
export function MemberManagement({
  role,
  assignmentRole,
}: {
  readonly role?: Role;
  readonly assignmentRole?: Role;
}) {
  const session = usePlatformSession();
  if (!session) return <p>登录后可查看成员管理。</p>;
  return (
    <MemberDirectory
      key={sessionScopeKey(session) + (role || "all")}
      role={role}
      assignmentRole={assignmentRole}
    />
  );
}
function MemberDirectory({
  role,
  assignmentRole,
}: {
  readonly role?: Role;
  readonly assignmentRole?: Role;
}) {
  const session = usePlatformSession();
  const [saving, setSaving] = useState(false),
    [directoryInfo, setDirectoryInfo] = useState(false);
  const [query, setQuery] = useState(""),
    [filter, setFilter] = useState<Role | "">(role || ""),
    [offset, setOffset] = useState(0),
    [refresh, setRefresh] = useState(0);
  const [data, setData] = useState<Directory | null>(null),
    [loading, setLoading] = useState(true),
    [error, setError] = useState(""),
    [selected, setSelected] = useState<Member | null>(null),
    [mode, setMode] = useState<"details" | "assign">("details");
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError("");
    setData(null);
    const params = new URLSearchParams({
      members_q: query,
      member_offset: String(offset),
      role: filter,
    });
    fetch(businessEndpoint + "/api/scene-permissions?" + params, {
      cache: "no-store",
      signal: controller.signal,
    })
      .then(async (response) => {
        if (!response.ok) throw Error("成员信息暂不可读，请重新读取。");
        const value: Directory = await response.json();
        if (
          value.workspace_id !== session?.user?.workspace_id ||
          typeof value.can_manage !== "boolean"
        )
          throw Error("成员范围无法确认，请重新读取。");
        if (!controller.signal.aborted) setData(value);
      })
      .catch((e) => {
        if (!controller.signal.aborted)
          setError(e instanceof Error ? e.message : "成员信息暂不可读。");
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [query, filter, offset, refresh, session?.user?.workspace_id]);
  function browse(action: () => void) {
    void runGuarded(() => {
      setSelected(null);
      action();
    });
  }
  return (
    <div className="member-management">
      <Drawer
        open={directoryInfo}
        onClose={() => setDirectoryInfo(false)}
        side="right"
        width="md"
        title="成员名单说明"
        closeLabel="关闭名单说明"
      >
        <p className="management-directory-notice">
          {data?.directory_complete
            ? "名单来自平台当前工作区已获准使用 CoSpace 的成员，包含尚未访问本产品的成员。角色与场景范围由 CoSpace 分配；平台撤权后不会删除历史角色记录，产品访问仍由平台独立校验。"
            : "当前仅展示本产品访问、协作申请及已授权记录中的成员，不代表完整平台名单。产品访问仍由平台校验。"}
        </p>
      </Drawer>

      {error && (
        <div role="alert" className="management-load-error">
          <p>{error}</p>
          <Button
            variant="outline"
            size="sm"
            onClick={() => setRefresh((value) => value + 1)}
          >
            重新读取成员
          </Button>
        </div>
      )}
      {loading && <p role="status">正在读取成员…</p>}
      {data && !data.can_manage && (
        <p>
          当前角色无权查看成员清单或分配角色。
          <Link
            to="/settings?section=scenes"
            className="text-primary underline"
          >
            查看协作权限
          </Link>
        </p>
      )}
      {(loading || data?.can_manage) && (
        <MemberTable
          data={data || { workspace_id: "", can_manage: false }}
          {...{ loading, offset }}
          toolbar={
            <div className="management-member-toolbar">
              <label>
                <span className="sr-only">搜索成员</span>
                <Input
                  aria-label="搜索产品成员"
                  placeholder="按成员名称搜索"
                  value={query}
                  onChange={(e) => {
                    const value = e.target.value;
                    browse(() => {
                      setQuery(value);
                      setOffset(0);
                    });
                  }}
                />
              </label>
              {!role && (
                <label>
                  <span className="sr-only">产品角色</span>
                  <NativeSelect
                    aria-label="筛选产品角色"
                    value={filter}
                    onChange={(e) => {
                      const value = e.target.value as Role | "";
                      browse(() => {
                        setFilter(value);
                        setOffset(0);
                      });
                    }}
                  >
                    <option value="">全部角色</option>
                    {Object.entries(labels).map(([key, label]) => (
                      <option key={key} value={key}>
                        {label}
                      </option>
                    ))}
                  </NativeSelect>
                </label>
              )}
              <Button
                variant="outline"
                size="sm"
                disabled={loading}
                onClick={() => browse(() => setRefresh((value) => value + 1))}
              >
                重新读取成员
              </Button>
            </div>
          }
          action={
            <Button
              variant="outline"
              size="sm"
              onClick={() => setDirectoryInfo(true)}
            >
              名单说明
            </Button>
          }
          onSelect={(member, mode) =>
            void runGuarded(() => {
              setSelected(member);
              setMode(mode);
            })
          }
          onPage={(value) => browse(() => setOffset(value))}
        />
      )}
      <Drawer
        open={!!selected && !!data?.can_manage}
        onClose={() => {
          if (!saving)
            void runGuarded(() => {
              setSelected(null);
              setRefresh((value) => value + 1);
            });
        }}
        side="right"
        width="min(600px, 100vw)"
        title={mode === "details" ? "成员详情" : "分配成员角色"}
        description={
          selected
            ? displayText(selected.display_name, "成员名称待补全")
            : undefined
        }
        closeLabel="关闭成员面板"
      >
        {selected &&
          data?.can_manage &&
          (mode === "details" ? (
            <div className="management-drawer-content">
              <dl className="management-information">
                <div>
                  <dt>成员</dt>
                  <dd>
                    {displayText(selected.display_name, "成员名称待补全")}
                  </dd>
                </div>
                <div>
                  <dt>产品角色</dt>
                  <dd>
                    {selected.roles
                      .map((value) =>
                        value === "owner" ? "所有者" : labels[value],
                      )
                      .join("、") || "默认查看者"}
                  </dd>
                </div>
                <div>
                  <dt>已授权场景</dt>
                  <dd>{selected.scene_count} 个</dd>
                </div>
                <div>
                  <dt>最近访问</dt>
                  <dd>
                    {selected.last_seen
                      ? new Date(selected.last_seen).toLocaleString("zh-CN")
                      : "暂无记录"}
                  </dd>
                </div>
              </dl>
              <p>
                角色与授权场景数仅统计你可管理的范围。平台使用资格由平台维护。
              </p>
              {!selected.roles.includes("owner") && (
                <Button onClick={() => setMode("assign")}>分配角色</Button>
              )}
            </div>
          ) : (
            <ScenePermissionsPanel
              initialSubject={selected.subject}
              initialRole={assignmentRole || role}
              editorOnly
              onBusyChange={setSaving}
              onSaved={() => {
                setSelected(null);
                setRefresh((value) => value + 1);
              }}
            />
          ))}
      </Drawer>
    </div>
  );
}
function MemberTable({
  data,
  loading,
  offset,
  toolbar,
  action,
  onPage,
  onSelect,
}: {
  readonly data: Directory;
  readonly loading: boolean;
  readonly offset: number;
  readonly toolbar: React.ReactNode;
  readonly action: React.ReactNode;
  readonly onPage: (value: number) => void;
  readonly onSelect: (member: Member, mode: "details" | "assign") => void;
}) {
  return (
    <ManagementList
      title="成员清单"
      icon="users"
      count={loading ? undefined : data.member_total || 0}
      {...{ loading, offset, toolbar, action, onPage }}
      rows={data.members || []}
      rowKey={(member) => member.subject}
      empty="没有匹配的成员。"
      columns={[
        {
          id: "member",
          header: "成员",
          cell: (member) => (
            <MemberTitle
              name={displayText(member.display_name, "成员名称待补全")}
              description={
                member.requested_at
                  ? "已提交协作申请"
                  : member.last_seen
                    ? "最近访问 " +
                      new Date(member.last_seen).toLocaleDateString("zh-CN")
                    : "尚未访问"
              }
              onClick={() => onSelect(member, "details")}
            />
          ),
        },
        {
          id: "roles",
          header: "产品角色",
          width: "sm",
          cell: (member) => (
            <RoleBadges
              roles={
                member.roles
                  .map((value) =>
                    value === "owner" ? "所有者" : labels[value],
                  )
                  .filter(Boolean).length
                  ? member.roles
                      .map((value) =>
                        value === "owner" ? "所有者" : labels[value],
                      )
                      .filter(Boolean)
                  : ["查看者"]
              }
            />
          ),
        },
        {
          id: "scenes",
          header: "已授权场景",
          align: "numeric",
          width: "xs",
          cell: (member) => member.scene_count + " 个",
        },
      ]}
      actions={(member) => [
        {
          id: "details",
          label: "成员详情",
          onSelect: () => onSelect(member, "details"),
        },
        ...(!member.roles.includes("owner")
          ? [
              {
                id: "assign",
                label: "分配角色",
                onSelect: () => onSelect(member, "assign"),
              },
            ]
          : []),
      ]}
    />
  );
}
export function RoleManagement() {
  const [selected, setSelected] = useState<string | null>(null);
  return (
    <>
      <ManagementList
        title="角色清单"
        icon="user"
        count={productRoleDefinitions.length}
        rows={productRoleDefinitions}
        rowKey={(item) => item.role}
        columns={[
          {
            id: "role",
            header: "角色",
            width: "md",
            cell: (item) => (
              <button
                type="button"
                className="management-title-button"
                onClick={() => setSelected(item.role)}
              >
                <TableTitleCell
                  title={item.role}
                  description={
                    item.role === "查看者"
                      ? "新成员默认角色"
                      : item.role === "所有者"
                        ? "平台工作区所有者"
                        : "产品预置角色"
                  }
                />
              </button>
            ),
          },
          { id: "scene", header: "场景操作", cell: (item) => item.scene },
          { id: "scope", header: "生效范围", cell: (item) => item.scope },
        ]}
        actions={(item) => [
          {
            id: "details",
            label: "角色详情",
            onSelect: () => setSelected(item.role),
          },
        ]}
      />
      <Drawer
        open={!!selected}
        onClose={() => setSelected(null)}
        side="right"
        width="md"
        title="角色详情"
        description={selected || undefined}
        closeLabel="关闭角色详情"
      >
        {selected && (
          <div className="management-drawer-content">
            <RoleDefinitions role={selected} />
            <Link
              to="/settings?section=members"
              className="text-primary underline"
            >
              前往成员管理
            </Link>
          </div>
        )}
      </Drawer>
    </>
  );
}
