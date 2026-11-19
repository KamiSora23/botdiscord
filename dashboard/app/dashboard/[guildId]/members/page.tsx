"use client";

import * as Dialog from "@radix-ui/react-dialog";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Search, Trash2, Users, X } from "lucide-react";
import { useFormatter, useTranslations } from "next-intl";
import { useDeferredValue, useState } from "react";
import { toast } from "sonner";

import { DurationInput } from "@/components/duration-input";
import { useRoles } from "@/components/multi-select";
import { Avatar, Badge, Button, Card, EmptyState, ErrorState, Field, inputClass, PageHeader, Skeleton } from "@/components/ui";
import { api, errorText } from "@/lib/api";
import { useGuildId } from "@/lib/hooks";
import { cn, colorToHex } from "@/lib/utils";

import type { Case } from "../moderation/page";

type Member = {
  id: string;
  username: string;
  global_name: string | null;
  nick: string | null;
  avatar_url: string;
  bot: boolean;
  roles: string[];
  joined_at: string | null;
  timed_out_until: string | null;
};
type Profile = {
  member: Member | null;
  in_guild: boolean;
  active_warns: number;
  cases: Case[];
  notes: { id: string; author: string; note: string; created_at: string }[];
  can_act: boolean;
};

export default function MembersPage() {
  const t = useTranslations();
  const guildId = useGuildId();
  const [query, setQuery] = useState("");
  const q = useDeferredValue(query.trim());
  const [open, setOpen] = useState<string | null>(null);
  const list = useQuery({
    queryKey: ["members", guildId, q],
    queryFn: () => api<{ data: Member[] }>(`/guilds/${guildId}/members?query=${encodeURIComponent(q)}`).then((r) => r.data),
    staleTime: 15_000,
  });

  return (
    <div className="space-y-6">
      <PageHeader title={t("nav.items.members")} description={t("members.description")} />
      <Card className="overflow-hidden">
        <div className="border-b border-border p-4">
          <label className="relative block">
            <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted" aria-hidden />
            <input className={cn(inputClass, "pl-9")} value={query} onChange={(e) => setQuery(e.target.value)} placeholder={t("members.search")} aria-label={t("members.search")} />
          </label>
        </div>
        {list.isPending ? (
          <Skeleton className="m-4 h-64" />
        ) : list.isError ? (
          <div className="p-4"><ErrorState error={list.error} onRetry={() => list.refetch()} /></div>
        ) : list.data.length === 0 ? (
          <EmptyState icon={Users} title={t("members.none")} />
        ) : (
          <ul className="divide-y divide-border">
            {list.data.map((m) => (
              <li key={m.id}>
                <button type="button" onClick={() => setOpen(m.id)} className="flex w-full items-center gap-3 px-4 py-3 text-left hover:bg-panel-hover/50">
                  <Avatar url={m.avatar_url} size={36} />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate font-medium">{m.nick ?? m.global_name ?? m.username}</span>
                    <span className="block truncate text-[12px] text-muted">@{m.username} · {m.id}</span>
                  </span>
                  {m.bot && <Badge>BOT</Badge>}
                  {m.timed_out_until && new Date(m.timed_out_until) > new Date() && <Badge tone="warning">{t("moderation.action_timeout")}</Badge>}
                </button>
              </li>
            ))}
          </ul>
        )}
      </Card>
      {open && <ProfileDrawer guildId={guildId} userId={open} onClose={() => setOpen(null)} />}
    </div>
  );
}

const ACTIONS = ["warn", "timeout", "untimeout", "kick", "ban", "unban"] as const;

