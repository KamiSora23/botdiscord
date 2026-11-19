"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ExternalLink, ListChecks, ThumbsDown, ThumbsUp } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { toast } from "sonner";

import { ChannelSelect } from "@/components/channel-select";
import { ModulePage } from "@/components/module-page";
import { RoleMultiSelect } from "@/components/multi-select";
import { Badge, Button, Card, CardHeader, EmptyState, Field, inputClass, Switch } from "@/components/ui";
import { api, errorText } from "@/lib/api";
import { useGuildId } from "@/lib/hooks";
import { useModuleConfig } from "@/lib/use-module";
import { cn } from "@/lib/utils";

type Cfg = { channel_id: string | null; create_thread: boolean; staff_role_ids: string[]; anonymous: boolean };
type Row = { number: number; author: { name: string }; content: string; status: string; upvotes: number; downvotes: number; staff_response: string | null; jump_url: string | null };
const STATUSES = ["pending", "approved", "in_progress", "implemented", "denied"] as const;
const TONE: Record<string, "primary" | "success" | "danger" | "warning" | "neutral"> = { pending: "primary", approved: "success", denied: "danger", in_progress: "warning", implemented: "success" };

export default function SuggestionsPage() {
  const t = useTranslations();
  const guildId = useGuildId();
  const qc = useQueryClient();
  const ctl = useModuleConfig<Cfg>(guildId, "suggestions");
  const form = ctl.form;
  const set = (p: Partial<Cfg>) => form && ctl.setForm({ ...form, ...p });
  const [filter, setFilter] = useState("");
  const list = useQuery({ queryKey: ["suggestions", guildId, filter], queryFn: () => api<{ data: Row[] }>(`/guilds/${guildId}/suggestions${filter ? `?status=${filter}` : ""}`) });
  const [editing, setEditing] = useState<{ number: number; status: string; response: string } | null>(null);
  const respond = useMutation({
    mutationFn: () => api(`/guilds/${guildId}/suggestions/${editing!.number}/respond`, { method: "POST", json: { status: editing!.status, response: editing!.response || null } }),
    onSuccess: () => { setEditing(null); qc.invalidateQueries({ queryKey: ["suggestions", guildId] }); toast.success(t("settings.saved")); },
    onError: (e) => toast.error(errorText(e, t("states.errorBody"))),
  });

  return (
    <ModulePage ctl={ctl as never} title={t("nav.items.suggestions")} description={t("suggestions.description")}>
      {form && (
        <div className="space-y-6">
          <Card>
            <CardHeader icon={ListChecks} title={t("welcome.settings")} />
            <fieldset disabled={!ctl.canEdit} className="grid gap-4 p-5 sm:grid-cols-2">
              <Field id="sg-channel" label={t("suggestions.channel")} help={t("suggestions.channelHelp")}><ChannelSelect id="sg-channel" guildId={guildId} value={form.channel_id} onChange={(v) => set({ channel_id: v })} needEmbed /></Field>
              <Field id="sg-staff" label={t("suggestions.staff")} help={t("suggestions.staffHelp")}><RoleMultiSelect id="sg-staff" guildId={guildId} value={form.staff_role_ids} onChange={(v) => set({ staff_role_ids: v })} /></Field>
              <label className="flex items-center justify-between gap-4 text-sm">{t("suggestions.thread")}<Switch checked={form.create_thread} label={t("suggestions.thread")} onCheckedChange={(v) => set({ create_thread: v })} /></label>
              <label className="flex items-center justify-between gap-4 text-sm">{t("suggestions.anonymous")}<Switch checked={form.anonymous} label={t("suggestions.anonymous")} onCheckedChange={(v) => set({ anonymous: v })} /></label>
            </fieldset>
          </Card>
          <Card className="overflow-hidden">
            <CardHeader title={t("suggestions.list")} action={
              <select className={cn(inputClass, "w-44")} value={filter} onChange={(e) => setFilter(e.target.value)} aria-label={t("suggestions.status")}>
                <option value="">{t("suggestions.all")}</option>
                {STATUSES.map((s) => <option key={s} value={s}>{t(`suggestions.status_${s}`)}</option>)}
              </select>
            } />
            {!list.data?.data.length ? <EmptyState icon={ListChecks} title={t("suggestions.none")} body={t("suggestions.noneBody")} /> : (
              <ul className="divide-y divide-border">
                {list.data.data.map((s) => (
                  <li key={s.number} className="space-y-2 px-5 py-4">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-mono text-[13px] text-muted">#{s.number}</span>
                      <Badge tone={TONE[s.status]}>{t(`suggestions.status_${s.status}`)}</Badge>
                      <span className="text-[13px] text-muted">{s.author.name}</span>
                      <span className="ml-auto inline-flex items-center gap-3 text-[13px] text-muted">
                        <span className="inline-flex items-center gap-1"><ThumbsUp className="size-3.5" aria-hidden />{s.upvotes}</span>
                        <span className="inline-flex items-center gap-1"><ThumbsDown className="size-3.5" aria-hidden />{s.downvotes}</span>
                        {s.jump_url && <a href={s.jump_url} target="_blank" rel="noopener noreferrer" className="text-primary-text" aria-label="Discord"><ExternalLink className="size-3.5" /></a>}
                      </span>
                    </div>
                    <p className="whitespace-pre-wrap text-sm">{s.content}</p>
                    {s.staff_response && <p className="border-l-2 border-primary pl-3 text-[13px] text-muted">{s.staff_response}</p>}
                    {editing?.number === s.number ? (
                      <div className="flex flex-wrap gap-2">
                        <select className={cn(inputClass, "w-44")} value={editing.status} onChange={(e) => setEditing({ ...editing, status: e.target.value })} aria-label={t("suggestions.status")}>
                          {STATUSES.map((x) => <option key={x} value={x}>{t(`suggestions.status_${x}`)}</option>)}
                        </select>
                        <input className={cn(inputClass, "min-w-56 flex-1")} placeholder={t("suggestions.response")} value={editing.response} maxLength={1000} onChange={(e) => setEditing({ ...editing, response: e.target.value })} aria-label={t("suggestions.response")} />
                        <Button loading={respond.isPending} onClick={() => respond.mutate()}>{t("common.save")}</Button>
                        <Button variant="ghost" onClick={() => setEditing(null)}>{t("common.cancel")}</Button>
                      </div>
                    ) : ctl.canEdit && (
                      <Button size="sm" variant="secondary" onClick={() => setEditing({ number: s.number, status: s.status, response: s.staff_response ?? "" })}>{t("suggestions.respond")}</Button>
                    )}
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
