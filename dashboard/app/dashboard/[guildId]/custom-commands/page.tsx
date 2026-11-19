"use client";

import * as Dialog from "@radix-ui/react-dialog";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Pencil, Plus, Terminal, Trash2, X } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { toast } from "sonner";

import { DiscordPreview } from "@/components/discord-preview";
import { MessageEditor } from "@/components/message-editor";
import { RoleMultiSelect } from "@/components/multi-select";
import { ConfirmDialog } from "@/components/save-bar";
import { Badge, Button, Card, CardHeader, EmptyState, ErrorState, Field, inputClass, PageHeader, Skeleton, Switch } from "@/components/ui";
import { api, ApiError, errorText } from "@/lib/api";
import { useGuildId } from "@/lib/hooks";
import { clean, type MessageTemplate } from "@/lib/messages";
import { useSample } from "@/lib/use-sample";
import { cn } from "@/lib/utils";

type Cmd = {
  id?: string; name: string; description: string; enabled: boolean; response: MessageTemplate; ephemeral: boolean;
  add_role_ids: string[]; remove_role_ids: string[]; allowed_role_ids: string[]; uses?: number; version?: number;
};

export default function CustomCommandsPage() {
  const t = useTranslations();
  const guildId = useGuildId();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["commands", guildId], queryFn: () => api<{ data: Cmd[]; can_edit: boolean; max: number }>(`/guilds/${guildId}/custom-commands`) });
  const [editing, setEditing] = useState<Cmd | null>(null);
  const [deleting, setDeleting] = useState<Cmd | null>(null);
  const remove = useMutation({
    mutationFn: (c: Cmd) => api(`/guilds/${guildId}/custom-commands/${c.id}`, { method: "DELETE" }),
    onSuccess: () => { setDeleting(null); qc.invalidateQueries({ queryKey: ["commands", guildId] }); },
  });

  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  return (
    <div className="space-y-6">
      <PageHeader title={t("nav.items.custom_commands")} description={t("commands.description")} />
      <Card>
        <CardHeader icon={Terminal} title={t("commands.list", { count: q.data?.data.length ?? 0, max: q.data?.max ?? 50 })} action={
          q.data?.can_edit && <Button size="sm" onClick={() => setEditing({ name: "", description: "", enabled: true, response: { content: "", embeds: [] }, ephemeral: false, add_role_ids: [], remove_role_ids: [], allowed_role_ids: [] })}>
            <Plus className="size-4" aria-hidden /> {t("commands.new")}
          </Button>
        } />
        {q.isPending ? <Skeleton className="m-5 h-32" /> : !q.data.data.length ? <EmptyState icon={Terminal} title={t("commands.none")} body={t("commands.noneBody")} /> : (
          <ul className="divide-y divide-border">
            {q.data.data.map((c) => (
              <li key={c.id} className="flex flex-wrap items-center gap-3 px-5 py-3">
                <code className="font-mono text-primary-text">/{c.name}</code>
                <span className="min-w-0 flex-1 truncate text-[13px] text-muted">{c.description}</span>
                {!c.enabled && <Badge>{t("common.disabled")}</Badge>}
                <span className="text-[12px] text-muted">{t("commands.uses", { count: c.uses ?? 0 })}</span>
                {q.data.can_edit && (
                  <>
                    <Button variant="ghost" size="sm" onClick={() => setEditing(c)} aria-label={t("automod.edit")}><Pencil className="size-4" /></Button>
                    <Button variant="ghost" size="sm" onClick={() => setDeleting(c)} aria-label={t("automod.delete")}><Trash2 className="size-4" /></Button>
                  </>
                )}
              </li>
            ))}
          </ul>
        )}
      </Card>
      <p className="text-[12px] text-muted">{t("commands.help")}</p>
      {editing && <Editor guildId={guildId} cmd={editing} onClose={() => setEditing(null)} />}
      <ConfirmDialog open={deleting !== null} title={t("automod.deleteTitle", { name: `/${deleting?.name ?? ""}` })} body={t("commands.deleteBody")} confirmLabel={t("automod.delete")} destructive onCancel={() => setDeleting(null)} onConfirm={() => deleting && remove.mutate(deleting)} />
    </div>
  );
}