function ProfileDrawer({ guildId, userId, onClose }: { guildId: string; userId: string; onClose: () => void }) {
  const t = useTranslations();
  const format = useFormatter();
  const qc = useQueryClient();
  const { data: roles } = useRoles(guildId);
  const key = ["member", guildId, userId];
  const q = useQuery({ queryKey: key, queryFn: () => api<Profile>(`/guilds/${guildId}/members/${userId}`) });
  const [note, setNote] = useState("");
  const [action, setAction] = useState<(typeof ACTIONS)[number]>("warn");
  const [reason, setReason] = useState("");
  const [duration, setDuration] = useState<number | null>(3600);

  const addNote = useMutation({
    mutationFn: () => api(`/guilds/${guildId}/members/${userId}/notes`, { method: "POST", json: { note } }),
    onSuccess: () => { setNote(""); qc.invalidateQueries({ queryKey: key }); },
    onError: (e) => toast.error(errorText(e, t("states.errorBody"))),
  });
  const delNote = useMutation({
    mutationFn: (id: string) => api(`/guilds/${guildId}/members/${userId}/notes/${id}`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: key }),
  });
  const act = useMutation({
    mutationFn: () => api<{ case: number }>(`/guilds/${guildId}/members/${userId}/actions`, {
      method: "POST",
      json: { action, reason: reason.trim() || null, duration_seconds: action === "timeout" || action === "ban" ? duration : null },
    }),
    onSuccess: (r) => {
      toast.success(t("members.actionDone", { number: r.case }));
      setReason("");
      qc.invalidateQueries({ queryKey: key });
      qc.invalidateQueries({ queryKey: ["cases", guildId] });
    },
    onError: (e) => toast.error(errorText(e, t("states.errorBody"))),
  });

  const p = q.data;
  const m = p?.member;
  return (
    <Dialog.Root open onOpenChange={(o) => !o && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/60" />
        <Dialog.Content className="fixed inset-y-0 right-0 z-50 w-[min(560px,100vw)] overflow-y-auto border-l border-border bg-sidebar p-6">
          <div className="mb-5 flex items-center justify-between">
            <Dialog.Title className="text-lg font-semibold">{t("members.profile")}</Dialog.Title>
            <Dialog.Close className="grid size-9 place-items-center rounded-lg text-muted hover:bg-panel-hover" aria-label={t("common.close")}><X className="size-5" /></Dialog.Close>
          </div>
          {q.isPending ? <Skeleton className="h-64" /> : q.isError ? <ErrorState error={q.error} /> : p && (
            <div className="space-y-6">
              <div className="flex items-center gap-4">
                {m ? <Avatar url={m.avatar_url} size={56} /> : <span className="size-14 rounded-full bg-input" />}
                <div className="min-w-0">
                  <p className="text-lg font-semibold">{m ? (m.nick ?? m.global_name ?? m.username) : userId}</p>
                  {m && <p className="text-muted">@{m.username}</p>}
                  <p className="font-mono text-[12px] text-muted">{userId}</p>
                </div>
              </div>
              <div className="flex flex-wrap gap-2">
                {!p.in_guild && <Badge tone="danger">{t("members.notInGuild")}</Badge>}
                <Badge tone={p.active_warns ? "warning" : "neutral"}>{t("members.activeWarns", { count: p.active_warns })}</Badge>
                {m?.joined_at && <Badge>{t("members.joined", { date: format.dateTime(new Date(m.joined_at), { dateStyle: "medium" }) })}</Badge>}
              </div>
              {m && m.roles.length > 0 && (
                <div className="flex flex-wrap gap-1.5">
                  {m.roles.map((rid) => {
                    const r = roles?.find((x) => x.id === rid);
                    return r ? (
                      <span key={rid} className="inline-flex items-center gap-1.5 rounded-md bg-input px-2 py-0.5 text-[12px]">
                        <span className="size-2 rounded-full" style={{ background: r.color ? colorToHex(r.color) : "var(--nx-text-muted)" }} aria-hidden />
                        {r.name}
                      </span>
                    ) : null;
                  })}
                </div>
              )}

              {p.can_act && (
                <div className="space-y-3 rounded-xl border border-border p-4">
                  <h3 className="text-sm font-semibold">{t("members.action")}</h3>
                  <div className="flex flex-wrap gap-2">
                    <select className={cn(inputClass, "w-44")} value={action} onChange={(e) => setAction(e.target.value as typeof action)} aria-label={t("moderation.action")}>
                      {ACTIONS.map((a) => <option key={a} value={a}>{t(`moderation.action_${a}`)}</option>)}
                    </select>
                    {(action === "timeout" || action === "ban") && <DurationInput id="member-duration" value={duration} onChange={setDuration} max={action === "ban" ? 31536000 : 2419200} />}
                    {action === "ban" && (
                      <button type="button" className="text-[12px] text-muted underline" onClick={() => setDuration(null)}>{t("duration.permanent")}</button>
                    )}
                  </div>
                  <Field id="member-reason" label={t("moderation.reason")}>
                    <input id="member-reason" className={inputClass} value={reason} maxLength={1000} onChange={(e) => setReason(e.target.value)} />
                  </Field>
                  <Button variant={["kick", "ban"].includes(action) ? "danger" : "primary"} loading={act.isPending} onClick={() => act.mutate()}>
                    {t("members.apply", { action: t(`moderation.action_${action}`) })}
                  </Button>
                  <p className="text-[12px] text-muted">{t("members.actionHelp")}</p>
                </div>
              )}

              <div>
                <h3 className="mb-2 text-sm font-semibold">{t("members.notes")}</h3>
                {p.can_act && (
                  <form className="mb-3 flex gap-2" onSubmit={(e) => { e.preventDefault(); if (note.trim()) addNote.mutate(); }}>
                    <input className={inputClass} value={note} maxLength={1000} onChange={(e) => setNote(e.target.value)} placeholder={t("members.notePlaceholder")} aria-label={t("members.notes")} />
                    <Button type="submit" variant="secondary" loading={addNote.isPending}>{t("common.save")}</Button>
                  </form>
                )}
                {p.notes.length === 0 ? <p className="text-[13px] text-muted">{t("members.noNotes")}</p> : (
                  <ul className="space-y-2">
                    {p.notes.map((n) => (
                      <li key={n.id} className="rounded-lg border border-border p-3 text-sm">
                        <p className="whitespace-pre-wrap">{n.note}</p>
                        <p className="mt-1 flex items-center justify-between text-[12px] text-muted">
                          {n.author} · {format.dateTime(new Date(n.created_at), { dateStyle: "medium", timeStyle: "short" })}
                          {p.can_act && <button type="button" onClick={() => delNote.mutate(n.id)} className="hover:text-danger" aria-label={t("automod.delete")}><Trash2 className="size-3.5" /></button>}
                        </p>
                      </li>
                    ))}
                  </ul>
                )}
              </div>

              <div>
                <h3 className="mb-2 text-sm font-semibold">{t("moderation.userHistory")}</h3>
                {p.cases.length === 0 ? <p className="text-[13px] text-muted">{t("moderation.noCases")}</p> : (
                  <ul className="divide-y divide-border rounded-lg border border-border">
                    {p.cases.map((c) => (
                      <li key={c.id} className={cn("flex items-center gap-3 px-3 py-2 text-[13px]", !c.active && c.action === "warn" && "opacity-50")}>
                        <span className="font-mono text-muted">#{c.number}</span>
                        <Badge>{t(`moderation.action_${c.action}`)}</Badge>
                        <span className="flex-1 truncate text-muted">{c.reason ?? "—"}</span>
                        <span className="text-[12px] text-muted">{format.dateTime(new Date(c.created_at), { dateStyle: "short" })}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </div>
          )}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
