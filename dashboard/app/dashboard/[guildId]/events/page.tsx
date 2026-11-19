"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarDays, ExternalLink, Plus, Settings2, XCircle } from "lucide-react";
import { useFormatter, useTranslations } from "next-intl";
import { useState } from "react";
import { toast } from "sonner";

import { ChannelSelect, useChannels } from "@/components/channel-select";
import { DateTimePicker } from "@/components/datetime-picker";
import { isMedia, MediaButton, MediaChip } from "@/components/media-picker";
import { ModulePage } from "@/components/module-page";
import { RoleMultiSelect } from "@/components/multi-select";
import { ConfirmDialog } from "@/components/save-bar";
import { Badge, Button, Card, CardHeader, EmptyState, Field, inputClass, Skeleton, Switch } from "@/components/ui";
import { api, errorText } from "@/lib/api";
import { browserTimeZone, isPastLocal, toLocalInput, zonedToDate } from "@/lib/datetime";
import { useGuildId } from "@/lib/hooks";
import { useModuleConfig } from "@/lib/use-module";
import { cn } from "@/lib/utils";

type Cfg = { default_channel_id: string | null; reminder_minutes: number; manager_role_ids: string[]; ping_at_start: boolean };
type Ev = { id: string; title: string; description: string; starts_at: string; channel_id: string; max_slots: number | null; status: string; going: number; maybe: number; no: number; url: string | null };
type Draft = { title: string; description: string; when: string; channel_id: string | null; max_slots: string; image_url: string };

function tomorrow20(): string {
  const d = new Date(Date.now() + 86400000);
  d.setHours(20, 0, 0, 0);
  return toLocalInput(d);
}

