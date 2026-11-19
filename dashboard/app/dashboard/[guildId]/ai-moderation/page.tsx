"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, ExternalLink, ShieldQuestion, Sparkles, X } from "lucide-react";
import { useFormatter, useTranslations } from "next-intl";
import { useState } from "react";
import { toast } from "sonner";

import { ChannelSelect } from "@/components/channel-select";
import { DurationInput } from "@/components/duration-input";
import { ModulePage } from "@/components/module-page";
import { ChannelMultiSelect, RoleMultiSelect } from "@/components/multi-select";
import { Badge, Button, Card, CardHeader, EmptyState, Field, inputClass, Notice, Switch } from "@/components/ui";
import { api, errorText } from "@/lib/api";
import { useGuildId } from "@/lib/hooks";
import { useModuleConfig } from "@/lib/use-module";
import { cn } from "@/lib/utils";

type Cfg = {
  categories: Record<string, boolean>; rules_text: string; action_threshold: number; review_threshold: number;
  action: "alert" | "delete" | "delete_timeout"; timeout_seconds: number; alert_channel_id: string | null;
  monitored_channel_ids: string[]; exempt_role_ids: string[]; min_length: number; max_requests_per_minute: number; monthly_token_limit: number;
};
type Status = { configured: boolean; month: string; tokens_used: number; token_limit: number; requests: number; pending_reviews: number };
type Ev = { id: string; user: { id: string; name: string }; category: string; score: number; reason: string | null; action: string; review_status: string; jump_url: string; created_at: string };

