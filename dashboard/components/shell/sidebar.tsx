"use client";

import { ChevronDown, LogOut, Search, UserRound } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useTranslations } from "next-intl";
import { useEffect, useMemo, useState } from "react";

import { GuildSwitcher } from "@/components/shell/guild-switcher";
import { Avatar, Badge } from "@/components/ui";
import { useGuild, useMe } from "@/lib/hooks";
import { canSee, isAvailable, NAV_GROUPS, OVERVIEW, SHOW_UPCOMING, type NavItem } from "@/lib/nav";
import { cn } from "@/lib/utils";

import { useLogout } from "./use-logout";

const COLLAPSED_KEY = "nexus.nav.collapsed";

function readCollapsed(): Record<string, boolean> {
  try {
    return JSON.parse(localStorage.getItem(COLLAPSED_KEY) ?? "{}");
  } catch {
    return {};
  }
}

export function Sidebar({ guildId, onNavigate }: { guildId: string; onNavigate?: () => void }) {
  const t = useTranslations("nav");
  const tc = useTranslations("common");
  const pathname = usePathname();
  const { data: me } = useMe();
  const { data: guild } = useGuild(guildId);
  const logout = useLogout();
  const [query, setQuery] = useState("");
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});

  useEffect(() => setCollapsed(readCollapsed()), []);

  const toggle = (key: string) => {
    const next = { ...collapsed, [key]: !collapsed[key] };
    setCollapsed(next);
    try {
      localStorage.setItem(COLLAPSED_KEY, JSON.stringify(next));
    } catch {
      // almacenamiento no disponible: solo se pierde la preferencia
    }
  };

  const groups = useMemo(() => {
    const q = query.trim().toLowerCase();
    return NAV_GROUPS.map((g) => ({
      ...g,
      items: g.items.filter((i) => (SHOW_UPCOMING || isAvailable(i)) && canSee(i, guild) && (!q || t(`items.${i.key}`).toLowerCase().includes(q))),
    })).filter((g) => g.items.length > 0);
  }, [query, t, guild]);

  const renderItem = (item: NavItem, label: string) => {
    const href = `/dashboard/${guildId}/${item.path}`;
    const active = pathname === href;
    const available = isAvailable(item);
    const Icon = item.icon;
    const content = (
      <>
        <Icon className={cn("size-[18px] shrink-0", active ? "text-primary" : "text-muted")} aria-hidden />
        <span className="flex-1 truncate">{label}</span>
        {!available && <Badge>{tc("soon")}</Badge>}
      </>
    );
    const cls = cn(
      "relative flex min-h-10 items-center gap-3 rounded-lg px-3 text-sm transition-colors",
      active && "bg-panel-hover text-text before:absolute before:inset-y-2 before:left-0 before:w-0.5 before:rounded-full before:bg-primary",
      !active && available && "text-text/85 hover:bg-panel-hover hover:text-text",
      !available && "cursor-default text-muted/70",
    );
    if (!available) {
      return (
        <div key={item.key} className={cls} aria-disabled="true">
          {content}
        </div>
      );
    }
    return (
      <Link key={item.key} href={href} className={cls} aria-current={active ? "page" : undefined} onClick={onNavigate}>
        {content}
      </Link>
    );
  };

  return (
    <nav aria-label="NEXUS" className="flex h-full flex-col gap-3 p-3">
      <Link href="/dashboard" className="flex items-center gap-2.5 px-2 py-1.5" onClick={onNavigate}>
        <span className="grid size-9 place-items-center rounded-xl bg-primary-solid text-sm font-bold text-white">N</span>
        <span className="text-[17px] font-semibold tracking-tight">NEXUS</span>
      </Link>

      <GuildSwitcher guildId={guildId} onNavigate={onNavigate} />

      <label className="relative block">
        <span className="sr-only">{t("searchNav")}</span>
        <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted" aria-hidden />
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={t("searchNav")}
          className="min-h-9 w-full rounded-lg border border-transparent bg-bg/60 pl-9 pr-3 text-[13px] placeholder:text-muted focus:border-border focus:outline-none"
        />
      </label>

      <div className="-mx-1 flex-1 space-y-4 overflow-y-auto px-1">
        {!query && renderItem(OVERVIEW, t("overview"))}
        {groups.map((g) => {
          const isCollapsed = !query && collapsed[g.key];
          return (
            <div key={g.key}>
              <button
                type="button"
                onClick={() => toggle(g.key)}
                aria-expanded={!isCollapsed}
                className="flex w-full items-center justify-between px-3 py-1 text-[11px] font-semibold uppercase tracking-wider text-muted hover:text-text"
              >
                {t(`groups.${g.key}`)}
                <ChevronDown className={cn("size-3.5 transition-transform", isCollapsed && "-rotate-90")} aria-hidden />
              </button>
              {!isCollapsed && <div className="mt-1 space-y-0.5">{g.items.map((i) => renderItem(i, t(`items.${i.key}`)))}</div>}
            </div>
          );
        })}
      </div>

      {me && (
        <div className="flex items-center gap-3 rounded-xl border border-border bg-panel/60 p-2.5">
          <Avatar url={me.avatar_url} size={34} />
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-medium">{me.global_name ?? me.username}</p>
            <div className="flex gap-3 text-[12px] text-muted">
              <Link href="/account" className="inline-flex items-center gap-1 hover:text-text" onClick={onNavigate}>
                <UserRound className="size-3" aria-hidden />
                {tc("account")}
              </Link>
              <button type="button" onClick={logout} className="inline-flex items-center gap-1 hover:text-text">
                <LogOut className="size-3" aria-hidden />
                {tc("signOut")}
              </button>
            </div>
          </div>
        </div>
      )}
    </nav>
  );
}
