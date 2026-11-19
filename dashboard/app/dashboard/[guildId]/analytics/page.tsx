"use client";

import { useQuery } from "@tanstack/react-query";
import { BarChart3, Gavel, LogIn, LogOut, Terminal, Ticket, TrendingUp, Users } from "lucide-react";
import { useFormatter, useTranslations } from "next-intl";
import { useState } from "react";
import { Area, AreaChart, Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { Card, CardHeader, ErrorState, PageHeader, Skeleton } from "@/components/ui";
import { api } from "@/lib/api";
import { useGuildId } from "@/lib/hooks";
import { cn } from "@/lib/utils";

type Data = {
  days: number;
  series: { day: string; joined: number; left: number; commands: number; welcome: number; mod: number }[];
  totals: { joined: number; left: number; commands: number; welcome: number; mod: number; net_growth: number; tickets: number; suggestions: number; active_members: number };
  moderation: { by_action: Record<string, number>; by_source: Record<string, number> };
};

const axis = { tickLine: false, axisLine: false, tick: { fill: "var(--nx-text-muted)", fontSize: 12 } } as const;
const tooltip = { contentStyle: { background: "var(--nx-sidebar)", border: "1px solid var(--nx-border)", borderRadius: 8, fontSize: 13 }, labelStyle: { color: "var(--nx-text)" } };

export default function AnalyticsPage() {
  const t = useTranslations();
  const format = useFormatter();
  const guildId = useGuildId();
  const [days, setDays] = useState<7 | 30 | 90>(30);
  const q = useQuery({ queryKey: ["analytics", guildId, days], queryFn: () => api<Data>(`/guilds/${guildId}/analytics?days=${days}`), placeholderData: (p) => p });

  const range = (
    <div role="group" className="flex rounded-lg border border-border p-0.5 text-[13px]">
      {([7, 30, 90] as const).map((d) => (
        <button key={d} type="button" aria-pressed={days === d} onClick={() => setDays(d)} className={cn("min-h-8 rounded-md px-3", days === d ? "bg-input" : "text-muted hover:text-text")}>
          {t("duration.nDays", { n: d })}
        </button>
      ))}
    </div>
  );

  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const d = q.data;
  const tick = (v: string) => v.slice(5).replace("-", "/");
  const stats = d ? [
    { icon: TrendingUp, label: t("analytics.net"), value: d.totals.net_growth, signed: true },
    { icon: LogIn, label: t("overview.joinedLegend"), value: d.totals.joined },
    { icon: LogOut, label: t("overview.leftLegend"), value: d.totals.left },
    { icon: Users, label: t("analytics.active"), value: d.totals.active_members },
    { icon: Terminal, label: t("analytics.commands"), value: d.totals.commands },
    { icon: Gavel, label: t("analytics.mod"), value: d.totals.mod },
    { icon: Ticket, label: t("analytics.tickets"), value: d.totals.tickets },
    { icon: BarChart3, label: t("analytics.suggestions"), value: d.totals.suggestions },
  ] : [];
  const modRows = d ? Object.entries(d.moderation.by_action).map(([k, v]) => ({ name: t.has(`moderation.action_${k}`) ? t(`moderation.action_${k}`) : k, value: v })) : [];

  return (
    <div className="space-y-6">
      <PageHeader title={t("nav.items.analytics")} description={t("analytics.description")} action={range} />
      {!d ? <Skeleton className="h-96" /> : (
        <>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            {stats.map(({ icon: Icon, label, value, signed }) => (
              <Card key={label} className="p-5">
                <div className="mb-2 flex items-center gap-2 text-[13px] text-muted"><Icon className="size-4 text-primary-text" aria-hidden />{label}</div>
                <p className={cn("text-2xl font-semibold tabular-nums", signed && value > 0 && "text-success", signed && value < 0 && "text-danger")}>
                  {signed && value > 0 ? "+" : ""}{format.number(value)}
                </p>
              </Card>
            ))}
          </div>
          <Card>
            <CardHeader title={t("analytics.growth")} />
            <div className="h-72 p-4">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={d.series} margin={{ top: 4, right: 8, left: -16, bottom: 0 }}>
                  <CartesianGrid vertical={false} stroke="var(--nx-border)" />
                  <XAxis dataKey="day" {...axis} tickFormatter={tick} minTickGap={24} />
                  <YAxis allowDecimals={false} {...axis} />
                  <Tooltip {...tooltip} />
                  <Legend wrapperStyle={{ fontSize: 12 }} />
                  <Area type="monotone" dataKey="joined" name={t("overview.joinedLegend")} stroke="var(--nx-primary)" fill="var(--nx-primary)" fillOpacity={0.2} />
                  <Area type="monotone" dataKey="left" name={t("overview.leftLegend")} stroke="var(--nx-text-muted)" fill="var(--nx-text-muted)" fillOpacity={0.1} />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </Card>
          <div className="grid gap-6 lg:grid-cols-2">
            <Card>
              <CardHeader title={t("analytics.activity")} />
              <div className="h-64 p-4">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={d.series} margin={{ top: 4, right: 8, left: -16, bottom: 0 }}>
                    <CartesianGrid vertical={false} stroke="var(--nx-border)" />
                    <XAxis dataKey="day" {...axis} tickFormatter={tick} minTickGap={24} />
                    <YAxis allowDecimals={false} {...axis} />
                    <Tooltip {...tooltip} cursor={{ fill: "var(--nx-panel-hover)" }} />
                    <Legend wrapperStyle={{ fontSize: 12 }} />
                    <Bar dataKey="commands" name={t("analytics.commands")} fill="var(--nx-primary)" radius={[3, 3, 0, 0]} />
                    <Bar dataKey="welcome" name={t("analytics.welcome")} fill="var(--nx-success)" radius={[3, 3, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </Card>
            <Card>
              <CardHeader title={t("analytics.modBreakdown")} />
              {modRows.length === 0 ? <p className="px-5 py-10 text-center text-[13px] text-muted">{t("analytics.noMod")}</p> : (
                <div className="h-64 p-4">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={modRows} layout="vertical" margin={{ top: 4, right: 16, left: 24, bottom: 0 }}>
                      <CartesianGrid horizontal={false} stroke="var(--nx-border)" />
                      <XAxis type="number" allowDecimals={false} {...axis} />
                      <YAxis type="category" dataKey="name" width={110} {...axis} />
                      <Tooltip {...tooltip} cursor={{ fill: "var(--nx-panel-hover)" }} />
                      <Bar dataKey="value" name={t("analytics.mod")} fill="var(--nx-warning)" radius={[0, 3, 3, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              )}
            </Card>
          </div>
        </>
      )}
    </div>
  );
}