export default function AIModerationPage() {
  const t = useTranslations();
  const format = useFormatter();
  const guildId = useGuildId();
  const qc = useQueryClient();
  const ctl = useModuleConfig<Cfg>(guildId, "ai_moderation");
  const form = ctl.form;
  const set = (p: Partial<Cfg>) => form && ctl.setForm({ ...form, ...p });
  const status = useQuery({ queryKey: ["ai-status", guildId], queryFn: () => api<Status>(`/guilds/${guildId}/ai-moderation/status`), refetchInterval: 60_000 });
  const [filter, setFilter] = useState<"pending" | "all">("pending");
  const events = useQuery({ queryKey: ["ai-events", guildId, filter], queryFn: () => api<{ data: Ev[]; can_edit: boolean }>(`/guilds/${guildId}/ai-moderation/events?status=${filter}`), refetchInterval: 30_000 });
  const review = useMutation({
    mutationFn: ({ id, decision, punishment }: { id: string; decision: "confirm" | "dismiss"; punishment: "none" | "warn" | "timeout" }) =>
      api(`/guilds/${guildId}/ai-moderation/events/${id}/review`, { method: "POST", json: { decision, punishment } }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["ai-events", guildId] }); qc.invalidateQueries({ queryKey: ["ai-status", guildId] }); },
    onError: (e) => toast.error(errorText(e, t("states.errorBody"))),
  });
  const s = status.data;
  const pct = s ? Math.min(100, Math.round((100 * s.tokens_used) / s.token_limit)) : 0;
  const thresholdErr = form && form.review_threshold > form.action_threshold;

  return (
    <ModulePage ctl={ctl as never} title={t("nav.items.ai_moderation")} description={t("ai.description")} errorCount={thresholdErr ? 1 : 0}>
      {form && (
        <div className="space-y-6">
          {s && !s.configured && <Notice tone="warning">{t("ai.notConfigured")}</Notice>}
          <Notice tone="info" icon={ShieldQuestion}>{t("ai.privacy")}</Notice>

          <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_340px]">
            <Card>
              <CardHeader icon={Sparkles} title={t("ai.detection")} />
              <fieldset disabled={!ctl.canEdit} className="space-y-4 p-5">
                <div className="grid gap-2 sm:grid-cols-2">
                  {Object.entries(form.categories).map(([c, on]) => (
                    <label key={c} className="flex items-center justify-between gap-3 rounded-lg border border-border px-3 py-2 text-sm">
                      {t(`ai.cat_${c}`)}
                      <Switch checked={on} label={t(`ai.cat_${c}`)} onCheckedChange={(v) => set({ categories: { ...form.categories, [c]: v } })} />
                    </label>
                  ))}
                </div>
                <Field id="ai-rules" label={t("ai.rules")} help={t("ai.rulesHelp")}>
                  <textarea id="ai-rules" rows={4} className={cn(inputClass, "py-2")} value={form.rules_text} maxLength={2000} onChange={(e) => set({ rules_text: e.target.value })} />
                </Field>
                <div className="grid gap-4 sm:grid-cols-2">
                  <Field id="ai-review" label={t("ai.reviewThreshold", { pct: Math.round(form.review_threshold * 100) })} error={thresholdErr ? t("ai.thresholdError") : undefined}>
                    <input id="ai-review" type="range" min={30} max={100} className="w-full accent-[var(--nx-primary)]" value={Math.round(form.review_threshold * 100)} onChange={(e) => set({ review_threshold: Number(e.target.value) / 100 })} />
                  </Field>
                  <Field id="ai-action-th" label={t("ai.actionThreshold", { pct: Math.round(form.action_threshold * 100) })}>
                    <input id="ai-action-th" type="range" min={50} max={100} className="w-full accent-[var(--nx-primary)]" value={Math.round(form.action_threshold * 100)} onChange={(e) => set({ action_threshold: Number(e.target.value) / 100 })} />
                  </Field>
                  <Field id="ai-action" label={t("ai.whatToDo")}>
                    <select id="ai-action" className={inputClass} value={form.action} onChange={(e) => set({ action: e.target.value as Cfg["action"] })}>
                      {(["alert", "delete", "delete_timeout"] as const).map((a) => <option key={a} value={a}>{t(`ai.do_${a}`)}</option>)}
                    </select>
                  </Field>
                  {form.action === "delete_timeout" && <Field id="ai-timeout" label={t("duration.label")}><DurationInput id="ai-timeout" value={form.timeout_seconds} onChange={(v) => set({ timeout_seconds: v })} /></Field>}
                  <Field id="ai-alert" label={t("automod.logChannel")}><ChannelSelect id="ai-alert" guildId={guildId} value={form.alert_channel_id} onChange={(v) => set({ alert_channel_id: v })} needEmbed /></Field>
                </div>
                <Field id="ai-channels" label={t("ai.channels")} help={t("ai.channelsHelp")}><ChannelMultiSelect id="ai-channels" guildId={guildId} value={form.monitored_channel_ids} onChange={(v) => set({ monitored_channel_ids: v })} /></Field>
                <Field id="ai-exempt" label={t("automod.exemptRoles")}><RoleMultiSelect id="ai-exempt" guildId={guildId} value={form.exempt_role_ids} onChange={(v) => set({ exempt_role_ids: v })} /></Field>
              </fieldset>
            </Card>
            <div className="space-y-6">
              <Card>
                <CardHeader title={t("ai.usage", { month: s?.month ?? "" })} />
                <div className="space-y-3 p-5">
                  <div className="h-2 overflow-hidden rounded-full bg-input"><div className={cn("h-full rounded-full", pct >= 90 ? "bg-danger" : "bg-primary")} style={{ width: `${pct}%` }} /></div>
                  <p className="text-sm">{t("ai.tokens", { used: (s?.tokens_used ?? 0).toLocaleString(), limit: (s?.token_limit ?? 0).toLocaleString() })}</p>
                  <p className="text-[12px] text-muted">{t("ai.requests", { count: s?.requests ?? 0 })}</p>
                  <fieldset disabled={!ctl.canEdit} className="space-y-3 pt-2">
                    <Field id="ai-limit" label={t("ai.limit")} help={t("ai.limitHelp")}><input id="ai-limit" type="number" min={10000} step={10000} className={inputClass} value={form.monthly_token_limit} onChange={(e) => set({ monthly_token_limit: Number(e.target.value) })} /></Field>
                    <Field id="ai-rpm" label={t("ai.rpm")}><input id="ai-rpm" type="number" min={1} max={120} className={inputClass} value={form.max_requests_per_minute} onChange={(e) => set({ max_requests_per_minute: Number(e.target.value) })} /></Field>
                    <Field id="ai-min" label={t("ai.minLength")}><input id="ai-min" type="number" min={1} max={500} className={inputClass} value={form.min_length} onChange={(e) => set({ min_length: Number(e.target.value) })} /></Field>
                  </fieldset>
                </div>
              </Card>
            </div>
          </div>

          <Card className="overflow-hidden">
            <CardHeader title={t("ai.queue", { count: s?.pending_reviews ?? 0 })} action={
              <div className="flex rounded-lg border border-border p-0.5 text-[13px]">
                {(["pending", "all"] as const).map((f) => <button key={f} type="button" aria-pressed={filter === f} onClick={() => setFilter(f)} className={cn("min-h-8 rounded-md px-3", filter === f ? "bg-input" : "text-muted")}>{t(`ai.filter_${f}`)}</button>)}
              </div>
            } />
            {!events.data?.data.length ? <EmptyState icon={Sparkles} title={t("ai.empty")} /> : (
              <ul className="divide-y divide-border">
                {events.data.data.map((e) => (
                  <li key={e.id} className="flex flex-wrap items-center gap-3 px-5 py-3 text-sm">
                    <div className="min-w-0 flex-1">
                      <p className="flex flex-wrap items-center gap-2"><span className="font-medium">{e.user.name}</span><Badge tone="warning">{t(`ai.cat_${e.category}`)}</Badge><span className="text-[12px] text-muted">{Math.round(e.score * 100)}% · {format.relativeTime(new Date(e.created_at))}</span></p>
                      {e.reason && <p className="text-[13px] text-muted">{e.reason}</p>}
                      <p className="text-[12px] text-muted">{t(`ai.action_${e.action}`)}</p>
                    </div>
                    <a href={e.jump_url} target="_blank" rel="noopener noreferrer" className="text-primary-text" aria-label="Discord"><ExternalLink className="size-4" /></a>
                    {e.review_status === "pending" && events.data.can_edit ? (
                      <>
                        <Button size="sm" variant="secondary" onClick={() => review.mutate({ id: e.id, decision: "confirm", punishment: "warn" })}><Check className="size-4" aria-hidden /> {t("ai.confirmWarn")}</Button>
                        <Button size="sm" variant="ghost" onClick={() => review.mutate({ id: e.id, decision: "confirm", punishment: "none" })}>{t("ai.confirm")}</Button>
                        <Button size="sm" variant="ghost" onClick={() => review.mutate({ id: e.id, decision: "dismiss", punishment: "none" })}><X className="size-4" aria-hidden /> {t("ai.dismiss")}</Button>
                      </>
                    ) : <Badge tone={e.review_status === "confirmed" ? "danger" : "neutral"}>{t(`ai.review_${e.review_status}`)}</Badge>}
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>
      )}
    </ModulePage>
  );
}
