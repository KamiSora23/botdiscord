"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ExternalLink, Plus, Send, Ticket, Trash2 } from "lucide-react";
import { useFormatter, useTranslations } from "next-intl";
import { useState } from "react";
import { toast } from "sonner";

import { ChannelSelect, useChannels } from "@/components/channel-select";
import { DiscordPreview } from "@/components/discord-preview";
import { MessageEditor } from "@/components/message-editor";
import { ModulePage } from "@/components/module-page";
import { RoleMultiSelect } from "@/components/multi-select";
import { Badge, Button, Card, CardHeader, EmptyState, Field, inputClass, Switch } from "@/components/ui";
import { api, errorText } from "@/lib/api";
import { useGuildId } from "@/lib/hooks";
import { clean, type MessageTemplate } from "@/lib/messages";
import { useModuleConfig } from "@/lib/use-module";
import { useSample } from "@/lib/use-sample";
import { cn } from "@/lib/utils";

type Panel = {
  id: string;
  name: string;
  channel_id: string | null;
  message_id: string | null;
  message: MessageTemplate;
  button_label: string;
  button_emoji: string | null;
  category_channel_id: string | null;
  support_role_ids: string[];
  opening_message: string;
  ask_subject: boolean;
};
type Cfg = { panels: Panel[]; transcript_channel_id: string | null; max_open_per_user: number; auto_close_hours: number | null; dm_transcript: boolean };
type TicketRow = { number: number; creator: { id: string; name: string }; channel_id: string | null; status: string; subject: string | null; opened_at: string; closed_at: string | null; close_reason: string | null };

function hex8() {
  return Array.from(crypto.getRandomValues(new Uint8Array(4)), (b) => b.toString(16).padStart(2, "0")).join("");
}

