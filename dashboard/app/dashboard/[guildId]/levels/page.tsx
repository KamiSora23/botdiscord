"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Award, Plus, RotateCcw, Trash2, Trophy } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { toast } from "sonner";

import { ChannelSelect } from "@/components/channel-select";
import { ModulePage } from "@/components/module-page";
import { ChannelMultiSelect, RoleMultiSelect, RoleSelect, useRoles } from "@/components/multi-select";
import { ConfirmDialog } from "@/components/save-bar";
import { Avatar, Button, Card, CardHeader, EmptyState, Field, inputClass, Switch } from "@/components/ui";
import { api, errorText } from "@/lib/api";
import { useGuildId } from "@/lib/hooks";
import { useModuleConfig } from "@/lib/use-module";
import { cn, colorToHex, hexToColor } from "@/lib/utils";

type Cfg = {
  xp_min: number; xp_max: number; cooldown_seconds: number; ignored_channel_ids: string[]; ignored_role_ids: string[];
  announce: "current" | "channel" | "dm" | "none"; announce_channel_id: string | null; announce_message: string;
  rewards: { level: number; role_id: string }[]; stack_rewards: boolean; card_color: number;
};
type Row = { rank: number; user_id: string; name: string; avatar_url: string; xp: number; level: number; progress: number; needed: number; messages: number };

