"use client";

import * as Dialog from "@radix-ui/react-dialog";
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Gavel, Plus, Search, Shield, Trash2, X } from "lucide-react";
import { useFormatter, useTranslations } from "next-intl";
import { useState } from "react";
import { toast } from "sonner";

import { ChannelSelect } from "@/components/channel-select";
import { DurationInput, useFormatDuration } from "@/components/duration-input";
import { ModulePage } from "@/components/module-page";
import { Badge, Button, Card, CardHeader, EmptyState, Field, inputClass, Skeleton, Switch } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { useGuildId } from "@/lib/hooks";
import { useModuleConfig } from "@/lib/use-module";
import { cn } from "@/lib/utils";

type Step = { warns: number; action: "timeout" | "kick" | "ban"; duration_seconds: number | null };
type ModCfg = {
  log_channel_id: string | null;
  dm_on_action: boolean;
  require_reason: boolean;
  default_reasons: string[];
  warn_expiry_days: number | null;
  escalation: Step[];
  ban_delete_message_days: number;
};
export type Case = {
  id: string;
  number: number;
  target: { id: string; name: string };
  moderator: { id: string; name: string | null } | null;
  action: string;
  reason: string | null;
  duration_seconds: number | null;
  expires_at: string | null;
  active: boolean;
  source: string;
  created_at: string;
};

const TONE: Record<string, "warning" | "danger" | "success" | "neutral" | "primary"> = {
  warn: "warning", timeout: "warning", kick: "danger", ban: "danger", softban: "danger", unban: "success", untimeout: "success", note: "neutral",
};