export default function TicketsPage() {
  const t = useTranslations();
  const guildId = useGuildId();
  const qc = useQueryClient();
  const ctl = useModuleConfig<Cfg>(guildId, "tickets", (c) => ({ ...c, panels: c.panels.map((p) => ({ ...p, message: clean(p.message), button_emoji: p.button_emoji || null })) }));
  const form = ctl.form;
  const set = (p: Partial<Cfg>) => form && ctl.setForm({ ...form, ...p });
  const [active, setActive] = useState(0);
  const { data: channels } = useChannels(guildId);
  const categories = (channels ?? []).filter((c) => c.type === "category");
  const panel = form?.panels[active];
  const { sample, color } = useSample(guildId, channels?.find((c) => c.id === panel?.channel_id)?.name ?? null);
  const setPanel = (p: Partial<Panel>) => form && set({ panels: form.panels.map((x, i) => (i === active ? { ...x, ...p } : x)) });
  const [status, setStatus] = useState<"open" | "closed">("open");
  const tickets = useQuery({ queryKey: ["tickets", guildId, status], queryFn: () => api<{ open_count: number; data: TicketRow[] }>(`/guilds/${guildId}/tickets?status=${status}`) });

  const publish = useMutation({
    mutationFn: (id: string) => api(`/guilds/${guildId}/tickets/panels/${id}/publish`, { method: "POST" }),
    onSuccess: () => { toast.success(t("rr.published")); ctl.query.refetch().then(() => ctl.discard()); },
    onError: (e) => toast.error(errorText(e, t("states.errorBody"))),
  });
  const close = useMutation({
    mutationFn: (n: number) => api(`/guilds/${guildId}/tickets/${n}/close`, { method: "POST", json: { reason: null } }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["tickets", guildId] }),
    onError: (e) => toast.error(errorText(e, t("states.errorBody"))),
  });

  return (
    <ModulePage ctl={ctl as never} title={t("nav.items.tickets")} description={t("tickets.description")}>
      {form && (
        <div className="space-y-6">
          <Card>
            <CardHeader icon={Ticket} title={t("tickets.panels")} description={t("tickets.panelsHelp")} />
            <div className="flex flex-wrap gap-2 border-b border-border p-4">
              {form.panels.map((p, i) => (
                <button key={p.id} type="button" onClick={() => setActive(i)} className={cn("min-h-9 rounded-lg px-3 text-sm", i === active ? "bg-primary-solid text-white" : "bg-input text-muted hover:text-text")}>
                  {p.name}
                </button>
              ))}
              {form.panels.length < 5 && ctl.canEdit && (
                <Button size="sm" variant="secondary" onClick={() => { set({ panels: [...form.panels, { ...(form.panels[0] ?? emptyPanel()), id: hex8(), name: t("tickets.newPanel"), message_id: null }] }); setActive(form.panels.length); }}>
                  <Plus className="size-4" aria-hidden /> {t("tickets.addPanel")}
                </Button>
              )}
            </div>
            {panel ? (
              <div className="grid gap-6 p-5 xl:grid-cols-[minmax(0,1fr)_400px]">
                <fieldset disabled={!ctl.canEdit} className="space-y-4">
                  <div className="grid gap-4 sm:grid-cols-2">
                    <Field id="tk-name" label={t("automod.name")}><input id="tk-name" className={inputClass} value={panel.name} maxLength={60} onChange={(e) => setPanel({ name: e.target.value })} /></Field>
                    <Field id="tk-channel" label={t("tickets.panelChannel")}><ChannelSelect id="tk-channel" guildId={guildId} value={panel.channel_id} onChange={(v) => setPanel({ channel_id: v, message_id: v === panel.channel_id ? panel.message_id : null })} needEmbed /></Field>
                    <Field id="tk-label" label={t("tickets.buttonLabel")}><input id="tk-label" className={inputClass} value={panel.button_label} maxLength={80} onChange={(e) => setPanel({ button_label: e.target.value })} /></Field>
                    <Field id="tk-emoji" label="Emoji"><input id="tk-emoji" className={inputClass} value={panel.button_emoji ?? ""} maxLength={64} onChange={(e) => setPanel({ button_emoji: e.target.value })} /></Field>
                    <Field id="tk-category" label={t("tickets.category")} help={t("tickets.categoryHelp")}>
                      <select id="tk-category" className={inputClass} value={panel.category_channel_id ?? ""} onChange={(e) => setPanel({ category_channel_id: e.target.value || null })}>
                        <option value="">{t("tickets.noCategory")}</option>
                        {categories.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
                      </select>
                    </Field>
                    <Field id="tk-roles" label={t("tickets.supportRoles")}><RoleMultiSelect id="tk-roles" guildId={guildId} value={panel.support_role_ids} onChange={(v) => setPanel({ support_role_ids: v })} /></Field>
                  </div>
                  <Field id="tk-opening" label={t("tickets.opening")} help={t("tickets.openingHelp")}>
                    <textarea id="tk-opening" rows={3} className={cn(inputClass, "py-2")} value={panel.opening_message} maxLength={2000} onChange={(e) => setPanel({ opening_message: e.target.value })} />
                  </Field>
                  <label className="flex items-center justify-between gap-4 text-sm">{t("tickets.askSubject")}<Switch checked={panel.ask_subject} label={t("tickets.askSubject")} onCheckedChange={(v) => setPanel({ ask_subject: v })} /></label>
                  <h3 className="pt-2 text-sm font-semibold">{t("tickets.panelMessage")}</h3>
                  <MessageEditor idPrefix={`tk-${panel.id}`} value={panel.message} onChange={(m) => setPanel({ message: m })} defaultColor={color} />
                  {form.panels.length > 1 && (
                    <Button variant="ghost" onClick={() => { set({ panels: form.panels.filter((_, i) => i !== active) }); setActive(0); }}>
                      <Trash2 className="size-4" aria-hidden /> {t("tickets.removePanel")}
                    </Button>
                  )}
                </fieldset>
                <div className="space-y-3">
                  <DiscordPreview template={panel.message} sample={sample} color={color} />
                  <div className="-mt-3 rounded-b-xl bg-[#313338] px-4 pb-4 pl-[72px]">
                    <span className="inline-flex h-8 items-center gap-1.5 rounded bg-[#5865f2] px-4 text-sm font-medium text-white">{panel.button_emoji}{panel.button_label}</span>
                  </div>
                  <Button className="w-full" variant="secondary" disabled={!panel.channel_id || ctl.dirty || !ctl.canEdit} loading={publish.isPending} onClick={() => publish.mutate(panel.id)}>
                    <Send className="size-4" aria-hidden /> {panel.message_id ? t("rr.update") : t("rr.publish")}
                  </Button>
                  {ctl.dirty && <p className="text-[12px] text-muted">{t("welcome.saveFirst")}</p>}
                </div>
              </div>
            ) : (
              <EmptyState icon={Ticket} title={t("tickets.noPanels")} />
            )}
          </Card>

          <Card>
            <CardHeader title={t("tickets.options")} />
            <fieldset disabled={!ctl.canEdit} className="grid gap-4 p-5 sm:grid-cols-2">
              <Field id="tk-transcripts" label={t("tickets.transcripts")} help={t("tickets.transcriptsHelp")}><ChannelSelect id="tk-transcripts" guildId={guildId} value={form.transcript_channel_id} onChange={(v) => set({ transcript_channel_id: v })} /></Field>
              <Field id="tk-max" label={t("tickets.maxOpen")}>
                <select id="tk-max" className={inputClass} value={form.max_open_per_user} onChange={(e) => set({ max_open_per_user: Number(e.target.value) })}>{[1, 2, 3, 4, 5].map((n) => <option key={n} value={n}>{n}</option>)}</select>
              </Field>
              <Field id="tk-auto" label={t("tickets.autoClose")}>
                <select id="tk-auto" className={inputClass} value={form.auto_close_hours ?? ""} onChange={(e) => set({ auto_close_hours: e.target.value ? Number(e.target.value) : null })}>
                  <option value="">{t("tickets.never")}</option>
                  {[12, 24, 48, 72, 168].map((h) => <option key={h} value={h}>{t("duration.nHours", { n: h })}</option>)}
                </select>
              </Field>
              <label className="flex items-center justify-between gap-4 self-end pb-2 text-sm">{t("tickets.dmTranscript")}<Switch checked={form.dm_transcript} label={t("tickets.dmTranscript")} onCheckedChange={(v) => set({ dm_transcript: v })} /></label>
            </fieldset>
          </Card>

          <TicketList tickets={tickets.data?.data ?? []} status={status} setStatus={setStatus} guildId={guildId} onClose={(n) => close.mutate(n)} canEdit={ctl.canEdit} openCount={tickets.data?.open_count ?? 0} />
        </div>
      )}
    </ModulePage>
  );
}

