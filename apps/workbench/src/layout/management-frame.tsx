import { ShellSidebarNav } from "./shell-navigation";
import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  Button,
  Drawer,
  ShellSidebarFrame,
  ViewHeader,
  ViewLayout,
  Popover,
  PopoverTrigger,
  PopoverContent,
  useMediaQuery,
  type ShellNavSection,
  type IconName,
} from "@vxture/design-system";
import {
  SidebarSimple,
  ArrowLeft,
  CaretRight,
  Question,
} from "@phosphor-icons/react";
import { useRecordNavigation } from "./record-navigation";
import { appLocation, appNavigate } from "./app-router";
import {
  managementPages,
  managementPage,
  managementHref,
  managementSections,
  managementSection,
} from "./management-contract";
import "./scene-catalog.css";
import "./spatial-services.css";
import "./management-frame.css";

const pages = {
  settings: { ...managementPages.settings, icon: "users" },
  account: { ...managementPages.account, icon: "user" },
} as const;
const ManagementLink = React.forwardRef<
  HTMLAnchorElement,
  React.AnchorHTMLAttributes<HTMLAnchorElement>
>(({ href = "", ...props }, ref) => <Link {...props} ref={ref} to={href} />);
ManagementLink.displayName = "ManagementLink";

export function ManagementFrame({
  route,
  children,
}: Readonly<{
  route: "settings" | "members" | "identity" | "account";
  children: React.ReactNode;
}>) {
  const { space } = useRecordNavigation();
  const current = managementPage(route),
    location = appLocation();
  const section = managementSection(
    new URLSearchParams(location.split("?")[1] || "").get("section") ||
      (route === "members" ? "members" : null),
  );
  const href = managementHref(route, space, section);
  useEffect(() => {
    if (location !== href) appNavigate(href, true);
  }, [href, location]);
  const [collapsed, setCollapsed] = useState(false),
    [open, setOpen] = useState(false);
  const narrow = useMediaQuery("(max-width:639px)");
  useEffect(() => setOpen(false), [route]);
  const sections: ShellNavSection[] = [
    {
      title: "概览",
      items: [
        {
          href: managementHref("settings", space),
          label: "概览",
          icon: "app-grid",
        },
        { href: "/account", label: "个人信息", icon: "user" },
      ],
    },
    {
      title: "成员权限",
      items: ["members", "roles", "permissions", "scenes"].map((key) => ({
        href: managementHref("settings", space, key),
        label:
          managementSections[
            key as "members" | "roles" | "permissions" | "scenes"
          ].label,
        icon: managementSections[
          key as "members" | "roles" | "permissions" | "scenes"
        ].icon,
      })),
    },
    {
      title: "业务配置",
      items: [
        {
          href: managementHref("settings", space, "advanced"),
          label: "高级配置",
          icon: "shield-check",
        },
      ],
    },
  ];
  const navigation = (compact: boolean, toggle: () => void) => (
    <ShellSidebarNav
      domainName="配置管理"
      sections={sections}
      collapsed={compact}
      onToggleCollapsed={toggle}
      isActive={(link) =>
        current === "account"
          ? link === "/account"
          : link.startsWith("/settings") &&
            managementSection(
              new URLSearchParams(link.split("?")[1] || "").get("section"),
            ) === section
      }
      storageKeyPrefix="cospace.management.navigation"
      linkComponent={ManagementLink}
      labels={{
        expandNav: "展开功能导航",
        collapseNav: "收起功能导航",
        expandAllGroups: "展开导航分组",
        collapseAllGroups: "收起导航分组",
      }}
    />
  );
  const page =
    current === "account" ? pages.account : managementSections[section];
  return (
    <main
      className="scene-catalog spatial-services management-domain"
      aria-label="配置管理"
    >
      {!narrow && (
        <ShellSidebarFrame mode={collapsed ? "collapsed" : "expanded"}>
          {navigation(collapsed, () => setCollapsed((value) => !value))}
        </ShellSidebarFrame>
      )}
      <div className="spatial-service-content">
        <ViewLayout className="scene-catalog-shell management-view-layout">
          {narrow && (
            <Button variant="ghost" size="sm" onClick={() => setOpen(true)}>
              <SidebarSimple size={16} />
              功能导航
            </Button>
          )}
          <nav className="management-breadcrumb" aria-label="当前位置">
            <Link
              to={managementHref("settings", space)}
              aria-label="返回配置管理"
            >
              <ArrowLeft size={16} />
            </Link>
            <Link to={managementHref("settings", space)}>配置管理</Link>
            <CaretRight size={14} />
            <span aria-current="page">{page.label}</span>
          </nav>
          <ViewHeader
            divider={false}
            icon={page.icon as IconName}
            title={page.label}
            secondary={
              <Popover>
                <PopoverTrigger asChild>
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    aria-label={`${page.label} · 帮助`}
                  >
                    <Question size={16} />
                  </Button>
                </PopoverTrigger>
                <PopoverContent align="start" className="management-page-help">
                  {page.description}
                </PopoverContent>
              </Popover>
            }
          />
          <div className="management-page-content">{children}</div>
        </ViewLayout>
      </div>
      <Drawer
        open={narrow && open}
        onClose={() => setOpen(false)}
        side="left"
        width="sm"
        title="功能导航"
        closeLabel="关闭功能导航"
      >
        {navigation(false, () => setOpen(false))}
      </Drawer>
    </main>
  );
}
