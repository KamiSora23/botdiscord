"use client";

import * as Dialog from "@radix-ui/react-dialog";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ExternalLink, Pencil, Plus, Send, Tags, Trash2, X } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { toast } from "sonner";

import { ChannelSelect, useChannels } from "@/components/channel-select";
import { DiscordPreview } from "@/components/discord-preview";
import { MessageEditor } from "@/components/message-editor";
import { ModulePage } from "@/components/module-page";
import { RoleSelect, useRoles } from "@/components/multi-select";
import { ConfirmDialog } from "@/components/save-bar";
import { Badge, Button, Card, CardHeader, EmptyState, Field, inputClass, Skeleton } from "@/components/ui";
import { api, errorText } from "@/lib/api";
import { useGuildId } from "@/lib/hooks";
import { clean, type MessageTemplate } from "@/lib/messages";
import { useModuleConfig } from "@/lib/use-module";
import { useSample } from "@/lib/use-sample";
import { cn } from "@/lib/utils";

type Opt = { id?: string; role_id: string; label: string; emoji: string | null; description: string | null; style: "primary" | "secondary" | "success" | "danger" };
type Panel = {
  id?: string;
  name: string;
  channel_id: string | null;
  message_id?: string | null;
  panel_type: "buttons" | "select" | "reactions";
  mode: "normal" | "unique" | "verify" | "drop";
  message: MessageTemplate;
  max_choices: number | null;
  placeholder: string | null;
  options: Opt[];
  version?: number;
  published_at?: string | null;
  outdated?: boolean;
  jump_url?: string | null;
};

const STYLE_CLS: Record<Opt["style"], string> = {
  primary: "bg-[#5865f2] text-white",
  secondary: "bg-[#4e5058] text-white",
  success: "bg-[#248046] text-white",
  danger: "bg-[#da373c] text-white",
};

export default function ReactionRolesPage() {
  const t = useTranslations();
  const guildId = useGuildId();
  const qc = useQueryClient();
  const ctl = useModuleConfig<{ remove_reaction_after: boolean }>(guildId, "reaction_roles");
  const panels = useQuery({ queryKey: ["role-panels", guildId], queryFn: () => api<{ data: Panel[]; can_edit: boolean }>(`/guilds/${guildId}/role-panels`) });
  const [editing, setEditing] = useState<Panel | null>(null);
  const [deleting, setDeleting] = useState<Panel | null>(null);

  const publish = useMutation({
    mutationFn: (p: Panel) => api(`/guilds/${guildId}/role-panels/${p.id}/publish`, { method: "POST" }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["role-panels", guildId] });
      toast.success(t("rr.published"));
    },
    onError: (e) => toast.error(errorText(e, t("states.errorBody"))),
  });
  const remove = useMutation({
    mutationFn: (p: Panel) => api(`/guilds/${guildId}/role-panels/${p.id}`, { method: "DELETE" }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["role-panels", guildId] });
      setDeleting(null);
    },
  });

  return (
    <ModulePage ctl={ctl as never} title={t("nav.items.reaction_roles")} description={t("rr.description")}>
      <Card>
        <CardHeader
          icon={Tags}
          title={t("rr.panels")}
          action={
            panels.data?.can_edit && (
              <Button size="sm" onClick={() => setEditing(newPanel(t("rr.defaultName"), t("rr.defaultMessage")))}>
                <Plus className="size-4" aria-hidden /> {t("rr.newPanel")}
              </Button>
            )
          }
        />
        {panels.isPending ? (
          <Skeleton className="m-5 h-32" />
        ) : !panels.data?.data.length ? (
          <EmptyState icon={Tags} title={t("rr.empty")} body={t("rr.emptyBody")} />
        ) : (
          <ul className="divide-y divide-border">
            {panels.data.data.map((p) => (
              <li key={p.id} className="flex flex-wrap items-center gap-3 px-5 py-3">
                <div className="min-w-0 flex-1">
                  <p className="flex flex-wrap items-center gap-2 font-medium">
                    {p.name}
                    {p.published_at ? (p.outdated ? <Badge tone="warning">{t("rr.outdated")}</Badge> : <Badge tone="success">{t("rr.published")}</Badge>) : <Badge>{t("rr.draft")}</Badge>}
                  </p>
                  <p className="text-[12px] text-muted">
                    {t(`rr.type_${p.panel_type}`)} · {t(`rr.mode_${p.mode}`)} · {t("rr.optionsCount", { count: p.options.length })}
                  </p>
                </div>
                {p.jump_url && (
                  <a href={p.jump_url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-[13px] text-primary-text hover:underline">
                    Discord <ExternalLink className="size-3.5" aria-hidden />
                  </a>
                )}
                {panels.data.can_edit && (
                  <>
                    <Button size="sm" variant="secondary" loading={publish.isPending && publish.variables?.id === p.id} onClick={() => publish.mutate(p)}>
                      <Send className="size-4" aria-hidden /> {p.message_id ? t("rr.update") : t("rr.publish")}
                    </Button>
                    <Button variant="ghost" size="sm" onClick={() => setEditing(p)} aria-label={t("automod.edit")}><Pencil className="size-4" /></Button>
                    <Button variant="ghost" size="sm" onClick={() => setDeleting(p)} aria-label={t("automod.delete")}><Trash2 className="size-4" /></Button>
                  </>
                )}
              </li>
            ))}
          </ul>
        )}
      </Card>
      {editing && <PanelEditor guildId={guildId} panel={editing} onClose={() => setEditing(null)} />}
      <ConfirmDialog
        open={deleting !== null}
        title={t("automod.deleteTitle", { name: deleting?.name ?? "" })}
        body={t("rr.deleteBody")}
        confirmLabel={t("automod.delete")}
        destructive
        onCancel={() => setDeleting(null)}
        onConfirm={() => deleting && remove.mutate(deleting)}
      />
    </ModulePage>
  );
}

