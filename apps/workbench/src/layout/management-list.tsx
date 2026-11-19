import React from "react";
import {
  ActionMenu,
  DataTable,
  EmptyState,
  Pagination,
  Section,
  StatusBadge,
  TableTitleCell,
  UserAvatar,
  type ActionMenuItem,
  type DataTableColumn,
  type IconName,
} from "@vxture/design-system";

/** The same list fittings used by Yucer: numbered rows, one action menu and a shared footer. */
export function ManagementList<Row>({
  title,
  icon,
  count,
  action,
  toolbar,
  rows,
  columns,
  rowKey,
  actions,
  offset = 0,
  onPage,
  loading = false,
  empty = "没有匹配的记录。",
}: {
  readonly title: string;
  readonly icon: IconName;
  readonly count?: React.ReactNode;
  readonly action?: React.ReactNode;
  readonly toolbar?: React.ReactNode;
  readonly rows: readonly Row[];
  readonly columns: readonly DataTableColumn<Row>[];
  readonly rowKey: (row: Row) => string;
  readonly actions: (row: Row) => readonly ActionMenuItem[];
  readonly offset?: number;
  readonly onPage?: (offset: number) => void;
  readonly loading?: boolean;
  readonly empty?: string;
}) {
  return (
    <Section
      className="management-list"
      title={
        <span className="management-list-title">
          {title}
          {count !== undefined && (
            <span className="management-list-count">{count}</span>
          )}
        </span>
      }
      icon={icon}
      action={action}
    >
      {toolbar && <div className="management-list-toolbar">{toolbar}</div>}
      <DataTable
        className="management-data-table"
        labels={{ rowActions: "操作" }}
        rows={rows}
        columns={columns}
        rowKey={rowKey}
        indexStart={offset + 1}
        loading={loading}
        loadingRows={4}
        rowActions={(row) => (
          <ActionMenu label="更多操作" items={actions(row)} />
        )}
        empty={<EmptyState title={empty} />}
      />
      {onPage && typeof count === "number" && (
        <Pagination
          countLabel={`共 ${count} 条记录`}
          total={count}
          page={Math.floor(offset / 25) + 1}
          pageCount={Math.max(1, Math.ceil(count / 25))}
          onPageChange={(page) => {
            if (!loading) onPage((page - 1) * 25);
          }}
          firstLabel="首页"
          previousLabel="上一页"
          nextLabel="下一页"
          lastLabel="末页"
        />
      )}
    </Section>
  );
}
export function MemberTitle({
  name,
  description,
  onClick,
}: {
  readonly name: string;
  readonly description?: string;
  readonly onClick: () => void;
}) {
  return (
    <button
      type="button"
      className="management-member-title"
      aria-label={`${name} · 成员详情`}
      onClick={onClick}
    >
      <UserAvatar alt={name} className="size-8 shrink-0" />
      <TableTitleCell title={name} tooltip={name} description={description} />
    </button>
  );
}
export function RoleBadges({ roles }: { readonly roles: readonly string[] }) {
  return (
    <div className="management-role-badges">
      {roles.map((role) => (
        <StatusBadge key={role} tone={role === "查看者" ? "neutral" : "info"}>
          {role}
        </StatusBadge>
      ))}
    </div>
  );
}
