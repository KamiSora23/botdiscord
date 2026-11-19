"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowRight, Bell, Clock, Headphones, History, Mic, Radio, Users } from "lucide-react";
import Link from "next/link";
import { useFormatter, useTranslations } from "next-intl";
import { useState } from "react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { useChannels } from "@/components/channel-select";
import { ModulePage } from "@/components/module-page";
import { Badge, Card, CardHeader, EmptyState, Field, inputClass, Skeleton, Switch } from "@/components/ui";
import { api } from "@/lib/api";
import { useGuildId } from "@/lib/hooks";
import { useModuleConfig } from "@/lib/use-module";
import { cn } from "@/lib/utils";

type Cfg = { retention_days: number; ignored_channel_ids: string[]; ignore_afk: boolean };
type Stats = {
  days: number; total_seconds: number; sessions: number; members: number; in_voice_now: number;
  top_users: { user_id: string; name: string; seconds: number; sessions: number }[];
  top_channels: { channel_id: string; name: string; seconds: number; sessions: number }[];
  daily: { day: string; seconds: number }[];
};
type Session = { id: string; user_id: string; user_name: string; channel_id: string; channel_name: string; joined_at: string; left_at: string | null; seconds: number; open: boolean };

const axis = { tickLine: false, axisLine: false, tick: { fill: "var(--nx-text-muted)", fontSize: 12 } } as const;
const tooltip = { contentStyle: { background: "var(--nx-sidebar)", border: "1px solid var(--nx-border)", borderRadius: 8, fontSize: 13 }, labelStyle: { color: "var(--nx-text)" } };

/** 3725 → «1 h 2 min». */
function dur(sec: number): string {
  const s = Math.max(0, Math.round(sec));
  const d = Math.floor(s / 86400), h = Math.floor((s % 86400) / 3600), m = Math.floor((s % 3600) / 60);
  if (d) return `${d} d ${h} h`;
  if (h) return `${h} h ${m} min`;
  if (m) return `${m} min`;
  return `${s} s`;
}