function newPanel(name: string, text: string): Panel {
  return {
    name, channel_id: null, panel_type: "buttons", mode: "normal", max_choices: null, placeholder: null,
    message: { content: null, embeds: [{ title: name, description: text, url: null, color: null, author: { name: null, icon_url: null, url: null }, thumbnail_url: null, image_url: null, footer: { text: null, icon_url: null }, timestamp: false, fields: [] }] },
    options: [],
  };
}

function strip(p: Panel) {
  return { name: p.name, channel_id: p.channel_id, panel_type: p.panel_type, mode: p.mode, message: clean(p.message), max_choices: p.max_choices, placeholder: p.placeholder, options: p.options.map((o) => ({ ...o, emoji: o.emoji || null, description: o.description || null })) };
}

function PanelEditor({ guildId, panel, onClose }: { guildId: string; panel: Panel; onClose: () => void }) {
  const t = useTranslations();
  const qc = useQueryClient();
  const [p, setP] = useState<Panel>(panel);
  const [newRole, setNewRole] = useState<string | null>(null);
  const { data: roles } = useRoles(guildId);
  const { data: channels } = useChannels(guildId);
  const { sample, color } = useSample(guildId, channels?.find((c) => c.id === p.channel_id)?.name ?? null);
  const set = (x: Partial<Panel>) => setP({ ...p, ...x });
  const setOpt = (i: number, x: Partial<Opt>) => set({ options: p.options.map((o, j) => (j === i ? { ...o, ...x } : o)) });
  const roleName = (id: string) => roles?.find((r) => r.id === id)?.name ?? id;
  const tooHigh = p.options.filter((o) => roles?.find((r) => r.id === o.role_id && !r.bot_can_assign));

  const save = useMutation({
    mutationFn: () =>
      p.id
        ? api(`/guilds/${guildId}/role-panels/${p.id}`, { method: "PUT", json: { ...strip(p), version: p.version } })
        : api(`/guilds/${guildId}/role-panels`, { method: "POST", json: strip(p) }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["role-panels", guildId] });
      toast.success(t("settings.saved"));
      onClose();
    },
    onError: (e) => toast.error(errorText(e, t("states.errorBody"))),
  });

  return (
    <Dialog.Root open onOpenChange={(o) => !o && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/60" />
        <Dialog.Content className="fixed inset-y-0 right-0 z-50 flex w-[min(1100px,100vw)] flex-col border-l border-border bg-sidebar">
          <div className="flex items-center justify-between border-b border-border px-6 py-4">
            <Dialog.Title className="text-lg font-semibold">{p.id ? t("rr.editPanel") : t("rr.newPanel")}</Dialog.Title>
            <Dialog.Close className="grid size-9 place-items-center rounded-lg text-muted hover:bg-panel-hover" aria-label={t("common.close")}><X className="size-5" /></Dialog.Close>
          </div>
          <div className="grid flex-1 gap-6 overflow-y-auto p-6 lg:grid-cols-[minmax(0,1fr)_400px]">
            <div className="space-y-5">
              <div className="grid gap-4 sm:grid-cols-2">
                <Field id="rp-name" label={t("automod.name")}>
                  <input id="rp-name" className={inputClass} value={p.name} maxLength={80} onChange={(e) => set({ name: e.target.value })} />
                </Field>
                <Field id="rp-channel" label={t("welcome.channel")} help={p.message_id ? t("rr.channelLocked") : undefined}>
                  <ChannelSelect id="rp-channel" guildId={guildId} value={p.channel_id} onChange={(v) => set({ channel_id: v })} disabled={Boolean(p.message_id)} needEmbed />
                </Field>
                <Field id="rp-type" label={t("rr.type")}>
                  <select id="rp-type" className={inputClass} value={p.panel_type} onChange={(e) => set({ panel_type: e.target.value as Panel["panel_type"] })} disabled={Boolean(p.message_id)}>
                    {(["buttons", "select", "reactions"] as const).map((x) => <option key={x} value={x}>{t(`rr.type_${x}`)}</option>)}
                  </select>
                </Field>
                <Field id="rp-mode" label={t("rr.mode")} help={t(`rr.modeHelp_${p.mode}`)}>
                  <select id="rp-mode" className={inputClass} value={p.mode} onChange={(e) => set({ mode: e.target.value as Panel["mode"] })}>
                    {(["normal", "unique", "verify", "drop"] as const).map((x) => <option key={x} value={x}>{t(`rr.mode_${x}`)}</option>)}
                  </select>
                </Field>
                {p.panel_type === "select" && (
                  <>
                    <Field id="rp-placeholder" label={t("rr.placeholder")}>
                      <input id="rp-placeholder" className={inputClass} value={p.placeholder ?? ""} maxLength={150} onChange={(e) => set({ placeholder: e.target.value || null })} />
                    </Field>
                    <Field id="rp-max" label={t("rr.maxChoices")}>
                      <input id="rp-max" type="number" min={1} max={25} className={inputClass} value={p.max_choices ?? ""} onChange={(e) => set({ max_choices: e.target.value ? Number(e.target.value) : null })} />
                    </Field>
                  </>
                )}
              </div>

              <fieldset className="space-y-3">
                <legend className="mb-1 text-sm font-semibold">{t("rr.options")}</legend>
                {tooHigh.length > 0 && <p className="text-[13px] text-warning">{t("autoroles.hierarchy", { roles: tooHigh.map((o) => roleName(o.role_id)).join(", ") })}</p>}
                {p.options.map((o, i) => (
                  <div key={o.id ?? i} className="grid gap-2 rounded-lg border border-border p-3 sm:grid-cols-[1fr_1fr_90px_auto]">
                    <span className="text-[13px] font-medium sm:col-span-4">@{roleName(o.role_id)}</span>
                    <input aria-label={t("rr.label")} placeholder={t("rr.label")} className={inputClass} value={o.label} maxLength={80} onChange={(e) => setOpt(i, { label: e.target.value })} />
                    <input aria-label={t("rr.descriptionField")} placeholder={t("rr.descriptionField")} className={inputClass} value={o.description ?? ""} maxLength={100} onChange={(e) => setOpt(i, { description: e.target.value })} disabled={p.panel_type !== "select"} />
                    <input aria-label="Emoji" placeholder="🎮" className={cn(inputClass, "text-center")} value={o.emoji ?? ""} maxLength={64} onChange={(e) => setOpt(i, { emoji: e.target.value })} />
                    <div className="flex gap-1">
                      {p.panel_type === "buttons" && (
                        <select aria-label={t("rr.style")} className={cn(inputClass, "w-28")} value={o.style} onChange={(e) => setOpt(i, { style: e.target.value as Opt["style"] })}>
                          {(["primary", "secondary", "success", "danger"] as const).map((s) => <option key={s} value={s}>{t(`rr.style_${s}`)}</option>)}
                        </select>
                      )}
                      <button type="button" className="grid size-10 place-items-center rounded-md text-muted hover:text-danger" aria-label={t("automod.delete")} onClick={() => set({ options: p.options.filter((_, j) => j !== i) })}>
                        <Trash2 className="size-4" />
                      </button>
                    </div>
                  </div>
                ))}
                {p.options.length < 25 && (
                  <div className="flex gap-2">
                    <RoleSelect id="rp-new-role" guildId={guildId} value={newRole} onChange={setNewRole} />
                    <Button type="button" variant="secondary" disabled={!newRole || p.options.some((o) => o.role_id === newRole)}
                      onClick={() => { if (newRole) { set({ options: [...p.options, { role_id: newRole, label: roleName(newRole), emoji: null, description: null, style: "secondary" }] }); setNewRole(null); } }}>
                      <Plus className="size-4" aria-hidden /> {t("rr.addOption")}
                    </Button>
                  </div>
                )}
              </fieldset>

              <div>
                <h3 className="mb-3 text-sm font-semibold">{t("welcome.message")}</h3>
                <MessageEditor idPrefix="rp" value={p.message} onChange={(m) => set({ message: m })} defaultColor={color} />
              </div>
            </div>

            <div className="space-y-3 lg:sticky lg:top-0">
              <h3 className="text-sm font-semibold">{t("editor.preview")}</h3>
              <DiscordPreview template={p.message} sample={sample} color={color} />
              <div className="rounded-xl bg-[#313338] p-4 pt-0">
                {p.panel_type === "buttons" && (
                  <div className="flex flex-wrap gap-2 pl-14">
                    {p.options.map((o, i) => <span key={i} className={cn("inline-flex h-8 items-center gap-1.5 rounded px-4 text-sm font-medium", STYLE_CLS[o.style])}>{o.emoji}{o.label}</span>)}
                  </div>
                )}
                {p.panel_type === "select" && (
                  <div className="ml-14 flex h-10 items-center justify-between rounded border border-[#1e1f22] bg-[#2b2d31] px-3 text-sm text-[#949ba4]">
                    {p.placeholder || t("rr.selectDefault")}
                    <span aria-hidden>⌄</span>
                  </div>
                )}
                {p.panel_type === "reactions" && (
                  <div className="flex flex-wrap gap-1.5 pl-14">
                    {p.options.map((o, i) => <span key={i} className="inline-flex h-7 items-center gap-1 rounded-lg border border-[#5865f2]/50 bg-[#5865f2]/15 px-2 text-sm">{o.emoji ?? "?"}<span className="text-[12px] text-[#dbdee1]">1</span></span>)}
                  </div>
                )}
              </div>
            </div>
          </div>
          <div className="flex justify-end gap-2 border-t border-border px-6 py-4">
            <Button variant="secondary" onClick={onClose}>{t("common.cancel")}</Button>
            <Button loading={save.isPending} disabled={!p.name.trim() || p.options.length === 0} onClick={() => save.mutate()}>{t("common.save")}</Button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
