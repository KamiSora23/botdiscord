"use client";

import { useQuery } from "@tanstack/react-query";
import { Activity, AlertTriangle, ArrowRight, Boxes, LogIn, Terminal, Users, Wand2 } from "lucide-react";
import Link from "next/link";
import { useFormatter, useTranslations } from "next-intl";
import { useState } from "react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip as ChartTooltip, XAxis, YAxis } from "recharts";

import { ActorAvatar, RelativeTime, useActionLabel } from "@/components/activity";
import { GettingStarted } from "@/components/getting-started";
import { Badge, Card, CardHeader, ErrorState, GuildIcon, Notice, Skeleton, StatusDot } from "@/components/ui";
import { api } from "@/lib/api";
import { useGuildId } from "@/lib/hooks";
import { NAV_GROUPS } from "@/lib/nav";
import type { Overview } from "@/lib/types";
import { cn } from "@/lib/utils";

const CATEGORY_ORDER = ["general", "moderation", "roles", "community", "progression", "utility"];

export default function OverviewPage() {
  const t = useTranslations();
  const guildId = useGuildId();
  const [days, setDays] = useState<7 | 30>(7);
  const q = useQuery({
    queryKey: ["overview", guildId, days],
    queryFn: () => api<Overview>(`/guilds/${guildId}/overview?days=${days}`),
    refetchInterval: 60_000,
    placeholderData: (prev) => prev,
  });

  if (q.isPending) return <OverviewSkeleton />;
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const o = q.data;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-4">
        <GuildIcon name={o.guild.name} url={o.guild.icon_url} size={56} />
        <div className="min-w-0 flex-1">
          <h1 className="truncate text-2xl font-semibold tracking-tight">{o.guild.name}</h1>
          <p className="text-muted">{t("common.members", { count: o.stats.member_count })}</p>
        </div>
        <Badge tone={o.bot.online ? "success" : "warning"} className="px-3 py-1 text-[12px] normal-case tracking-normal">
          <StatusDot status={o.bot.online ? "on" : "warn"} />
          {o.bot.online ? t("common.online") : t("common.offline")}
          {o.bot.online && o.bot.latency_ms != null && <span className="font-mono opacity-80">· {t("overview.latency", { ms: o.bot.latency_ms })}</span>}
        </Badge>
      </div>

      {o.stats.modules_enabled === 0 && (
        <Notice
          tone="info"
          icon={Wand2}
          action={
            <Link href={`/dashboard/${guildId}/setup`} className="text-sm font-medium text-primary-text hover:underline">
              {t("setup.title")} →
            </Link>
          }
        >
          {t("setup.overviewHint")}
        </Notice>
      )}

      <GettingStarted guildId={guildId} modules={o.modules} alerts={o.alerts} />

      {o.alerts.length > 0 && (
        <section aria-label={t("overview.alerts")} className="space-y-2">
          {o.alerts.map((a, i) => (
            <Notice
              key={i}
              tone={a.severity === "error" ? "danger" : "warning"}
              icon={AlertTriangle}
              action={
                <Link href={`/dashboard/${guildId}/diagnostics`} className="text-sm font-medium text-primary-text hover:underline">
                  {t("overview.fix")} →
                </Link>
              }
            >
              {t.has(`alerts.${a.code}`)
                ? t(`alerts.${a.code}`, {
                    permission: a.permission ? (t.has(`permissions.${a.permission}`) ? t(`permissions.${a.permission}`) : a.permission) : "",
                    intent: a.intent ?? "",
                  })
                : a.code}
            </Notice>
          ))}
        </section>
      )}

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard icon={Users} label={t("overview.members")} value={o.stats.member_count} />
        <StatCard icon={LogIn} label={t("overview.joined7d")} value={o.stats.joined_7d} sub={t("overview.left", { count: o.stats.left_7d })} />
        <StatCard icon={Terminal} label={t("overview.commands7d")} value={o.stats.commands_7d} />
        <StatCard
          icon={Boxes}
          label={t("overview.modulesActive")}
          value={o.stats.modules_total ? `${o.stats.modules_enabled}/${o.stats.modules_total}` : "—"}
          sub={o.stats.modules_total ? undefined : t("common.soon")}
        />
      </div>

      <Card>
        <CardHeader
          icon={Activity}
          title={t("overview.activity")}
          action={
            <div role="group" className="flex rounded-lg border border-border p-0.5 text-[13px]">
              {([7, 30] as const).map((d) => (
                <button
                  key={d}
                  type="button"
                  aria-pressed={days === d}
                  onClick={() => setDays(d)}
                  className={cn("min-h-8 rounded-md px-3", days === d ? "bg-input text-text" : "text-muted hover:text-text")}
                >
                  {t(d === 7 ? "overview.range7" : "overview.range30")}
                </button>
              ))}
            </div>
          }
        />
        <div className="h-64 px-2 py-4 sm:px-4">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={o.chart} margin={{ top: 4, right: 8, bottom: 0, left: -16 }}>
              <CartesianGrid vertical={false} stroke="var(--nx-border)" />
              <XAxis
                dataKey="day"
                tickLine={false}
                axisLine={false}
                tick={{ fill: "var(--nx-text-muted)", fontSize: 12 }}
                tickFormatter={(d: string) => d.slice(5).replace("-", "/")}
                minTickGap={16}
              />
              <YAxis allowDecimals={false} tickLine={false} axisLine={false} tick={{ fill: "var(--nx-text-muted)", fontSize: 12 }} />
              <ChartTooltip
                cursor={{ fill: "var(--nx-panel-hover)" }}
                contentStyle={{ background: "var(--nx-sidebar)", border: "1px solid var(--nx-border)", borderRadius: 8, fontSize: 13 }}
                labelStyle={{ color: "var(--nx-text)" }}
              />
              <Bar dataKey="members_joined" name={t("overview.joinedLegend")} fill="var(--nx-primary)" radius={[4, 4, 0, 0]} maxBarSize={28} />
              <Bar dataKey="members_left" name={t("overview.leftLegend")} fill="var(--nx-text-muted)" radius={[4, 4, 0, 0]} maxBarSize={28} />
            </BarChart>
          </ResponsiveContainer>
        </div>
        <div className="flex gap-4 border-t border-border px-5 py-3 text-[12px] text-muted">
          <span className="inline-flex items-center gap-1.5">
            <span className="size-2.5 rounded-sm bg-primary" aria-hidden />
            {t("overview.joinedLegend")}
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span className="size-2.5 rounded-sm bg-muted" aria-hidden />
            {t("overview.leftLegend")}
          </span>
        </div>
      </Card>

      <div className="grid gap-6 xl:grid-cols-[1fr_380px]">
        <section aria-labelledby="modules-title">
          <h2 id="modules-title" className="mb-3 text-base font-semibold">
            {t("overview.modules")}
          </h2>
          <div className="grid gap-4 md:grid-cols-2">
            {CATEGORY_ORDER.map((cat) => {
              const mods = o.modules.filter((m) => m.category === cat);
              if (mods.length === 0) return null;
              const avail = mods.filter((m) => m.available);
              const group = NAV_GROUPS.find((g) => g.key === cat);
              return (
                <Card key={cat} className="p-5">
                  <div className="mb-3 flex items-center justify-between">
                    <h3 className="font-semibold">{t(`overview.categories.${cat}`)}</h3>
                    <Badge tone={avail.length ? "success" : "neutral"}>
                      {avail.length
                        ? t("overview.activeCount", { active: avail.filter((m) => m.enabled).length, total: avail.length })
                        : t("common.soon")}
                    </Badge>
                  </div>
                  <ul className="space-y-1">
                    {mods.map((m) => {
                      const item = group?.items.find((i) => i.module === m.module);
                      const Icon = item?.icon;
                      return (
                        <li key={m.module} className={cn("flex min-h-9 items-center gap-2.5 text-sm", !m.available && "text-muted/70")}>
                          {Icon && <Icon className="size-4 text-muted" aria-hidden />}
                          <span className="flex-1 truncate">{t.has(`nav.items.${m.module}`) ? t(`nav.items.${m.module}`) : m.module}</span>
                          {m.available ? (
                            <StatusDot status={m.enabled ? "on" : "off"} label={m.enabled ? t("common.enabled") : t("common.disabled")} />
                          ) : (
                            <span className="text-[12px]">{t("common.soon")}</span>
                          )}
                        </li>
                      );
                    })}
                  </ul>
                </Card>
              );
            })}
          </div>
        </section>

        <Card className="h-fit">
          <CardHeader
            title={t("overview.recentActivity")}
            action={
              <Link href={`/dashboard/${guildId}/audit-log`} className="inline-flex items-center gap-1 text-[13px] text-primary-text hover:underline">
                {t("common.viewAll")} <ArrowRight className="size-3.5" aria-hidden />
              </Link>
            }
          />
          <RecentActivity entries={o.recent_activity} />
        </Card>
      </div>
    </div>
  );
}