export default function ModerationPage() {
  const t = useTranslations();
  const guildId = useGuildId();
  const [tab, setTab] = useState<"settings" | "cases">("cases");
  const ctl = useModuleConfig<ModCfg>(guildId, "moderation");
  const form = ctl.form;
  const set = (p: Partial<ModCfg>) => form && ctl.setForm({ ...form, ...p });
  const fmt = useFormatDuration();
  const [newReason, setNewReason] = useState("");

  const dupWarns = form ? new Set(form.escalation.map((s) => s.warns)).size !== form.escalation.length : false;

  return (
    <ModulePage ctl={ctl as never} title={t("nav.items.moderation")} description={t("moderation.description")} errorCount={dupWarns ? 1 : 0}>
      <div role="tablist" className="mb-4 inline-flex rounded-xl border border-border bg-panel p-1">
        {(["cases", "settings"] as const).map((k) => (
          <button key={k} role="tab" aria-selected={tab === k} onClick={() => setTab(k)} className={cn("min-h-9 rounded-lg px-4 text-sm font-medium", tab === k ? "bg-primary-solid text-white" : "text-muted hover:text-text")}>
            {t(`moderation.tab_${k}`)}
          </button>
        ))}
      </div>

      {tab === "cases" ? (
        <CasesTable guildId={guildId} canEdit={ctl.canEdit} />
      ) : (
        form && (
          <div className="grid gap-6 lg:grid-cols-2">
            <Card>
              <CardHeader icon={Shield} title={t("moderation.general")} />
              <fieldset disabled={!ctl.canEdit} className="space-y-4 p-5">
                <Field id="mod-log" label={t("moderation.logChannel")} help={t("moderation.logChannelHelp")}>
                  <ChannelSelect id="mod-log" guildId={guildId} value={form.log_channel_id} onChange={(v) => set({ log_channel_id: v })} needEmbed />
                </Field>
                <ToggleRow label={t("moderation.dmOnAction")} help={t("moderation.dmOnActionHelp")} checked={form.dm_on_action} onChange={(v) => set({ dm_on_action: v })} />
                <ToggleRow label={t("moderation.requireReason")} help={t("moderation.requireReasonHelp")} checked={form.require_reason} onChange={(v) => set({ require_reason: v })} />
                <Field id="mod-expiry" label={t("moderation.warnExpiry")} help={t("moderation.warnExpiryHelp")}>
                  <select id="mod-expiry" className={inputClass} value={form.warn_expiry_days ?? ""} onChange={(e) => set({ warn_expiry_days: e.target.value ? Number(e.target.value) : null })}>
                    <option value="">{t("moderation.never")}</option>
                    {[7, 14, 30, 60, 90, 180, 365].map((d) => (
                      <option key={d} value={d}>
                        {t("duration.nDays", { n: d })}
                      </option>
                    ))}
                  </select>
                </Field>
                <Field id="mod-ban-days" label={t("moderation.banDeleteDays")}>
                  <select id="mod-ban-days" className={inputClass} value={form.ban_delete_message_days} onChange={(e) => set({ ban_delete_message_days: Number(e.target.value) })}>
                    {[0, 1, 2, 3, 4, 5, 6, 7].map((d) => (
                      <option key={d} value={d}>
                        {d === 0 ? t("moderation.dontDelete") : t("duration.nDays", { n: d })}
                      </option>
                    ))}
                  </select>
                </Field>
              </fieldset>
            </Card>

            <div className="space-y-6">
              <Card>
                <CardHeader icon={Gavel} title={t("moderation.escalation")} description={t("moderation.escalationHelp")} />
                <fieldset disabled={!ctl.canEdit} className="space-y-3 p-5">
                  {form.escalation.map((s, i) => (
                    <div key={i} className="flex flex-wrap items-center gap-2 rounded-lg border border-border p-3">
                      <span className="text-sm text-muted">{t("moderation.at")}</span>
                      <input type="number" min={1} max={50} aria-label={t("moderation.warnsCount")} className={cn(inputClass, "w-20")} value={s.warns} aria-invalid={dupWarns}
                        onChange={(e) => set({ escalation: form.escalation.map((x, j) => (j === i ? { ...x, warns: Number(e.target.value) || 1 } : x)) })} />
                      <span className="text-sm text-muted">{t("moderation.warnsArrow")}</span>
                      <select aria-label={t("moderation.action")} className={cn(inputClass, "w-36")} value={s.action}
                        onChange={(e) => set({ escalation: form.escalation.map((x, j) => (j === i ? { ...x, action: e.target.value as Step["action"], duration_seconds: e.target.value === "timeout" ? x.duration_seconds ?? 3600 : null } : x)) })}>
                        {(["timeout", "kick", "ban"] as const).map((a) => (
                          <option key={a} value={a}>
                            {t(`moderation.action_${a}`)}
                          </option>
                        ))}
                      </select>
                      {s.action === "timeout" && (
                        <DurationInput id={`esc-${i}`} value={s.duration_seconds} onChange={(v) => set({ escalation: form.escalation.map((x, j) => (j === i ? { ...x, duration_seconds: v } : x)) })} />
                      )}
                      <button type="button" className="ml-auto grid size-8 place-items-center rounded-md text-muted hover:text-danger" aria-label={t("moderation.removeStep")}
                        onClick={() => set({ escalation: form.escalation.filter((_, j) => j !== i) })}>
                        <Trash2 className="size-4" />
                      </button>
                    </div>
                  ))}
                  {dupWarns && <p className="text-[13px] text-danger">{t("moderation.duplicateWarns")}</p>}
                  {form.escalation.length < 10 && (
                    <Button type="button" variant="secondary" size="sm"
                      onClick={() => set({ escalation: [...form.escalation, { warns: (form.escalation.at(-1)?.warns ?? 0) + 1, action: "timeout", duration_seconds: 3600 }] })}>
                      <Plus className="size-4" aria-hidden /> {t("moderation.addStep")}
                    </Button>
                  )}
                </fieldset>
              </Card>

              <Card>
                <CardHeader title={t("moderation.reasons")} description={t("moderation.reasonsHelp")} />
                <fieldset disabled={!ctl.canEdit} className="space-y-3 p-5">
                  <div className="flex flex-wrap gap-2">
                    {form.default_reasons.map((r, i) => (
                      <span key={i} className="inline-flex items-center gap-1.5 rounded-lg bg-input px-2.5 py-1 text-[13px]">
                        {r}
                        <button type="button" aria-label={`${t("common.close")} ${r}`} onClick={() => set({ default_reasons: form.default_reasons.filter((_, j) => j !== i) })} className="text-muted hover:text-danger">
                          <X className="size-3" />
                        </button>
                      </span>
                    ))}
                  </div>
                  <form className="flex gap-2" onSubmit={(e) => {
                    e.preventDefault();
                    if (newReason.trim()) {
                      set({ default_reasons: [...form.default_reasons, newReason.trim()] });
                      setNewReason("");
                    }
                  }}>
                    <input className={inputClass} value={newReason} maxLength={200} onChange={(e) => setNewReason(e.target.value)} placeholder={t("moderation.newReason")} aria-label={t("moderation.newReason")} />
                    <Button type="submit" variant="secondary">
                      <Plus className="size-4" aria-hidden />
                    </Button>
                  </form>
                </fieldset>
              </Card>
              <p className="text-[12px] text-muted">{t("moderation.commandsHelp", { example: fmt(3600) })}</p>
            </div>
          </div>
        )
      )}
    </ModulePage>
  );
}

