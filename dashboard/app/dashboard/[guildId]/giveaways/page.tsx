"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ExternalLink, Gift } from "lucide-react";
import { useFormatter, useTranslations } from "next-intl";
import { useState } from "react";
import { toast } from "sonner";

import { ChannelSelect } from "@/components/channel-select";
import { DurationInput } from "@/components/duration-input";
import { ModulePage } from "@/components/module-page";
import { RoleMultiSelect, RoleSelect } from "@/components/multi-select";
import { Badge, Button, Card, CardHeader, EmptyState, Field, inputClass } from "@/components/ui";
import { api, errorText } from "@/lib/api";
import { useGuildId } from "@/lib/hooks";
import { useModuleConfig } from "@/lib/use-module";
import { cn } from "@/lib/utils";

type Cfg = { manager_role_ids: string[]; ping_role_id: string | null };
type G = { id: string; prize: string; winner_count: number; ends_at: string; ended: boolean; entries: number; winner_ids: string[]; seed: string | null; jump_url: string | null };

export default function GiveawaysPage() {
  const t = useTranslations();
  const format = useFormatter();
  const guildId = useGuildId();
  const qc = useQueryClient();
  const ctl = useModuleConfig<Cfg>(guildId, "giveaways");
  const form = ctl.form;
  const list = useQuery({ queryKey: ["giveaways", guildId], queryFn: () => api<{ data: G[] }>(`/guilds/${guildId}/giveaways`), refetchInterval: 30_000 });
  const [draft, setDraft] = useState({ channel_id: null as string | null, prize: "", description: "", winner_count: 1, duration_seconds: 86400, required_role_ids: [] as string[] });
  const create = useMutation({
    mutationFn: () => api(`/guilds/${guildId}/giveaways`, { method: "POST", json: { ...draft, description: draft.description || null } }),
    onSuccess: () => { toast.success(t("giveaways.created")); setDraft({ ...draft, prize: "", description: "" }); qc.invalidateQueries({ queryKey: ["giveaways", guildId] }); },
    onError: (e) => toast.error(errorText(e, t("states.errorBody"))),
  });
  const action = useMutation({
    mutationFn: ({ id, a }: { id: string; a: "end" | "reroll" | "cancel" }) => api(`/guilds/${guildId}/giveaways/${id}/${a}`, { method: "POST" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["giveaways", guildId] }),
    onError: (e) => toast.error(errorText(e, t("states.errorBody"))),
  });

  return (
    <ModulePage ctl={ctl as never} title={t("nav.items.giveaways")} description={t("giveaways.description")}>
      {form && (
        <div className="space-y-6">
          <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_340px]">
            <Card>
              <CardHeader icon={Gift} title={t("giveaways.new")} />
              <fieldset disabled={!ctl.canEdit || !ctl.enabled} className="grid gap-4 p-5 sm:grid-cols-2">
                <Field id="gw-prize" label={t("giveaways.prize")}><input id="gw-prize" className={inputClass} value={draft.prize} maxLength={200} onChange={(e) => setDraft({ ...draft, prize: e.target.value })} /></Field>
                <Field id="gw-channel" label={t("welcome.channel")}><ChannelSelect id="gw-channel" guildId={guildId} value={draft.channel_id} onChange={(v) => setDraft({ ...draft, channel_id: v })} needEmbed /></Field>
                <div className="sm:col-span-2"><Field id="gw-desc" label={t("editor.description")}><textarea id="gw-desc" rows={2} className={cn(inputClass, "py-2")} value={draft.description} maxLength={1000} onChange={(e) => setDraft({ ...draft, description: e.target.value })} /></Field></div>
                <Field id="gw-duration" label={t("polls.duration")}><DurationInput id="gw-duration" value={draft.duration_seconds} onChange={(v) => setDraft({ ...draft, duration_seconds: v })} max={5184000} /></Field>
                <Field id="gw-winners" label={t("giveaways.winners")}><input id="gw-winners" type="number" min={1} max={20} className={cn(inputClass, "w-28")} value={draft.winner_count} onChange={(e) => setDraft({ ...draft, winner_count: Number(e.target.value) })} /></Field>
                <div className="sm:col-span-2"><Field id="gw-req" label={t("giveaways.required")}><RoleMultiSelect id="gw-req" guildId={guildId} value={draft.required_role_ids} onChange={(v) => setDraft({ ...draft, required_role_ids: v.slice(0, 5) })} /></Field></div>
                <Button disabled={!draft.prize.trim() || !draft.channel_id} loading={create.isPending} onClick={() => create.mutate()}>{t("giveaways.start")}</Button>
              </fieldset>
            </Card>
            <Card className="h-fit">
              <CardHeader title={t("welcome.settings")} />
              <fieldset disabled={!ctl.canEdit} className="space-y-4 p-5">
                <Field id="gw-managers" label={t("giveaways.managers")} help={t("giveaways.managersHelp")}><RoleMultiSelect id="gw-managers" guildId={guildId} value={form.manager_role_ids} onChange={(v) => ctl.setForm({ ...form, manager_role_ids: v })} /></Field>
                <Field id="gw-ping" label={t("giveaways.ping")}><RoleSelect id="gw-ping" guildId={guildId} value={form.ping_role_id} onChange={(v) => ctl.setForm({ ...form, ping_role_id: v })} /></Field>
              </fieldset>
            </Card>
          </div>
          <Card className="overflow-hidden">
            <CardHeader title={t("giveaways.list")} />
            {!list.data?.data.length ? <EmptyState icon={Gift} title={t("giveaways.none")} /> : (
              <ul className="divide-y divide-border">
                {list.data.data.map((g) => (
                  <li key={g.id} className="flex flex-wrap items-center gap-3 px-5 py-3 text-sm">
                    <span className="font-medium">{g.prize}</span>
                    <Badge tone={g.ended ? "neutral" : "success"}>{g.ended ? t("giveaways.ended") : t("giveaways.active")}</Badge>
                    <span className="text-[12px] text-muted">{t("giveaways.entries", { count: g.entries })} · {format.relativeTime(new Date(g.ends_at))}</span>
                    {g.ended && g.seed && <span className="font-mono text-[11px] text-muted" title={t("giveaways.seedHelp")}>seed {g.seed.slice(0, 8)}…</span>}
                    <span className="ml-auto flex items-center gap-2">
                      {g.jump_url && <a href={g.jump_url} target="_blank" rel="noopener noreferrer" className="text-primary-text" aria-label="Discord"><ExternalLink className="size-4" /></a>}
                      {ctl.canEdit && (g.ended ? (
                        <Button size="sm" variant="secondary" onClick={() => action.mutate({ id: g.id, a: "reroll" })}>{t("giveaways.reroll")}</Button>
                      ) : (
                        <>
                          <Button size="sm" variant="secondary" onClick={() => action.mutate({ id: g.id, a: "end" })}>{t("giveaways.endNow")}</Button>
                          <Button size="sm" variant="ghost" onClick={() => action.mutate({ id: g.id, a: "cancel" })}>{t("common.cancel")}</Button>
                        </>
                      ))}
                    </span>
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