function RecentActivity({ entries }: { entries: Overview["recent_activity"] }) {
  const t = useTranslations();
  const label = useActionLabel();
  if (entries.length === 0) return <p className="px-5 py-8 text-center text-[13px] text-muted">{t("overview.noActivity")}</p>;
  return (
    <ul className="divide-y divide-border">
      {entries.map((e) => (
        <li key={e.id} className="flex items-start gap-3 px-5 py-3">
          <ActorAvatar entry={e} />
          <div className="min-w-0 text-[13px]">
            <p>
              {e.actor?.name && <span className="font-medium">{e.actor.name} </span>}
              <span className={e.actor ? "text-muted" : ""}>{label(e)}</span>
            </p>
            <p className="text-[12px] text-muted">
              <RelativeTime iso={e.created_at} />
            </p>
          </div>
        </li>
      ))}
    </ul>
  );
}

function StatCard({ icon: Icon, label, value, sub }: { icon: typeof Users; label: string; value: React.ReactNode; sub?: string }) {
  const format = useFormatter();
  return (
    <Card className="p-5">
      <div className="mb-3 grid size-9 place-items-center rounded-lg bg-primary/15">
        <Icon className="size-[18px] text-primary-text" aria-hidden />
      </div>
      <p className="text-2xl font-semibold tabular-nums">{typeof value === "number" ? format.number(value) : value}</p>
      <p className="mt-0.5 text-[13px] text-muted">
        {label}
        {sub && <span className="ml-2 text-muted/80">· {sub}</span>}
      </p>
    </Card>
  );
}

function OverviewSkeleton() {
  return (
    <div className="space-y-6">
      <div className="flex items-center gap-4">
        <Skeleton className="size-14 rounded-xl" />
        <div className="space-y-2">
          <Skeleton className="h-7 w-56" />
          <Skeleton className="h-4 w-32" />
        </div>
      </div>
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-32" />
        ))}
      </div>
      <Skeleton className="h-80" />
    </div>
  );
}