function ToggleRow({ label, help, checked, onChange }: { label: string; help?: string; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <label className="flex items-center justify-between gap-4">
      <span>
        <span className="block text-sm font-medium">{label}</span>
        {help && <span className="text-[13px] text-muted">{help}</span>}
      </span>
      <Switch checked={checked} label={label} onCheckedChange={onChange} />
    </label>
  );
}

type Page = { data: Case[]; next_cursor: number | null };

function CasesTable({ guildId, canEdit }: { guildId: string; canEdit: boolean }) {
  const t = useTranslations();
  const format = useFormatter();
  const fmt = useFormatDuration();
  const [q, setQ] = useState("");
  const [action, setAction] = useState("");
  const [open, setOpen] = useState<number | null>(null);
  const params = new URLSearchParams();
  if (q.trim()) params.set("target", q.trim());
  if (action) params.set("action", action);
  const query = useInfiniteQuery({
    queryKey: ["cases", guildId, q.trim(), action],
    queryFn: ({ pageParam }) => api<Page>(`/guilds/${guildId}/moderation/cases?${params}${pageParam ? `&cursor=${pageParam}` : ""}`),
    initialPageParam: null as number | null,
    getNextPageParam: (l) => l.next_cursor,
  });
  const rows = query.data?.pages.flatMap((p) => p.data) ?? [];

  return (
    <Card className="overflow-hidden">
      <div className="flex flex-wrap gap-2 border-b border-border p-4">
        <label className="relative min-w-56 flex-1">
          <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted" aria-hidden />
          <input className={cn(inputClass, "pl-9")} value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("moderation.searchUser")} aria-label={t("moderation.searchUser")} />
        </label>
        <select className={cn(inputClass, "w-48")} value={action} onChange={(e) => setAction(e.target.value)} aria-label={t("moderation.action")}>
          <option value="">{t("moderation.allActions")}</option>
          {["warn", "timeout", "kick", "ban", "unban"].map((a) => (
            <option key={a} value={a}>
              {t(`moderation.action_${a}`)}
            </option>
          ))}
        </select>
      </div>
      {query.isPending ? (
        <Skeleton className="m-4 h-64" />
      ) : rows.length === 0 ? (
        <EmptyState icon={Gavel} title={t("moderation.noCases")} body={t("moderation.noCasesBody")} />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[720px] text-left text-sm">
            <thead className="border-b border-border text-[12px] uppercase tracking-wider text-muted">
              <tr>
                <th className="px-4 py-3 font-semibold">#</th>
                <th className="px-4 py-3 font-semibold">{t("moderation.action")}</th>
                <th className="px-4 py-3 font-semibold">{t("moderation.user")}</th>
                <th className="px-4 py-3 font-semibold">{t("moderation.reason")}</th>
                <th className="px-4 py-3 font-semibold">{t("moderation.moderator")}</th>
                <th className="px-4 py-3 font-semibold">{t("audit.date")}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {rows.map((c) => (
                <tr key={c.id} className={cn("cursor-pointer hover:bg-panel-hover/50", !c.active && c.action === "warn" && "opacity-50")} onClick={() => setOpen(c.number)}>
                  <td className="px-4 py-3 font-mono text-muted">{c.number}</td>
                  <td className="px-4 py-3">
                    <Badge tone={TONE[c.action] ?? "neutral"}>{t(`moderation.action_${c.action}`)}</Badge>
                    {c.duration_seconds ? <span className="ml-2 text-[12px] text-muted">{fmt(c.duration_seconds)}</span> : null}
                  </td>
                  <td className="px-4 py-3">{c.target.name}</td>
                  <td className="max-w-xs truncate px-4 py-3 text-muted">{c.reason ?? "—"}</td>
                  <td className="px-4 py-3 text-muted">{c.source === "manual" ? c.moderator?.name : t(`moderation.source_${c.source}`)}</td>
                  <td className="whitespace-nowrap px-4 py-3 text-muted">{format.dateTime(new Date(c.created_at), { dateStyle: "medium", timeStyle: "short" })}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {query.hasNextPage && (
        <div className="border-t border-border p-3 text-center">
          <Button variant="secondary" onClick={() => query.fetchNextPage()} loading={query.isFetchingNextPage}>
            {t("audit.loadMore")}
          </Button>
        </div>
      )}
      <CaseDrawer guildId={guildId} number={open} onClose={() => setOpen(null)} canEdit={canEdit} />
    </Card>
  );
}

function CaseDrawer({ guildId, number, onClose, canEdit }: { guildId: string; number: number | null; onClose: () => void; canEdit: boolean }) {
  const t = useTranslations();
  const format = useFormatter();
  const fmt = useFormatDuration();
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: ["case", guildId, number],
    queryFn: () => api<{ data: Case; history: Case[] }>(`/guilds/${guildId}/moderation/cases/${number}`),
    enabled: number !== null,
  });
  const [reason, setReason] = useState<string | null>(null);
  const patch = useMutation({
    mutationFn: (body: { reason?: string; active?: boolean }) => api(`/guilds/${guildId}/moderation/cases/${number}`, { method: "PATCH", json: body }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["cases", guildId] });
      qc.invalidateQueries({ queryKey: ["case", guildId, number] });
      setReason(null);
      toast.success(t("settings.saved"));
    },
    onError: (e) => toast.error(e instanceof ApiError ? e.message : t("states.errorBody")),
  });
  const c = q.data?.data;
  return (
    <Dialog.Root open={number !== null} onOpenChange={(o) => !o && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/60" />
        <Dialog.Content className="fixed inset-y-0 right-0 z-50 w-[min(520px,100vw)] overflow-y-auto border-l border-border bg-sidebar p-6">
          <div className="mb-5 flex items-center justify-between">
            <Dialog.Title className="text-lg font-semibold">{t("moderation.caseTitle", { number: number ?? 0 })}</Dialog.Title>
            <Dialog.Close className="grid size-9 place-items-center rounded-lg text-muted hover:bg-panel-hover" aria-label={t("common.close")}>
              <X className="size-5" />
            </Dialog.Close>
          </div>
          {!c ? (
            <Skeleton className="h-64" />
          ) : (
            <div className="space-y-5">
              <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-sm">
                <dt className="text-muted">{t("moderation.action")}</dt>
                <dd><Badge tone={TONE[c.action] ?? "neutral"}>{t(`moderation.action_${c.action}`)}</Badge>{!c.active && <span className="ml-2 text-[12px] text-muted">{t("moderation.inactive")}</span>}</dd>
                <dt className="text-muted">{t("moderation.user")}</dt>
                <dd>{c.target.name} <span className="font-mono text-[12px] text-muted">{c.target.id}</span></dd>
                <dt className="text-muted">{t("moderation.moderator")}</dt>
                <dd>{c.moderator?.name ?? t(`moderation.source_${c.source}`)}</dd>
                {c.duration_seconds ? (<><dt className="text-muted">{t("duration.label")}</dt><dd>{fmt(c.duration_seconds)}</dd></>) : null}
                <dt className="text-muted">{t("audit.date")}</dt>
                <dd>{format.dateTime(new Date(c.created_at), { dateStyle: "long", timeStyle: "short" })}</dd>
                {c.expires_at && (<><dt className="text-muted">{t("moderation.expires")}</dt><dd>{format.dateTime(new Date(c.expires_at), { dateStyle: "medium", timeStyle: "short" })}</dd></>)}
              </dl>
              <Field id="case-reason" label={t("moderation.reason")}>
                <textarea id="case-reason" rows={3} disabled={!canEdit} className={cn(inputClass, "py-2")} value={reason ?? c.reason ?? ""} onChange={(e) => setReason(e.target.value)} maxLength={1000} />
              </Field>
              {canEdit && (
                <div className="flex flex-wrap gap-2">
                  <Button disabled={reason === null} loading={patch.isPending} onClick={() => patch.mutate({ reason: reason ?? "" })}>{t("common.save")}</Button>
                  {(c.action === "warn" || c.action === "note") && (
                    <Button variant="secondary" onClick={() => patch.mutate({ active: !c.active })}>{c.active ? t("moderation.pardon") : t("moderation.reactivate")}</Button>
                  )}
                </div>
              )}
              <div>
                <h3 className="mb-2 text-sm font-semibold">{t("moderation.userHistory")}</h3>
                <ul className="divide-y divide-border rounded-lg border border-border">
                  {q.data!.history.map((h) => (
                    <li key={h.id} className="flex items-center gap-3 px-3 py-2 text-[13px]">
                      <span className="font-mono text-muted">#{h.number}</span>
                      <Badge tone={TONE[h.action] ?? "neutral"}>{t(`moderation.action_${h.action}`)}</Badge>
                      <span className="flex-1 truncate text-muted">{h.reason ?? "—"}</span>
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          )}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
