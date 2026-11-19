"use client";

import { useQueryClient } from "@tanstack/react-query";
import { Bot, LogOut, RefreshCw, Search, ServerOff, UserRound } from "lucide-react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { LocaleSync } from "@/components/locale-sync";
import { useLogout } from "@/components/shell/use-logout";
import { Avatar, Badge, Button, Card, EmptyState, ErrorState, GuildIcon, LinkButton, Skeleton, StatusDot } from "@/components/ui";
import { api } from "@/lib/api";
import { useGuilds, useMe } from "@/lib/hooks";
import type { GuildListItem } from "@/lib/types";

export default function ServersPage() {
  const t = useTranslations();
  const qc = useQueryClient();
  const { data: me } = useMe();
  const guilds = useGuilds();
  const logout = useLogout();
  const [query, setQuery] = useState("");
  const [refreshing, setRefreshing] = useState(false);

  // Al volver de la ventana de invitación, recargar la lista para ver el bot como activo.
  useEffect(() => {
    const onFocus = () => qc.invalidateQueries({ queryKey: ["guilds"] });
    window.addEventListener("focus", onFocus);
    return () => window.removeEventListener("focus", onFocus);
  }, [qc]);

  const refresh = async () => {
    setRefreshing(true);
    try {
      const data = await api<{ data: GuildListItem[] }>("/guilds?refresh=true");
      qc.setQueryData(["guilds"], data.data);
    } finally {
      setRefreshing(false);
    }
  };

  const list = (guilds.data ?? []).filter((g) => g.name.toLowerCase().includes(query.toLowerCase()));
  const withBot = (guilds.data ?? []).filter((g) => g.bot_present).length;

  return (
    <div className="min-h-dvh">
      <LocaleSync />
      <header className="border-b border-border bg-sidebar">
        <div className="mx-auto flex h-16 max-w-[1280px] items-center justify-between gap-4 px-4 sm:px-6">
          <Link href="/" className="flex items-center gap-2.5">
            <span className="grid size-9 place-items-center rounded-xl bg-primary-solid text-sm font-bold text-white">N</span>
            <span className="text-[17px] font-semibold tracking-tight">NEXUS</span>
          </Link>
          {me && (
            <div className="flex items-center gap-2">
              <Link href="/account" className="flex items-center gap-2 rounded-lg px-2 py-1.5 hover:bg-panel-hover">
                <Avatar url={me.avatar_url} size={30} />
                <span className="hidden text-sm sm:inline">{me.global_name ?? me.username}</span>
                <UserRound className="size-4 text-muted sm:hidden" aria-label={t("common.account")} />
              </Link>
              <Button variant="ghost" size="sm" onClick={logout} aria-label={t("common.signOut")}>
                <LogOut className="size-4" aria-hidden />
              </Button>
            </div>
          )}
        </div>
      </header>

      <main className="mx-auto max-w-[1280px] px-4 py-8 sm:px-6">
        <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">{t("servers.title")}</h1>
            <p className="mt-1 text-muted">{t("servers.subtitle")}</p>
          </div>
          <div className="flex w-full gap-2 sm:w-auto">
            <label className="relative flex-1 sm:w-72">
              <span className="sr-only">{t("servers.search")}</span>
              <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted" aria-hidden />
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder={t("servers.search")}
                className="min-h-10 w-full rounded-lg border border-border bg-panel pl-9 pr-3 text-sm focus:border-primary focus:outline-none"
              />
            </label>
            <Button variant="secondary" onClick={refresh} loading={refreshing} aria-label={t("servers.refresh")}>
              {!refreshing && <RefreshCw className="size-4" aria-hidden />}
            </Button>
          </div>
        </div>

        {guilds.data && guilds.data.length > 0 && (
          <div className="mb-6 grid gap-3 sm:grid-cols-3">
            <Summary label={t("servers.managed")} value={String(guilds.data.length)} />
            <Summary label={t("servers.withBot")} value={String(withBot)} />
            <Summary label={t("servers.botStatus")} value={<BotHealth />} />
          </div>
        )}

        {guilds.isPending ? (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {Array.from({ length: 6 }).map((_, i) => (
              <Skeleton key={i} className="h-36" />
            ))}
          </div>
        ) : guilds.isError ? (
          <ErrorState error={guilds.error} onRetry={() => guilds.refetch()} />
        ) : guilds.data.length === 0 ? (
          <Card>
            <EmptyState icon={ServerOff} title={t("servers.emptyTitle")} body={t("servers.emptyBody")} />
          </Card>
        ) : list.length === 0 ? (
          <p className="py-10 text-center text-muted">{t("servers.noResults")}</p>
        ) : (
          <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {list.map((g) => (
              <li key={g.id}>
                <ServerCard guild={g} />
              </li>
            ))}
          </ul>
        )}
      </main>
    </div>
  );
}

function Summary({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <Card className="px-5 py-4">
      <p className="text-[13px] text-muted">{label}</p>
      <div className="mt-1 text-xl font-semibold">{value}</div>
    </Card>
  );
}

function BotHealth() {
  const t = useTranslations("common");
  const [online, setOnline] = useState<boolean | null>(null);
  useEffect(() => {
    api<{ bot: string }>("/health")
      .then((h) => setOnline(h.bot === "online"))
      .catch(() => setOnline(false));
  }, []);
  if (online === null) return <Skeleton className="h-7 w-24" />;
  return <StatusDot status={online ? "on" : "off"} label={online ? t("online") : t("offline")} />;
}

function ServerCard({ guild }: { guild: GuildListItem }) {
  const t = useTranslations();
  return (
    <Card className="flex h-full flex-col gap-4 p-5">
      <div className="flex items-center gap-3">
        <GuildIcon name={guild.name} url={guild.icon_url} size={48} className={guild.bot_present ? "" : "grayscale"} />
        <div className="min-w-0">
          <h2 className="truncate font-semibold">{guild.name}</h2>
          <p className="text-[13px] text-muted">
            {guild.member_count != null ? t("common.members", { count: guild.member_count }) : "—"}
          </p>
        </div>
      </div>
      <div className="mt-auto flex items-center justify-between gap-3">
        {guild.bot_present ? (
          <span className="text-[13px] text-success">
            <StatusDot status="on" label={t("servers.botActive")} />
          </span>
        ) : (
          <Badge>{t("servers.notAdded")}</Badge>
        )}
        {guild.bot_present ? (
          <LinkButton href={`/dashboard/${guild.id}/overview`} className="min-h-9">
            {t("common.manage")}
          </LinkButton>
        ) : (
          guild.invite_url && (
            <LinkButton href={guild.invite_url} target="_blank" rel="noopener noreferrer" variant="secondary" className="min-h-9">
              <Bot className="size-4" aria-hidden />
              {t("common.invite")}
            </LinkButton>
          )
        )}
      </div>
    </Card>
  );
}