function Editor({ guildId, cmd, onClose }: { guildId: string; cmd: Cmd; onClose: () => void }) {
  const t = useTranslations();
  const qc = useQueryClient();
  const [c, setC] = useState<Cmd>(cmd);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const { sample, color } = useSample(guildId, null);
  const set = (x: Partial<Cmd>) => setC({ ...c, ...x });
  const body = () => ({ name: c.name, description: c.description, enabled: c.enabled, response: clean(c.response), ephemeral: c.ephemeral, add_role_ids: c.add_role_ids, remove_role_ids: c.remove_role_ids, allowed_role_ids: c.allowed_role_ids });
  const save = useMutation({
    mutationFn: () => (c.id ? api(`/guilds/${guildId}/custom-commands/${c.id}`, { method: "PUT", json: { ...body(), version: c.version } }) : api(`/guilds/${guildId}/custom-commands`, { method: "POST", json: body() })),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["commands", guildId] }); toast.success(t("commands.saved")); onClose(); },
    onError: (e) => { if (e instanceof ApiError && e.fields) setErrors(e.fields); toast.error(errorText(e, t("states.errorBody"))); },
  });
  const nameErr = errors.name ? t.has(`commands.err_${errors.name}`) ? t(`commands.err_${errors.name}`) : errors.name : undefined;

  return (
    <Dialog.Root open onOpenChange={(o) => !o && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/60" />
        <Dialog.Content className="fixed inset-y-0 right-0 z-50 flex w-[min(1000px,100vw)] flex-col border-l border-border bg-sidebar">
          <div className="flex items-center justify-between border-b border-border px-6 py-4">
            <Dialog.Title className="text-lg font-semibold">{c.id ? `/${cmd.name}` : t("commands.new")}</Dialog.Title>
            <Dialog.Close className="grid size-9 place-items-center rounded-lg text-muted hover:bg-panel-hover" aria-label={t("common.close")}><X className="size-5" /></Dialog.Close>
          </div>
          <div className="grid flex-1 gap-6 overflow-y-auto p-6 lg:grid-cols-[minmax(0,1fr)_380px]">
            <div className="space-y-4">
              <div className="grid gap-4 sm:grid-cols-2">
                <Field id="cc-name" label={t("commands.name")} error={nameErr} help={t("commands.nameHelp")}>
                  <div className="flex items-center"><span className="mr-1 font-mono text-muted">/</span><input id="cc-name" className={cn(inputClass, "font-mono")} value={c.name} maxLength={32} onChange={(e) => set({ name: e.target.value.toLowerCase().replace(/[^a-z0-9_-]/g, "") })} /></div>
                </Field>
                <Field id="cc-desc" label={t("editor.description")}><input id="cc-desc" className={inputClass} value={c.description} maxLength={100} onChange={(e) => set({ description: e.target.value })} /></Field>
              </div>
              <div className="flex flex-wrap gap-6">
                <label className="flex items-center gap-3 text-sm"><Switch checked={c.enabled} label={t("common.enabled")} onCheckedChange={(v) => set({ enabled: v })} />{t("common.enabled")}</label>
                <label className="flex items-center gap-3 text-sm"><Switch checked={c.ephemeral} label={t("commands.ephemeral")} onCheckedChange={(v) => set({ ephemeral: v })} />{t("commands.ephemeral")}</label>
              </div>
              <h3 className="text-sm font-semibold">{t("commands.response")}</h3>
              <MessageEditor idPrefix="cc" value={c.response} onChange={(m) => set({ response: m })} defaultColor={color} />
              <h3 className="pt-2 text-sm font-semibold">{t("commands.actions")}</h3>
              <Field id="cc-add" label={t("commands.addRoles")}><RoleMultiSelect id="cc-add" guildId={guildId} value={c.add_role_ids} onChange={(v) => set({ add_role_ids: v.slice(0, 5) })} /></Field>
              <Field id="cc-remove" label={t("commands.removeRoles")}><RoleMultiSelect id="cc-remove" guildId={guildId} value={c.remove_role_ids} onChange={(v) => set({ remove_role_ids: v.slice(0, 5) })} /></Field>
              <Field id="cc-allowed" label={t("commands.allowedRoles")} help={t("commands.allowedHelp")}><RoleMultiSelect id="cc-allowed" guildId={guildId} value={c.allowed_role_ids} onChange={(v) => set({ allowed_role_ids: v })} /></Field>
            </div>
            <div className="space-y-3 lg:sticky lg:top-0">
              <h3 className="text-sm font-semibold">{t("editor.preview")}</h3>
              <DiscordPreview template={c.response} sample={sample} color={color} />
            </div>
          </div>
          <div className="flex justify-end gap-2 border-t border-border px-6 py-4">
            <Button variant="secondary" onClick={onClose}>{t("common.cancel")}</Button>
            <Button loading={save.isPending} disabled={!c.name || !c.description.trim()} onClick={() => save.mutate()}>{t("common.save")}</Button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