export default function LevelsPage() {
  const t = useTranslations();
  const guildId = useGuildId();
  const qc = useQueryClient();
  const ctl = useModuleConfig<Cfg>(guildId, "levels");
  const { data: roles } = useRoles(guildId);
  const form = ctl.form;
  const set = (p: Partial<Cfg>) => form && ctl.setForm({ ...form, ...p });
  const board = useQuery({ queryKey: ["leaderboard", guildId], queryFn: () => api<{ data: Row[]; total: number }>(`/guilds/${guildId}/levels/leaderboard?limit=25`) });
  const [newReward, setNewReward] = useState<{ level: number; role_id: string | null }>({ level: 5, role_id: null });
  const [resetting, setResetting] = useState<Row | null>(null);
  const reset = useMutation({
    mutationFn: (r: Row) => api(`/guilds/${guildId}/levels/members/${r.user_id}`, { method: "DELETE" }),
    onSuccess: () => { setResetting(null); qc.invalidateQueries({ queryKey: ["leaderboard", guildId] }); },
    onError: (e) => toast.error(errorText(e, t("states.errorBody"))),
  });
  const xpErr = form && form.xp_min > form.xp_max;
  const chanErr = form && form.announce === "channel" && !form.announce_channel_id;

  return (
    <ModulePage ctl={ctl as never} title={t("nav.items.levels")} description={t("levels.description")} errorCount={(xpErr ? 1 : 0) + (chanErr ? 1 : 0)}>
      {form && (
        <div className="space-y-6">
          <div className="grid gap-6 lg:grid-cols-2">
            <Card>
              <CardHeader icon={Award} title={t("levels.xp")} description={t("levels.xpHelp")} />
              <fieldset disabled={!ctl.canEdit} className="space-y-4 p-5">
                <div className="flex flex-wrap gap-4">
                  <Field id="lv-min" label={t("levels.xpMin")} error={xpErr ? t("levels.xpError") : undefined}><input id="lv-min" type="number" min={1} max={500} className={cn(inputClass, "w-28")} value={form.xp_min} onChange={(e) => set({ xp_min: Number(e.target.value) })} /></Field>
                  <Field id="lv-max" label={t("levels.xpMax")}><input id="lv-max" type="number" min={1} max={500} className={cn(inputClass, "w-28")} value={form.xp_max} onChange={(e) => set({ xp_max: Number(e.target.value) })} /></Field>
                  <Field id="lv-cd" label={t("levels.cooldown")}>
                    <select id="lv-cd" className={cn(inputClass, "w-36")} value={form.cooldown_seconds} onChange={(e) => set({ cooldown_seconds: Number(e.target.value) })}>
                      {[0, 15, 30, 60, 120, 300].map((s) => <option key={s} value={s}>{s === 0 ? t("autoroles.noDelay") : s < 60 ? t("welcome.seconds", { n: s }) : t("welcome.minutes", { n: s / 60 })}</option>)}
                    </select>
                  </Field>
                </div>
                <Field id="lv-ign-ch" label={t("logging.ignoredChannels")}><ChannelMultiSelect id="lv-ign-ch" guildId={guildId} value={form.ignored_channel_ids} onChange={(v) => set({ ignored_channel_ids: v })} /></Field>
                <Field id="lv-ign-roles" label={t("levels.ignoredRoles")}><RoleMultiSelect id="lv-ign-roles" guildId={guildId} value={form.ignored_role_ids} onChange={(v) => set({ ignored_role_ids: v })} /></Field>
                <Field id="lv-color" label={t("levels.cardColor")}>
                  <input id="lv-color" type="color" className="h-10 w-14 cursor-pointer rounded-lg border border-border bg-input p-1" value={colorToHex(form.card_color).toLowerCase()} onChange={(e) => set({ card_color: hexToColor(e.target.value) ?? form.card_color })} />
                </Field>
              </fieldset>
            </Card>
            <Card>
              <CardHeader title={t("levels.announce")} />
              <fieldset disabled={!ctl.canEdit} className="space-y-4 p-5">
                <Field id="lv-ann" label={t("levels.where")}>
                  <select id="lv-ann" className={inputClass} value={form.announce} onChange={(e) => set({ announce: e.target.value as Cfg["announce"] })}>
                    {(["current", "channel", "dm", "none"] as const).map((a) => <option key={a} value={a}>{t(`levels.announce_${a}`)}</option>)}
                  </select>
                </Field>
                {form.announce === "channel" && <Field id="lv-ann-ch" label={t("welcome.channel")} error={chanErr ? t("welcome.channelRequired") : undefined}><ChannelSelect id="lv-ann-ch" guildId={guildId} value={form.announce_channel_id} onChange={(v) => set({ announce_channel_id: v })} /></Field>}
                {form.announce !== "none" && (
                  <Field id="lv-msg" label={t("welcome.message")} help={t("levels.messageHelp")}>
                    <textarea id="lv-msg" rows={3} className={cn(inputClass, "py-2")} value={form.announce_message} maxLength={500} onChange={(e) => set({ announce_message: e.target.value })} />
                  </Field>
                )}
              </fieldset>
            </Card>
          </div>

          <Card>
            <CardHeader icon={Trophy} title={t("levels.rewards")} description={t("levels.rewardsHelp")} />
            <fieldset disabled={!ctl.canEdit} className="space-y-3 p-5">
              {form.rewards.map((r, i) => (
                <div key={i} className="flex items-center gap-3 rounded-lg border border-border px-3 py-2 text-sm">
                  <span className="w-24 font-medium">{t("levels.level")} {r.level}</span>
                  <span className="flex-1">@{roles?.find((x) => x.id === r.role_id)?.name ?? r.role_id}</span>
                  <button type="button" className="text-muted hover:text-danger" aria-label={t("automod.delete")} onClick={() => set({ rewards: form.rewards.filter((_, j) => j !== i) })}><Trash2 className="size-4" /></button>
                </div>
              ))}
              <div className="flex flex-wrap gap-2">
                <input type="number" min={1} max={500} aria-label={t("levels.level")} className={cn(inputClass, "w-24")} value={newReward.level} onChange={(e) => setNewReward({ ...newReward, level: Number(e.target.value) })} />
                <div className="min-w-48 flex-1"><RoleSelect id="lv-new-role" guildId={guildId} value={newReward.role_id} onChange={(v) => setNewReward({ ...newReward, role_id: v })} /></div>
                <Button type="button" variant="secondary" disabled={!newReward.role_id || form.rewards.some((r) => r.level === newReward.level)}
                  onClick={() => { set({ rewards: [...form.rewards, { level: newReward.level, role_id: newReward.role_id! }].sort((a, b) => a.level - b.level) }); setNewReward({ level: newReward.level + 5, role_id: null }); }}>
                  <Plus className="size-4" aria-hidden />
                </Button>
              </div>
              <label className="flex items-center justify-between gap-4 text-sm">{t("levels.stack")}<Switch checked={form.stack_rewards} label={t("levels.stack")} onCheckedChange={(v) => set({ stack_rewards: v })} /></label>
            </fieldset>
          </Card>

          <Card className="overflow-hidden">
            <CardHeader title={t("levels.leaderboard", { count: board.data?.total ?? 0 })} />
            {!board.data?.data.length ? <EmptyState icon={Trophy} title={t("levels.empty")} /> : (
              <ul className="divide-y divide-border">
                {board.data.data.map((r) => (
                  <li key={r.user_id} className="flex items-center gap-3 px-5 py-2.5 text-sm">
                    <span className="w-8 font-mono text-muted">#{r.rank}</span>
                    <Avatar url={r.avatar_url} size={28} />
                    <span className="min-w-0 flex-1 truncate">{r.name}</span>
                    <span className="hidden w-40 sm:block"><span className="block h-1.5 overflow-hidden rounded-full bg-input"><span className="block h-full rounded-full bg-primary" style={{ width: `${Math.round((100 * r.progress) / r.needed)}%` }} /></span></span>
                    <span className="w-20 text-right">{t("levels.level")} <b>{r.level}</b></span>
                    <span className="w-24 text-right font-mono text-[12px] text-muted">{r.xp.toLocaleString()} XP</span>
                    {ctl.canManage && <button type="button" className="text-muted hover:text-danger" aria-label={t("levels.reset")} onClick={() => setResetting(r)}><RotateCcw className="size-4" /></button>}
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>
      )}
      <ConfirmDialog open={resetting !== null} title={t("levels.resetTitle", { name: resetting?.name ?? "" })} body={t("levels.resetBody")} confirmLabel={t("levels.reset")} destructive onCancel={() => setResetting(null)} onConfirm={() => resetting && reset.mutate(resetting)} />
    </ModulePage>
  );
}
