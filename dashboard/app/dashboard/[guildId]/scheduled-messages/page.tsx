"use client";

import * as Dialog from "@radix-ui/react-dialog";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarClock, Pencil, Plus, Send, Trash2, X } from "lucide-react";
import { useFormatter, useTranslations } from "next-intl";
import { useState } from "react";
import { toast } from "sonner";

import { ChannelSelect, useChannels } from "@/components/channel-select";
import { DateTimePicker } from "@/components/datetime-picker";
import { DiscordPreview } from "@/components/discord-preview";
import { MessageEditor } from "@/components/message-editor";
import { ModulePage } from "@/components/module-page";
import { ConfirmDialog } from "@/components/save-bar";
import { Badge, Button, Card, CardHeader, EmptyState, Field, inputClass, Skeleton, Switch } from "@/components/ui";
import { api, ApiError, errorText } from "@/lib/api";
import { browserTimeZone, isPastLocal, toBrowserLocal } from "@/lib/datetime";
import { useGuildId } from "@/lib/hooks";
import { clean, type MessageTemplate } from "@/lib/messages";
import { useModuleConfig } from "@/lib/use-module";
import { useSample } from "@/lib/use-sample";

type Msg = {
  id?: string; name: string; channel_id: string | null; message: MessageTemplate; local_time: string; timezone?: string | null;
  repeat: "none" | "daily" | "weekly" | "monthly"; status?: string; version?: number; next_run_at?: string | null;
  last_sent_at?: string | null; last_error?: string | null;
};