export default function EventsPage() {
  const t = useTranslations();
  const format = useFormatter();
  const guildId = useGuildId();
  const qc = useQueryClient();
  const ctl = useModuleConfig<Cfg>(guildId, "events");
  const form = ctl.form;
  const set = (p: Partial<Cfg>) => form && ctl.setForm({ ...form, ...p });
  const { data: channels } = useChannels(guildId);
  const [tab, setTab] = useState<"upcoming" | "past">("upcoming");
  const list = useQuery({
    queryKey: ["events", guildId, tab], enabled: ctl.enabled,
    queryFn: () => api<{ data: Ev[] }>(`/guilds/${guildId}/events?when=${tab}`), refetchInterval: 30_000,
  });
  const empty: Draft = { title: "", description: "", when: tomorrow20(), channel_id: null, max_slots: "", image_url: "" };
  const [draft, setDraft] = useState<Draft | null>(null);
  const [cancelling, setCancelling] = useState<Ev | null>(null);
  const past = !!draft?.when && isPastLocal(draft.when);
  const channelId = draft?.channel_id ?? form?.default_channel_id ?? null;

  const create = useMutation({
    mutationFn: (d: Draft) => api(`/guilds/${guildId}/events`, { method: "POST", json: {
      title: d.title, description: d.description, channel_id: channelId,
      starts_at: zonedToDate(d.when, browserTimeZone())!.toISOString(),
      max_slots: d.max_slots ? Number(d.max_slots) : null, image_url: d.image_url || null,
    } }),
    onSuccess: () => { toast.success(t("events.created")); setDraft(null); qc.invalidateQueries({ queryKey: ["events", guildId] }); },
    onError: (e) => toast.error(errorText(e, t("states.errorBody"))),
  });
  const cancel = useMutation({
    mutationFn: (e: Ev) => api(`/guilds/${guildId}/events/${e.id}/cancel`, { method: "POST" }),
    onSuccess: () => { setCancelling(null); qc.invalidateQueries({ queryKey: ["events", guildId] }); },
    onError: (e) => toast.error(errorText(e, t("states.errorBody"))),
  });
  const chName = (id: string) => channels?.find((c) => c.id === id)?.name ?? "?";

  return (
    <ModulePage ctl={ctl as never} title={t("nav.items.events")} description={t("events.description")}>
      {form && (
        <div className="space-y-6">
          {ctl.enabled && (
            <Card>
              <CardHeader icon={CalendarDays} title={t("events.list")} action={
                <div className="flex items-center gap-2">
                  <div role="group" className="flex rounded-lg border border-border p-0.5 text-[13px]">
                    {(["upcoming", "past"] as const).map((x) => (
                      <button key={x} type="button" aria-pressed={tab === x} onClick={() => setTab(x)} className={cn("min-h-8 rounded-md px-3", tab === x ? "bg-input" : "text-muted hover:text-text")}>{t(`events.${x}`)}</button>
                    ))}
                  </div>
                  {ctl.canEdit && <Button size="sm" onClick={() => setDraft(empty)}><Plus className="size-4" aria-hidden /> {t("events.new")}</Button>}
                </div>
              } />

              {draft && (
                <div className="space-y-4 border-b border-border bg-panel-hover/40 p-5">
                  <div className="grid gap-4 sm:grid-cols-2">
                    <Field id="ev-title" label={t("events.title")}><input id="ev-title" className={inputClass} maxLength={100} value={draft.title} onChange={(e) => setDraft({ ...draft, title: e.target.value })} /></Field>
                    <Field id="ev-when" label={t("scheduled.when", { tz: browserTimeZone() })} error={past ? t("scheduled.inPast") : undefined}>
                      <DateTimePicker id="ev-when" value={draft.when} minDate={new Date()} invalid={past} onChange={(v) => setDraft({ ...draft, when: v })} />
                    </Field>
                    <Field id="ev-channel" label={t("welcome.channel")}><ChannelSelect id="ev-channel" guildId={guildId} value={channelId} onChange={(v) => setDraft({ ...draft, channel_id: v })} needEmbed /></Field>
                    <Field id="ev-slots" label={t("events.slots")} help={t("events.slotsHelp")}><input id="ev-slots" type="number" min={1} max={1000} className={inputClass} value={draft.max_slots} onChange={(e) => setDraft({ ...draft, max_slots: e.target.value })} /></Field>
                    <Field id="ev-desc" label={t("editor.description")}><textarea id="ev-desc" rows={3} className={cn(inputClass, "py-2")} maxLength={1500} value={draft.description} onChange={(e) => setDraft({ ...draft, description: e.target.value })} /></Field>
                    <Field id="ev-img" label={t("events.image")} help={t("events.imageHelp")}>
                      <div className="flex gap-2">
                        {isMedia(draft.image_url) ? <MediaChip value={draft.image_url} onClear={() => setDraft({ ...draft, image_url: "" })} /> : (
                          <input id="ev-img" className={inputClass} placeholder="https://…" value={draft.image_url} onChange={(e) => setDraft({ ...draft, image_url: e.target.value })} />
                        )}
                        <MediaButton onPick={(u) => setDraft({ ...draft, image_url: u })} />
                      </div>
                    </Field>
                  </div>
                  <div className="flex justify-end gap-2">
                    <Button variant="secondary" onClick={() => setDraft(null)}>{t("common.cancel")}</Button>
                    <Button loading={create.isPending} disabled={!draft.title.trim() || !channelId || past || !!(draft.image_url && !draft.image_url.startsWith("https://") && !isMedia(draft.image_url))} onClick={() => create.mutate(draft)}>{t("events.publish")}</Button>
                  </div>
                </div>
              )}

              {list.isPending ? <Skeleton className="m-5 h-24" /> : !list.data?.data.length ? (
                <EmptyState icon={CalendarDays} title={t("events.none")} body={t("events.noneBody")} />
              ) : (
                <ul className="divide-y divide-border">
                  {list.data.data.map((e) => (
                    <li key={e.id} className="flex flex-wrap items-center gap-3 px-5 py-3 text-sm">
                      <div className="min-w-0 flex-1">
                        <p className="flex flex-wrap items-center gap-2 font-medium">{e.title}
                          {e.status !== "scheduled" && <Badge tone={e.status === "cancelled" ? "danger" : "success"}>{t(`events.status_${e.status}`)}</Badge>}
                        </p>
                        <p className="text-[12px] text-muted">
                          {format.dateTime(new Date(e.starts_at), { dateStyle: "full", timeStyle: "short" })} · #{chName(e.channel_id)}
                        </p>
                      </div>
                      <span className="text-[13px] tabular-nums">✅ {e.going}{e.max_slots ? `/${e.max_slots}` : ""} · ❔ {e.maybe} · ❌ {e.no}</span>
                      {e.url && <a href={e.url} target="_blank" rel="noreferrer" className="text-muted hover:text-text" aria-label={t("events.open")}><ExternalLink className="size-4" /></a>}
                      {ctl.canEdit && e.status === "scheduled" && <Button variant="ghost" size="sm" onClick={() => setCancelling(e)}><XCircle className="size-4" aria-hidden /> {t("events.cancel")}</Button>}
                    </li>
                  ))}
                </ul>
              )}
            </Card>
          )}

          <Card>
            <CardHeader icon={Settings2} title={t("welcome.settings")} />
            <fieldset disabled={!ctl.canEdit} className="grid gap-4 p-5 sm:grid-cols-2">
              <Field id="ev-default" label={t("events.defaultChannel")}><ChannelSelect id="ev-default" guildId={guildId} value={form.default_channel_id} onChange={(v) => set({ default_channel_id: v })} needEmbed /></Field>
              <Field id="ev-remind" label={t("events.reminder")} help={t("events.reminderHelp")}>
                <select id="ev-remind" className={inputClass} value={form.reminder_minutes} onChange={(e) => set({ reminder_minutes: Number(e.target.value) })}>
                  {[0, 5, 15, 30, 60, 180, 1440].map((m) => <option key={m} value={m}>{t(`events.rem_${m}`)}</option>)}
                </select>
              </Field>
              <Field id="ev-managers" label={t("events.managers")} help={t("events.managersHelp")}><RoleMultiSelect id="ev-managers" guildId={guildId} value={form.manager_role_ids} onChange={(v) => set({ manager_role_ids: v })} /></Field>
              <label className="flex items-center justify-between gap-4 self-end text-sm">{t("events.ping")}<Switch checked={form.ping_at_start} label={t("events.ping")} onCheckedChange={(v) => set({ ping_at_start: v })} /></label>
            </fieldset>
          </Card>
        </div>
      )}
      <ConfirmDialog open={cancelling !== null} title={t("events.cancelTitle", { title: cancelling?.title ?? "" })} body={t("events.cancelBody")}
        confirmLabel={t("events.cancel")} destructive onCancel={() => setCancelling(null)} onConfirm={() => cancelling && cancel.mutate(cancelling)} />
    </ModulePage>
  );
}