function emptyPanel(): Panel {
  return { id: hex8(), name: "Soporte", channel_id: null, message_id: null, message: { content: "🎫", embeds: [] }, button_label: "Abrir ticket", button_emoji: "🎫", category_channel_id: null, support_role_ids: [], opening_message: "Hola {user}", ask_subject: false };
}

function TicketList({ tickets, status, setStatus, guildId, onClose, canEdit, openCount }: {
  tickets: TicketRow[]; status: "open" | "closed"; setStatus: (s: "open" | "closed") => void; guildId: string; onClose: (n: number) => void; canEdit: boolean; openCount: number;
}) {
  const t = useTranslations();
  const format = useFormatter();
  return (
    <Card className="overflow-hidden">
      <CardHeader title={t("tickets.list")} action={
        <div className="flex rounded-lg border border-border p-0.5 text-[13px]">
          {(["open", "closed"] as const).map((s) => (
            <button key={s} type="button" aria-pressed={status === s} onClick={() => setStatus(s)} className={cn("min-h-8 rounded-md px-3", status === s ? "bg-input" : "text-muted")}>
              {t(`tickets.status_${s}`)}{s === "open" ? ` (${openCount})` : ""}
            </button>
          ))}
        </div>
      } />
      {tickets.length === 0 ? <p className="px-5 py-8 text-center text-[13px] text-muted">{t("tickets.none")}</p> : (
        <ul className="divide-y divide-border">
          {tickets.map((tk) => (
            <li key={tk.number} className="flex flex-wrap items-center gap-3 px-5 py-3 text-sm">
              <span className="font-mono text-muted">#{tk.number}</span>
              <span className="font-medium">{tk.creator.name}</span>
              {tk.subject && <span className="max-w-xs truncate text-muted">{tk.subject}</span>}
              <span className="ml-auto text-[12px] text-muted">{format.relativeTime(new Date(tk.closed_at ?? tk.opened_at))}</span>
              {tk.status === "open" ? (
                <>
                  {tk.channel_id && <a className="inline-flex items-center gap-1 text-[13px] text-primary-text hover:underline" href={`https://discord.com/channels/${guildId}/${tk.channel_id}`} target="_blank" rel="noopener noreferrer">Discord <ExternalLink className="size-3.5" aria-hidden /></a>}
                  {canEdit && <Button size="sm" variant="secondary" onClick={() => onClose(tk.number)}>{t("tickets.close")}</Button>}
                </>
              ) : <Badge>{tk.close_reason ? tk.close_reason.slice(0, 40) : t("tickets.status_closed")}</Badge>}
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