export default function VoiceActivityPage() {
  const t = useTranslations();
  const format = useFormatter();
  const guildId = useGuildId();
  const ctl = useModuleConfig<Cfg>(guildId, "voice_activity");
  const form = ctl.form;
  const set = (p: Partial<Cfg>) => form && ctl.setForm({ ...form, ...p });
  const [days, setDays] = useState<7 | 30 | 0>(30);
  const [userFilter, setUserFilter] = useState("");
  const { data: channels } = useChannels(guildId);
  const voiceChannels = (channels ?? []).filter((c) => c.type === "voice");

  const stats = useQuery({
    queryKey: ["voice-stats", guildId, days], enabled: ctl.enabled,
    queryFn: () => api<Stats>(`/guilds/${guildId}/voice/stats?days=${days}`), placeholderData: (p) => p, refetchInterval: 60_000,
  });
  const sessions = useQuery({
    queryKey: ["voice-sessions", guildId, userFilter], enabled: ctl.enabled,
    queryFn: () => api<{ data: Session[] }>(`/guilds/${guildId}/voice/sessions?limit=50${userFilter ? `&user_id=${userFilter}` : ""}`),
    refetchInterval: 60_000,
  });
  const logs = useQuery({
    queryKey: ["module", guildId, "logging"],
    queryFn: () => api<{ data: { enabled: boolean; config: { categories: Record<string, { channel_id: string | null; events: Record<string, boolean>; event_channels?: Record<string, string> }> } } }>(`/guilds/${guildId}/modules/logging`),
  });
  const voiceLog = logs.data?.data.config.categories.voice;
  const chName = (id: string | null | undefined) => (id ? `#${channels?.find((c) => c.id === id)?.name ?? "?"}` : null);
  const s = stats.data;
  // Si hay poco tiempo, la gráfica en minutos (en horas se vería vacía).
  const maxDay = Math.max(0, ...(s?.daily.map((d) => d.seconds) ?? [0]));
  const inMinutes = maxDay < 3600;
  const maxUser = Math.max(1, ...(s?.top_users.map((u) => u.seconds) ?? [1]));

  const range = (
    <div role="group" className="flex rounded-lg border border-border p-0.5 text-[13px]">
      {([7, 30, 0] as const).map((d) => (
        <button key={d} type="button" aria-pressed={days === d} onClick={() => setDays(d)}
          className={cn("min-h-8 rounded-md px-3", days === d ? "bg-input" : "text-muted hover:text-text")}>
          {d ? t("duration.nDays", { n: d }) : t("voice.all")}
        </button>
      ))}
    </div>
  );

  return (
    <ModulePage ctl={ctl as never} title={t("nav.items.voice_activity")} description={t("voice.description")}>
      {form && (
        <div className="space-y-6">
          {ctl.enabled && (
            <>
              <div className="flex flex-wrap items-center justify-between gap-3">
                <h2 className="text-sm font-semibold">{t("voice.stats")}</h2>
                {range}
              </div>
              {!s ? <Skeleton className="h-28" /> : (
                <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
                  {[
                    { icon: Clock, label: t("voice.totalTime"), value: dur(s.total_seconds) },
                    { icon: Headphones, label: t("voice.sessions"), value: format.number(s.sessions) },
                    { icon: Users, label: t("voice.members"), value: format.number(s.members) },
                    { icon: Radio, label: t("voice.now"), value: format.number(s.in_voice_now) },
                  ].map(({ icon: Icon, label, value }) => (
                    <Card key={label} className="p-5">
                      <div className="mb-2 flex items-center gap-2 text-[13px] text-muted"><Icon className="size-4 text-primary-text" aria-hidden />{label}</div>
                      <p className="text-2xl font-semibold tabular-nums">{value}</p>
                    </Card>
                  ))}
                </div>
              )}

              {s && (
                <div className="grid gap-6 lg:grid-cols-[1.4fr_1fr]">
                  <Card>
                    <CardHeader title={inMinutes ? t("voice.perDayMin") : t("voice.perDay")} />
                    {s.daily.length === 0 ? <p className="px-5 py-10 text-center text-[13px] text-muted">{t("voice.empty")}</p> : (
                      <div className="h-64 p-4">
                        <ResponsiveContainer width="100%" height="100%">
                          <BarChart data={s.daily.map((d) => ({ day: d.day.slice(5).replace("-", "/"), hours: inMinutes ? Math.max(1, Math.round(d.seconds / 60)) : +(d.seconds / 3600).toFixed(1) }))} margin={{ top: 4, right: 8, left: -16, bottom: 0 }}>
                            <CartesianGrid vertical={false} stroke="var(--nx-border)" />
                            <XAxis dataKey="day" {...axis} minTickGap={16} />
                            <YAxis {...axis} />
                            <Tooltip {...tooltip} cursor={{ fill: "var(--nx-panel-hover)" }} formatter={(v) => [inMinutes ? `${v} min` : `${v} h`, inMinutes ? t("voice.minutes") : t("voice.hours")]} />
                            <Bar dataKey="hours" fill="var(--nx-primary)" radius={[3, 3, 0, 0]} />
                          </BarChart>
                        </ResponsiveContainer>
                      </div>
                    )}
                  </Card>
                  <Card>
                    <CardHeader title={t("voice.topMembers")} />
                    {s.top_users.length === 0 ? <p className="px-5 py-10 text-center text-[13px] text-muted">{t("voice.empty")}</p> : (
                      <ol className="space-y-2 p-5">
                        {s.top_users.map((u, n) => (
                          <li key={u.user_id}>
                            <button type="button" onClick={() => setUserFilter(u.user_id)} className="w-full text-left" title={t("voice.filterUser")}>
                              <div className="mb-1 flex items-center justify-between text-sm">
                                <span className="truncate"><span className="mr-2 text-muted tabular-nums">#{n + 1}</span>{u.name || u.user_id}</span>
                                <span className="tabular-nums text-muted">{dur(u.seconds)}</span>
                              </div>
                              <div className="h-1.5 rounded-full bg-panel-hover"><div className="h-full rounded-full bg-primary" style={{ width: `${(u.seconds / maxUser) * 100}%` }} /></div>
                            </button>
                          </li>
                        ))}
                      </ol>
                    )}
                  </Card>
                </div>
              )}

              {s && s.top_channels.length > 0 && (
                <Card>
                  <CardHeader icon={Mic} title={t("voice.topChannels")} />
                  <ul className="divide-y divide-border">
                    {s.top_channels.map((c) => (
                      <li key={c.channel_id} className="flex items-center justify-between px-5 py-2.5 text-sm">
                        <span>🔊 {c.name}</span>
                        <span className="text-muted tabular-nums">{dur(c.seconds)} · {t("voice.nSessions", { n: c.sessions })}</span>
                      </li>
                    ))}
                  </ul>
                </Card>
              )}

              <Card>
                <CardHeader icon={Bell} title={t("voice.noticesTitle")} description={t("voice.noticesHelp")} action={
                  <Link href={`/dashboard/${guildId}/logging#voice`} className="flex items-center gap-1 text-[13px] text-primary-text hover:underline">
                    {t("voice.changeChannels")} <ArrowRight className="size-3.5" aria-hidden />
                  </Link>
                } />
                <ul className="divide-y divide-border text-sm">
                  {(["voice_join", "voice_leave", "voice_move"] as const).map((ev) => {
                    const on = logs.data?.data.enabled && voiceLog && voiceLog.events[ev] !== false;
                    const dest = on ? (voiceLog?.event_channels?.[ev] ?? voiceLog?.channel_id) : null;
                    return (
                      <li key={ev} className="flex items-center justify-between px-5 py-2.5">
                        <span>{t(`logging.ev_${ev}`)}</span>
                        <span className={dest ? "text-primary-text" : "text-muted"}>{dest ? chName(dest) : t("logging.notSent")}</span>
                      </li>
                    );
                  })}
                </ul>
              </Card>

              <Card>
                <CardHeader icon={History} title={t("voice.history")} description={t("voice.historyHelp")} action={
                  userFilter ? <button type="button" onClick={() => setUserFilter("")} className="text-[13px] text-primary-text hover:underline">{t("voice.clearFilter")}</button> : null
                } />
                {sessions.isPending ? <Skeleton className="m-5 h-40" /> : !sessions.data?.data.length ? (
                  <EmptyState icon={Headphones} title={t("voice.empty")} body={t("voice.emptyBody")} />
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead className="text-left text-[12px] text-muted">
                        <tr><th className="px-5 py-2 font-medium">{t("voice.member")}</th><th className="px-3 py-2 font-medium">{t("voice.channel")}</th><th className="px-3 py-2 font-medium">{t("voice.joined")}</th><th className="px-3 py-2 font-medium">{t("voice.left")}</th><th className="px-5 py-2 text-right font-medium">{t("voice.duration")}</th></tr>
                      </thead>
                      <tbody className="divide-y divide-border">
                        {sessions.data.data.map((r) => (
                          <tr key={r.id} className="hover:bg-panel-hover">
                            <td className="px-5 py-2"><button type="button" className="hover:underline" onClick={() => setUserFilter(r.user_id)}>{r.user_name || r.user_id}</button></td>
                            <td className="px-3 py-2 text-muted">🔊 {r.channel_name}</td>
                            <td className="px-3 py-2 tabular-nums">{format.dateTime(new Date(r.joined_at), { dateStyle: "short", timeStyle: "short" })}</td>
                            <td className="px-3 py-2 tabular-nums">{r.open ? <Badge tone="success">{t("voice.inVoice")}</Badge> : format.dateTime(new Date(r.left_at!), { timeStyle: "short" })}</td>
                            <td className="px-5 py-2 text-right tabular-nums">{dur(r.seconds)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </Card>
            </>
          )}

          <Card>
            <CardHeader icon={Mic} title={t("welcome.settings")} description={t("voice.privacy")} />
            <fieldset disabled={!ctl.canEdit} className="grid gap-4 p-5 sm:grid-cols-2">
              <Field id="va-retention" label={t("voice.retention")} help={t("voice.retentionHelp")}>
                <select id="va-retention" className={inputClass} value={form.retention_days} onChange={(e) => set({ retention_days: Number(e.target.value) })}>
                  {[7, 30, 60, 90, 180, 365].map((d) => <option key={d} value={d}>{t("duration.nDays", { n: d })}</option>)}
                </select>
              </Field>
              <label className="flex items-center justify-between gap-4 self-end text-sm">{t("voice.ignoreAfk")}<Switch checked={form.ignore_afk} label={t("voice.ignoreAfk")} onCheckedChange={(v) => set({ ignore_afk: v })} /></label>
              <div className="sm:col-span-2">
                <p className="mb-2 text-sm font-medium">{t("voice.ignored")}</p>
                {voiceChannels.length === 0 ? <p className="text-[13px] text-muted">{t("voice.noVoice")}</p> : (
                  <div className="flex flex-wrap gap-2">
                    {voiceChannels.map((c) => {
                      const on = form.ignored_channel_ids.includes(c.id);
                      return (
                        <button key={c.id} type="button" aria-pressed={on}
                          onClick={() => set({ ignored_channel_ids: on ? form.ignored_channel_ids.filter((x) => x !== c.id) : [...form.ignored_channel_ids, c.id] })}
                          className={cn("rounded-full border px-3 py-1 text-[13px]", on ? "border-danger/60 bg-danger/10 text-danger line-through" : "border-border hover:border-primary")}>
                          🔊 {c.name}
                        </button>
                      );
                    })}
                  </div>
                )}
                <p className="mt-2 text-[12px] text-muted">{t("voice.ignoredHelp")}</p>
              </div>
            </fieldset>
          </Card>
        </div>
      )}
    </ModulePage>
  );
}
