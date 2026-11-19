"use client";

import * as Dialog from "@radix-ui/react-dialog";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { GitBranch, Pencil, PlayCircle, PlugZap, Plus, Rss, Send, Trash2, Tv, X } from "lucide-react";
import { useFormatter, useTranslations } from "next-intl";
import { useState } from "react";
import { toast } from "sonner";

import { ChannelSelect } from "@/components/channel-select";
import { DiscordPreview } from "@/components/discord-preview";
import { MessageEditor } from "@/components/message-editor";
import { ModulePage } from "@/components/module-page";
import { ConfirmDialog } from "@/components/save-bar";
import { Badge, Button, Card, CardHeader, EmptyState, Field, inputClass, Notice, Switch } from "@/components/ui";
import { api, ApiError, errorText } from "@/lib/api";
import { useGuildId } from "@/lib/hooks";
import { clean, type MessageTemplate } from "@/lib/messages";
import { useModuleConfig } from "@/lib/use-module";
import { useSample } from "@/lib/use-sample";
import { cn } from "@/lib/utils";

type Provider = "youtube" | "twitch" | "rss" | "github";
type Integ = {
  id?: string; provider: Provider; external_id?: string; source?: string; display_name?: string | null; channel_id: string | null;
  message: MessageTemplate; enabled: boolean; status?: string; last_error?: string | null; version?: number;
  last_checked_at?: string | null; last_event_at?: string | null;
};
type ListResp = { data: Integ[]; can_edit: boolean; twitch_available: boolean; defaults: Record<Provider, MessageTemplate> };

const ICONS: Record<Provider, typeof Rss> = { youtube: PlayCircle, twitch: Tv, rss: Rss, github: GitBranch };
const EXTRA_VARS = ["title", "url", "author", "name", "thumbnail"] as const;

function sourceOf(i: Integ): string {
  if (i.source) return i.source;
  if (i.provider === "youtube") return `https://www.youtube.com/channel/${i.external_id}`;
  if (i.provider === "twitch") return `https://twitch.tv/${i.external_id}`;
  if (i.provider === "github") return `https://github.com/${i.external_id}`;
  return i.external_id ?? "";
}