function tomorrowAt9(): string {
  const d = new Date(Date.now() + 86400000);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}T09:00`;
}

export default function ScheduledPage() {
  const t = useTranslations();
  const format = useFormatter();
  const guildId = useGuildId();
  const qc = useQueryClient();
  const ctl = useModuleConfig<Record<string, never>>(guildId, "scheduled_messages");
  const q = useQuery({ queryKey: ["scheduled", guildId], queryFn: () => api<{ data: Msg[]; timezone: string; can_edit: boolean }>(`/guilds/${guildId}/scheduled-messages`) });
  const { data: channels } = useChannels(guildId);
  const [editing, setEditing] = useState<Msg | null>(null);
  const [deleting, setDeleting] = useState<Msg | null>(null);
  const sendNow = useMutation({
    mutationFn: (m: Msg) => api(`/guilds/${guildId}/scheduled-messages/${m.id}/send-now`, { method: "POST" }),
    onSuccess: () => toast.success(t("embeds.sent")),
    onError: (e) => toast.error(errorText(e, t("states.errorBody"))),
  });
  const remove = useMutation({
    mutationFn: (m: Msg) => api(`/guilds/${guildId}/scheduled-messages/${m.id}`, { method: "DELETE" }),
    onSuccess: () => { setDeleting(null); qc.invalidateQueries({ queryKey: ["scheduled", guildId] }); },
  });

  return (
    <ModulePage ctl={ctl as never} title={t("nav.items.scheduled_messages")} description={t("scheduled.description", { tz: browserTimeZone() })}>
      <Card>
        <CardHeader icon={CalendarClock} title={t("scheduled.list")} action={
          q.data?.can_edit && <Button size="sm" onClick={() => setEditing({ name: "", channel_id: null, message: { content: "", embeds: [] }, local_time: tomorrowAt9(), repeat: "none" })}><Plus className="size-4" aria-hidden /> {t("scheduled.new")}</Button>
        } />
        {q.isPending ? <Skeleton className="m-5 h-32" /> : !q.data?.data.length ? <EmptyState icon={CalendarClock} title={t("scheduled.none")} body={t("scheduled.noneBody")} /> : (
          <ul className="divide-y divide-border">
            {q.data.data.map((m) => (
              <li key={m.id} className="flex flex-wrap items-center gap-3 px-5 py-3 text-sm">
                <div className="min-w-0 flex-1">
                  <p className="flex flex-wrap items-center gap-2 font-medium">{m.name}
                    <Badge tone={m.status === "scheduled" ? "success" : m.status === "failed" ? "danger" : "neutral"}>{t(`scheduled.status_${m.status}`)}</Badge>
                    {m.repeat !== "none" && <Badge tone="primary">{t(`scheduled.repeat_${m.repeat}`)}</Badge>}
                  </p>
                  <p className="text-[12px] text-muted">
                    #{channels?.find((c) => c.id === m.channel_id)?.name ?? "?"} · {m.next_run_at ? t("scheduled.next", { date: format.dateTime(new Date(m.next_run_at), { dateStyle: "medium", timeStyle: "short" }) }) : t("scheduled.noNext")}
                  </p>
                  {m.last_error && <p className="text-[12px] text-danger">{m.last_error}</p>}
                </div>
                {q.data.can_edit && (
                  <>
                    <Button size="sm" variant="secondary" loading={sendNow.isPending && sendNow.variables?.id === m.id} onClick={() => sendNow.mutate(m)}><Send className="size-4" aria-hidden /> {t("scheduled.sendNow")}</Button>
                    <Button variant="ghost" size="sm" onClick={() => setEditing(m)} aria-label={t("automod.edit")}><Pencil className="size-4" /></Button>
                    <Button variant="ghost" size="sm" onClick={() => setDeleting(m)} aria-label={t("automod.delete")}><Trash2 className="size-4" /></Button>
                  </>
                )}
              </li>
            ))}
          </ul>
        )}
      </Card>
      {editing && <Editor guildId={guildId} msg={editing} tz={q.data?.timezone ?? "UTC"} onClose={() => setEditing(null)} />}
      <ConfirmDialog open={deleting !== null} title={t("automod.deleteTitle", { name: deleting?.name ?? "" })} body={t("scheduled.deleteBody")} confirmLabel={t("automod.delete")} destructive onCancel={() => setDeleting(null)} onConfirm={() => deleting && remove.mutate(deleting)} />
    </ModulePage>
  );
}

function Editor({ guildId, msg, tz, onClose }: { guildId: string; msg: Msg; tz: string; onClose: () => void }) {
  const t = useTranslations();
  const qc = useQueryClient();
  const myTz = browserTimeZone();
  // Un mensaje guardado en otra zona horaria se muestra convertido a la del navegador (mismo instante).
  // (Un mensaje nuevo ya viene con la hora del navegador.)
  const [m, setM] = useState<Msg>(() => (msg.id ? { ...msg, local_time: toBrowserLocal(msg.local_time, msg.timezone || tz) } : msg));
  const [paused, setPaused] = useState(msg.status === "paused");
  const { data: channels } = useChannels(guildId);
  const { sample, color } = useSample(guildId, channels?.find((c) => c.id === m.channel_id)?.name ?? null);
  const set = (x: Partial<Msg>) => setM({ ...m, ...x });
  const body = () => ({ name: m.name, channel_id: m.channel_id, message: clean(m.message), local_time: m.local_time, timezone: myTz, repeat: m.repeat, paused });
  const [err, setErr] = useState<string | null>(null);
  const past = !!m.local_time && isPastLocal(m.local_time);
  const save = useMutation({
    mutationFn: () => (m.id ? api(`/guilds/${guildId}/scheduled-messages/${m.id}`, { method: "PUT", json: { ...body(), version: m.version } }) : api(`/guilds/${guildId}/scheduled-messages`, { method: "POST", json: body() })),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["scheduled", guildId] }); toast.success(t("settings.saved")); onClose(); },
    onError: (e) => { if (e instanceof ApiError && e.fields?.local_time) setErr(t("scheduled.inPast")); toast.error(errorText(e, t("states.errorBody"))); },
  });
  return (
    <Dialog.Root open onOpenChange={(o) => !o && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/60" />
        <Dialog.Content className="fixed inset-y-0 right-0 z-50 flex w-[min(1000px,100vw)] flex-col border-l border-border bg-sidebar">
          <div className="flex items-center justify-between border-b border-border px-6 py-4">
            <Dialog.Title className="text-lg font-semibold">{m.id ? m.name : t("scheduled.new")}</Dialog.Title>
            <Dialog.Close className="grid size-9 place-items-center rounded-lg text-muted hover:bg-panel-hover" aria-label={t("common.close")}><X className="size-5" /></Dialog.Close>
          </div>
          <div className="grid flex-1 gap-6 overflow-y-auto p-6 lg:grid-cols-[minmax(0,1fr)_380px]">
            <div className="space-y-4">
              <div className="grid gap-4 sm:grid-cols-2">
                <Field id="sm-name" label={t("automod.name")}><input id="sm-name" className={inputClass} value={m.name} maxLength={80} onChange={(e) => set({ name: e.target.value })} /></Field>
                <Field id="sm-channel" label={t("welcome.channel")}><ChannelSelect id="sm-channel" guildId={guildId} value={m.channel_id} onChange={(v) => set({ channel_id: v })} needEmbed={m.message.embeds.length > 0} /></Field>
                <Field id="sm-time" label={t("scheduled.when", { tz: myTz })} error={err ?? (past && !paused ? t("scheduled.inPast") : undefined)}>
                  <DateTimePicker id="sm-time" value={m.local_time} minDate={new Date()} invalid={past && !paused}
                    onChange={(v) => { setErr(null); set({ local_time: v }); }} />
                </Field>
                <Field id="sm-repeat" label={t("scheduled.repeat")}>
                  <select id="sm-repeat" className={inputClass} value={m.repeat} onChange={(e) => set({ repeat: e.target.value as Msg["repeat"] })}>
                    {(["none", "daily", "weekly", "monthly"] as const).map((r) => <option key={r} value={r}>{t(`scheduled.repeat_${r}`)}</option>)}
                  </select>
                </Field>
              </div>
              <label className="flex items-center gap-3 text-sm"><Switch checked={paused} label={t("scheduled.paused")} onCheckedChange={setPaused} />{t("scheduled.paused")}</label>
              <MessageEditor idPrefix="sm" value={m.message} onChange={(x) => set({ message: x })} defaultColor={color} />
              <p className="text-[12px] text-muted">{t("scheduled.mentionsNote")}</p>
            </div>
            <div className="space-y-3 lg:sticky lg:top-0">
              <h3 className="text-sm font-semibold">{t("editor.preview")}</h3>
              <DiscordPreview template={m.message} sample={sample} color={color} />
            </div>
          </div>
          <div className="flex justify-end gap-2 border-t border-border px-6 py-4">
            <Button variant="secondary" onClick={onClose}>{t("common.cancel")}</Button>
            <Button loading={save.isPending} disabled={!m.name.trim() || !m.channel_id || !m.local_time || (past && !paused)} onClick={() => save.mutate()}>{t("common.save")}</Button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