export default function IntegrationsPage() {
  const t = useTranslations();
  const format = useFormatter();
  const guildId = useGuildId();
  const qc = useQueryClient();
  const ctl = useModuleConfig<Record<string, never>>(guildId, "integrations");
  const q = useQuery({ queryKey: ["integrations", guildId], queryFn: () => api<ListResp>(`/guilds/${guildId}/integrations`), refetchInterval: 60_000 });
  const [editing, setEditing] = useState<Integ | null>(null);
  const [deleting, setDeleting] = useState<Integ | null>(null);
  const test = useMutation({
    mutationFn: (i: Integ) => api(`/guilds/${guildId}/integrations/${i.id}/test`, { method: "POST" }),
    onSuccess: () => toast.success(t("integrations.testSent")),
    onError: (e) => toast.error(errorText(e, t("states.errorBody"))),
  });
  const remove = useMutation({
    mutationFn: (i: Integ) => api(`/guilds/${guildId}/integrations/${i.id}`, { method: "DELETE" }),
    onSuccess: () => { setDeleting(null); qc.invalidateQueries({ queryKey: ["integrations", guildId] }); },
  });

  return (
    <ModulePage ctl={ctl as never} title={t("nav.items.integrations")} description={t("integrations.description")}>
      <div className="space-y-6">
        {q.data && !q.data.twitch_available && <Notice tone="info">{t("integrations.twitchMissing")}</Notice>}
        <Card>
          <CardHeader icon={PlugZap} title={t("integrations.list")} action={
            q.data?.can_edit && (
              <div className="flex flex-wrap gap-2">
                {(["youtube", "twitch", "rss", "github"] as const).map((p) => {
                  const Icon = ICONS[p];
                  return (
                    <Button key={p} size="sm" variant="secondary" disabled={p === "twitch" && !q.data?.twitch_available}
                      onClick={() => setEditing({ provider: p, source: "", channel_id: null, message: q.data!.defaults[p], enabled: true })}>
                      <Plus className="size-3.5" aria-hidden /><Icon className="size-4" aria-hidden /> {t(`integrations.p_${p}`)}
                    </Button>
                  );
                })}
              </div>
            )
          } />
          {!q.data?.data.length ? <EmptyState icon={PlugZap} title={t("integrations.none")} body={t("integrations.noneBody")} /> : (
            <ul className="divide-y divide-border">
              {q.data.data.map((i) => {
                const Icon = ICONS[i.provider];
                return (
                  <li key={i.id} className="flex flex-wrap items-center gap-3 px-5 py-3 text-sm">
                    <span className="grid size-9 place-items-center rounded-lg bg-input"><Icon className="size-4 text-muted" aria-hidden /></span>
                    <div className="min-w-0 flex-1">
                      <p className="flex flex-wrap items-center gap-2 font-medium">
                        {i.display_name ?? i.external_id}
                        {!i.enabled ? <Badge>{t("common.disabled")}</Badge> : i.status === "error" ? <Badge tone="danger">{t("integrations.error")}</Badge> : i.status === "ok" ? <Badge tone="success">{t("integrations.ok")}</Badge> : <Badge>{t("integrations.pending")}</Badge>}
                      </p>
                      <p className="text-[12px] text-muted">
                        {t(`integrations.p_${i.provider}`)} · {i.last_checked_at ? t("integrations.checked", { when: format.relativeTime(new Date(i.last_checked_at)) }) : t("integrations.notChecked")}
                        {i.last_event_at && ` · ${t("integrations.lastPost", { when: format.relativeTime(new Date(i.last_event_at)) })}`}
                      </p>
                      {i.last_error && <p className="text-[12px] text-danger">{t.has(`integrations.err_${i.last_error}`) ? t(`integrations.err_${i.last_error}`) : i.last_error}</p>}
                    </div>
                    {q.data.can_edit && (
                      <>
                        <Button size="sm" variant="secondary" loading={test.isPending && test.variables?.id === i.id} onClick={() => test.mutate(i)}><Send className="size-4" aria-hidden /> {t("integrations.test")}</Button>
                        <Button variant="ghost" size="sm" onClick={() => setEditing({ ...i, source: sourceOf(i) })} aria-label={t("automod.edit")}><Pencil className="size-4" /></Button>
                        <Button variant="ghost" size="sm" onClick={() => setDeleting(i)} aria-label={t("automod.delete")}><Trash2 className="size-4" /></Button>
                      </>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
        </Card>
        <p className="text-[12px] text-muted">{t("integrations.howItWorks")}</p>
      </div>
      {editing && <Editor guildId={guildId} integ={editing} onClose={() => setEditing(null)} />}
      <ConfirmDialog open={deleting !== null} title={t("automod.deleteTitle", { name: deleting?.display_name ?? "" })} body={t("integrations.deleteBody")} confirmLabel={t("automod.delete")} destructive onCancel={() => setDeleting(null)} onConfirm={() => deleting && remove.mutate(deleting)} />
    </ModulePage>
  );
}

function Editor({ guildId, integ, onClose }: { guildId: string; integ: Integ; onClose: () => void }) {
  const t = useTranslations();
  const qc = useQueryClient();
  const [i, setI] = useState<Integ>(integ);
  const [sourceErr, setSourceErr] = useState<string | null>(null);
  const { sample, color } = useSample(guildId, null);
  const set = (x: Partial<Integ>) => setI({ ...i, ...x });
  const save = useMutation({
    mutationFn: () => {
      const body = { provider: i.provider, source: i.source, channel_id: i.channel_id, message: clean(i.message), enabled: i.enabled };
      return i.id ? api(`/guilds/${guildId}/integrations/${i.id}`, { method: "PUT", json: { ...body, version: i.version } }) : api(`/guilds/${guildId}/integrations`, { method: "POST", json: body });
    },
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["integrations", guildId] }); toast.success(t("settings.saved")); onClose(); },
    onError: (e) => {
      const code = e instanceof ApiError ? e.fields?.source : undefined;
      if (code) setSourceErr(t.has(`integrations.err_${code}`) ? t(`integrations.err_${code}`) : code);
      else toast.error(errorText(e, t("states.errorBody")));
    },
  });
  const extraValues = { title: t("integrations.sampleTitle"), url: "https://example.com", author: i.display_name ?? "Autor", name: i.display_name ?? t(`integrations.p_${i.provider}`), thumbnail: "" };

  return (
    <Dialog.Root open onOpenChange={(o) => !o && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/60" />
        <Dialog.Content className="fixed inset-y-0 right-0 z-50 flex w-[min(1000px,100vw)] flex-col border-l border-border bg-sidebar">
          <div className="flex items-center justify-between border-b border-border px-6 py-4">
            <Dialog.Title className="text-lg font-semibold">{t(`integrations.p_${i.provider}`)}</Dialog.Title>
            <Dialog.Close className="grid size-9 place-items-center rounded-lg text-muted hover:bg-panel-hover" aria-label={t("common.close")}><X className="size-5" /></Dialog.Close>
          </div>
          <div className="grid flex-1 gap-6 overflow-y-auto p-6 lg:grid-cols-[minmax(0,1fr)_380px]">
            <div className="space-y-4">
              <Field id="in-source" label={t(`integrations.source_${i.provider}`)} help={t(`integrations.sourceHelp_${i.provider}`)} error={sourceErr ?? undefined}>
                <input id="in-source" className={cn(inputClass, "font-mono text-[13px]")} value={i.source ?? ""} maxLength={500} onChange={(e) => { setSourceErr(null); set({ source: e.target.value }); }} />
              </Field>
              <Field id="in-channel" label={t("welcome.channel")}><ChannelSelect id="in-channel" guildId={guildId} value={i.channel_id} onChange={(v) => set({ channel_id: v })} needEmbed /></Field>
              <label className="flex items-center gap-3 text-sm"><Switch checked={i.enabled} label={t("common.enabled")} onCheckedChange={(v) => set({ enabled: v })} />{t("common.enabled")}</label>
              <p className="text-[12px] text-muted">{t("integrations.varsHelp")}</p>
              <MessageEditor idPrefix="in" value={i.message} onChange={(m) => set({ message: m })} defaultColor={color} extraVariables={EXTRA_VARS} />
            </div>
            <div className="space-y-3 lg:sticky lg:top-0">
              <h3 className="text-sm font-semibold">{t("editor.preview")}</h3>
              <DiscordPreview template={i.message} sample={sample} color={color} extraValues={extraValues} />
            </div>
          </div>
          <div className="flex justify-end gap-2 border-t border-border px-6 py-4">
            <Button variant="secondary" onClick={onClose}>{t("common.cancel")}</Button>
            <Button loading={save.isPending} disabled={!i.source?.trim() || !i.channel_id} onClick={() => save.mutate()}>{t("common.save")}</Button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
