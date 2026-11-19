"use client";

import * as Dialog from "@radix-ui/react-dialog";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AtSign, Ban, CaseUpper, FlaskConical, Link2, MailWarning, MessagesSquare, Pencil, Plus, Repeat, ShieldAlert, Trash2, X } from "lucide-react";
import { useFormatter, useTranslations } from "next-intl";
import { useState } from "react";
import { toast } from "sonner";

import { ChannelSelect } from "@/components/channel-select";
import { DurationInput } from "@/components/duration-input";
import { ModulePage } from "@/components/module-page";
import { ChannelMultiSelect, RoleMultiSelect } from "@/components/multi-select";
import { ConfirmDialog } from "@/components/save-bar";
import { Badge, Button, Card, CardHeader, EmptyState, Field, inputClass, Skeleton, Switch } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { useGuildId } from "@/lib/hooks";
import { useModuleConfig } from "@/lib/use-module";
import { cn } from "@/lib/utils";

type AutomodCfg = { log_channel_id: string | null; exempt_role_ids: string[]; exempt_channel_ids: string[] };
type RuleType = "spam" | "duplicates" | "bad_words" | "links" | "invites" | "mass_mentions" | "caps";
type ActionT = "delete" | "alert" | "warn" | "timeout" | "kick" | "ban";
type Rule = {
  id?: string;
  name: string;
  enabled: boolean;
  rule_type: RuleType;
  config: Record<string, unknown>;
  actions: { type: ActionT; duration_seconds?: number | null }[];
  exempt_role_ids: string[];
  exempt_channel_ids: string[];
  priority: number;
  test_mode: boolean;
  version?: number;
};

const TYPES: { type: RuleType; icon: typeof Ban; defaults: Record<string, unknown> }[] = [
  { type: "spam", icon: MessagesSquare, defaults: { max_messages: 5, per_seconds: 5 } },
  { type: "duplicates", icon: Repeat, defaults: { max_repeats: 3, per_seconds: 30 } },
  { type: "bad_words", icon: Ban, defaults: { words: [] } },
  { type: "links", icon: Link2, defaults: { mode: "allowlist", domains: ["youtube.com", "twitch.tv", "x.com"] } },
  { type: "invites", icon: MailWarning, defaults: { allow_own_server: true } },
  { type: "mass_mentions", icon: AtSign, defaults: { max_mentions: 5 } },
  { type: "caps", icon: CaseUpper, defaults: { min_length: 10, max_percent: 70 } },
];
const PUNISH: ActionT[] = ["warn", "timeout", "kick", "ban"];

export default function AutomodPage() {
  const t = useTranslations();
  const guildId = useGuildId();
  const qc = useQueryClient();
  const ctl = useModuleConfig<AutomodCfg>(guildId, "automod");
  const form = ctl.form;
  const set = (p: Partial<AutomodCfg>) => form && ctl.setForm({ ...form, ...p });
  const rules = useQuery({ queryKey: ["automod-rules", guildId], queryFn: () => api<{ data: Rule[]; can_edit: boolean }>(`/guilds/${guildId}/automod/rules`) });
  const [editing, setEditing] = useState<Rule | null>(null);
  const [deleting, setDeleting] = useState<Rule | null>(null);

  const toggle = useMutation({
    mutationFn: (r: Rule) => api(`/guilds/${guildId}/automod/rules/${r.id}`, { method: "PUT", json: { ...strip(r), enabled: !r.enabled, version: r.version } }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["automod-rules", guildId] }),
    onError: (e) => toast.error(e instanceof ApiError ? e.message : t("states.errorBody")),
  });
  const remove = useMutation({
    mutationFn: (r: Rule) => api(`/guilds/${guildId}/automod/rules/${r.id}`, { method: "DELETE" }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["automod-rules", guildId] });
      setDeleting(null);
    },
  });

  return (
    <ModulePage ctl={ctl as never} title={t("nav.items.automod")} description={t("automod.description")}>
      <div className="grid items-start gap-6 xl:grid-cols-[minmax(0,1fr)_380px]">
        <div className="space-y-6">
          <Card>
            <CardHeader
              icon={ShieldAlert}
              title={t("automod.rules")}
              description={t("automod.rulesHelp")}
              action={
                rules.data?.can_edit && (
                  <Button size="sm" onClick={() => setEditing(newRule(t("automod.type_bad_words")))}>
                    <Plus className="size-4" aria-hidden /> {t("automod.newRule")}
                  </Button>
                )
              }
            />
            {rules.isPending ? (
              <Skeleton className="m-5 h-40" />
            ) : !rules.data?.data.length ? (
              <EmptyState icon={ShieldAlert} title={t("automod.noRules")} body={t("automod.noRulesBody")} />
            ) : (
              <ul className="divide-y divide-border">
                {rules.data.data.map((r) => {
                  const Icon = TYPES.find((x) => x.type === r.rule_type)?.icon ?? ShieldAlert;
                  return (
                    <li key={r.id} className="flex flex-wrap items-center gap-3 px-5 py-3">
                      <span className="grid size-9 place-items-center rounded-lg bg-input"><Icon className="size-4 text-muted" aria-hidden /></span>
                      <div className="min-w-0 flex-1">
                        <p className="flex items-center gap-2 font-medium">
                          {r.name}
                          {r.test_mode && <Badge tone="warning">{t("automod.testMode")}</Badge>}
                        </p>
                        <p className="text-[12px] text-muted">
                          {t(`automod.type_${r.rule_type}`)} · {r.actions.map((a) => t(`automod.action_${a.type}`)).join(", ")}
                        </p>
                      </div>
                      <Switch checked={r.enabled} disabled={!rules.data.can_edit} label={r.name} onCheckedChange={() => toggle.mutate(r)} />
                      {rules.data.can_edit && (
                        <>
                          <Button variant="ghost" size="sm" onClick={() => setEditing(r)} aria-label={t("automod.edit")}><Pencil className="size-4" /></Button>
                          <Button variant="ghost" size="sm" onClick={() => setDeleting(r)} aria-label={t("automod.delete")}><Trash2 className="size-4" /></Button>
                        </>
                      )}
                    </li>
                  );
                })}
              </ul>
            )}
          </Card>

          {form && (
            <Card>
              <CardHeader title={t("automod.global")} />
              <fieldset disabled={!ctl.canEdit} className="space-y-4 p-5">
                <Field id="am-log" label={t("automod.logChannel")} help={t("automod.logChannelHelp")}>
                  <ChannelSelect id="am-log" guildId={guildId} value={form.log_channel_id} onChange={(v) => set({ log_channel_id: v })} needEmbed />
                </Field>
                <Field id="am-exempt-roles" label={t("automod.exemptRoles")} help={t("automod.exemptHelp")}>
                  <RoleMultiSelect id="am-exempt-roles" guildId={guildId} value={form.exempt_role_ids} onChange={(v) => set({ exempt_role_ids: v })} />
                </Field>
                <Field id="am-exempt-channels" label={t("automod.exemptChannels")}>
                  <ChannelMultiSelect id="am-exempt-channels" guildId={guildId} value={form.exempt_channel_ids} onChange={(v) => set({ exempt_channel_ids: v })} />
                </Field>
              </fieldset>
            </Card>
          )}
        </div>

        <div className="space-y-6">
          <TestBox guildId={guildId} />
          <RecentEvents guildId={guildId} />
        </div>
      </div>

      {editing && <RuleEditor guildId={guildId} rule={editing} onClose={() => setEditing(null)} />}
      <ConfirmDialog
        open={deleting !== null}
        title={t("automod.deleteTitle", { name: deleting?.name ?? "" })}
        body={t("automod.deleteBody")}
        confirmLabel={t("automod.delete")}
        destructive
        onCancel={() => setDeleting(null)}
        onConfirm={() => deleting && remove.mutate(deleting)}
      />
    </ModulePage>
  );
}

function newRule(name: string): Rule {
  return { name, enabled: true, rule_type: "bad_words", config: { words: [] }, actions: [{ type: "delete" }, { type: "alert" }], exempt_role_ids: [], exempt_channel_ids: [], priority: 0, test_mode: true };
}

function strip(r: Rule) {
  const { id: _id, version: _v, ...rest } = r;
  void _id;
  void _v;
  return rest;
}

function RuleEditor({ guildId, rule, onClose }: { guildId: string; rule: Rule; onClose: () => void }) {
  const t = useTranslations();
  const qc = useQueryClient();
  const [r, setR] = useState<Rule>(rule);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const set = (p: Partial<Rule>) => setR({ ...r, ...p });
  const cfg = (k: string) => r.config[k];
  const setCfg = (k: string, v: unknown) => set({ config: { ...r.config, [k]: v } });
  const has = (a: ActionT) => r.actions.some((x) => x.type === a);
  const punish = r.actions.find((x) => PUNISH.includes(x.type))?.type ?? "";

  const save = useMutation({
    mutationFn: () =>
      r.id
        ? api(`/guilds/${guildId}/automod/rules/${r.id}`, { method: "PUT", json: { ...strip(r), version: r.version } })
        : api(`/guilds/${guildId}/automod/rules`, { method: "POST", json: strip(r) }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["automod-rules", guildId] });
      toast.success(t("settings.saved"));
      onClose();
    },
    onError: (e) => {
      if (e instanceof ApiError && e.fields) setErrors(e.fields);
      toast.error(e instanceof ApiError ? e.message : t("states.errorBody"));
    },
  });

  const setPunish = (p: string) => {
    const keep = r.actions.filter((x) => !PUNISH.includes(x.type));
    set({ actions: p ? [...keep, { type: p as ActionT, duration_seconds: p === "timeout" ? 600 : null }] : keep });
  };
  const toggleAction = (a: ActionT, on: boolean) => set({ actions: on ? [...r.actions, { type: a }] : r.actions.filter((x) => x.type !== a) });
  const words = (cfg("words") as string[] | undefined) ?? [];
  const domains = (cfg("domains") as string[] | undefined) ?? [];
  const num = (k: string, label: string, min: number, max: number) => (
    <Field id={`rule-${k}`} label={label}>
      <input id={`rule-${k}`} type="number" min={min} max={max} className={cn(inputClass, "w-32")} value={Number(cfg(k) ?? min)} onChange={(e) => setCfg(k, Number(e.target.value))} />
    </Field>
  );

  return (
    <Dialog.Root open onOpenChange={(o) => !o && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/60" />
        <Dialog.Content className="fixed inset-y-0 right-0 z-50 flex w-[min(640px,100vw)] flex-col border-l border-border bg-sidebar">
          <div className="flex items-center justify-between border-b border-border px-6 py-4">
            <Dialog.Title className="text-lg font-semibold">{r.id ? t("automod.editRule") : t("automod.newRule")}</Dialog.Title>
            <Dialog.Close className="grid size-9 place-items-center rounded-lg text-muted hover:bg-panel-hover" aria-label={t("common.close")}><X className="size-5" /></Dialog.Close>
          </div>
          <div className="flex-1 space-y-5 overflow-y-auto p-6">
            <Field id="rule-name" label={t("automod.name")} error={errors.name}>
              <input id="rule-name" className={inputClass} value={r.name} maxLength={80} onChange={(e) => set({ name: e.target.value })} />
            </Field>
            {!r.id && (
              <fieldset>
                <legend className="mb-2 text-[13px] font-medium">{t("automod.type")}</legend>
                <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
                  {TYPES.map(({ type, icon: Icon, defaults }) => (
                    <button key={type} type="button" aria-pressed={r.rule_type === type}
                      onClick={() => set({ rule_type: type, config: defaults, name: r.name === t(`automod.type_${r.rule_type}`) ? t(`automod.type_${type}`) : r.name })}
                      className={cn("flex items-center gap-2 rounded-lg border p-3 text-left text-sm", r.rule_type === type ? "border-primary bg-primary/10" : "border-border hover:bg-panel-hover")}>
                      <Icon className="size-4 shrink-0 text-muted" aria-hidden /> {t(`automod.type_${type}`)}
                    </button>
                  ))}
                </div>
              </fieldset>
            )}
            <div className="space-y-3 rounded-xl border border-border p-4">
              <p className="text-[13px] text-muted">{t(`automod.help_${r.rule_type}`)}</p>
              {r.rule_type === "spam" && <div className="flex flex-wrap gap-4">{num("max_messages", t("automod.maxMessages"), 2, 50)}{num("per_seconds", t("automod.perSeconds"), 1, 120)}</div>}
              {r.rule_type === "duplicates" && <div className="flex flex-wrap gap-4">{num("max_repeats", t("automod.maxRepeats"), 2, 20)}{num("per_seconds", t("automod.perSeconds"), 5, 600)}</div>}
              {r.rule_type === "mass_mentions" && num("max_mentions", t("automod.maxMentions"), 1, 50)}
              {r.rule_type === "caps" && <div className="flex flex-wrap gap-4">{num("min_length", t("automod.minLength"), 3, 500)}{num("max_percent", t("automod.maxPercent"), 30, 100)}</div>}
              {r.rule_type === "bad_words" && (
                <Field id="rule-words" label={t("automod.words")} help={t("automod.wordsHelp")}>
                  <textarea id="rule-words" rows={5} className={cn(inputClass, "py-2 font-mono text-[13px]")} defaultValue={words.join("\n")} onChange={(e) => setCfg("words", e.target.value.split(/[\n,]/).map((w) => w.trim()).filter(Boolean))} />
                </Field>
              )}
              {r.rule_type === "links" && (
                <>
                  <Field id="rule-mode" label={t("automod.linkMode")}>
                    <select id="rule-mode" className={inputClass} value={String(cfg("mode"))} onChange={(e) => setCfg("mode", e.target.value)}>
                      {["allowlist", "blocklist", "block_all"].map((m) => <option key={m} value={m}>{t(`automod.mode_${m}`)}</option>)}
                    </select>
                  </Field>
                  {cfg("mode") !== "block_all" && (
                    <Field id="rule-domains" label={t("automod.domains")} help={t("automod.domainsHelp")}>
                      <textarea id="rule-domains" rows={4} className={cn(inputClass, "py-2 font-mono text-[13px]")} defaultValue={domains.join("\n")} onChange={(e) => setCfg("domains", e.target.value.split(/[\n,\s]/).map((w) => w.trim()).filter(Boolean))} />
                    </Field>
                  )}
                </>
              )}
              {r.rule_type === "invites" && (
                <label className="flex items-center justify-between gap-4 text-sm">
                  {t("automod.allowOwnServer")}
                  <Switch checked={Boolean(cfg("allow_own_server"))} label={t("automod.allowOwnServer")} onCheckedChange={(v) => setCfg("allow_own_server", v)} />
                </label>
              )}
            </div>

            <fieldset className="space-y-3">
              <legend className="mb-1 text-[13px] font-medium">{t("automod.actions")}</legend>
              {(["delete", "alert"] as const).map((a) => (
                <label key={a} className="flex items-center justify-between gap-4 text-sm">
                  {t(`automod.action_${a}`)}
                  <Switch checked={has(a)} label={t(`automod.action_${a}`)} onCheckedChange={(v) => toggleAction(a, v)} />
                </label>
              ))}
              <Field id="rule-punish" label={t("automod.punishment")}>
                <div className="flex flex-wrap gap-2">
                  <select id="rule-punish" className={cn(inputClass, "w-48")} value={punish} onChange={(e) => setPunish(e.target.value)}>
                    <option value="">{t("automod.noPunishment")}</option>
                    {PUNISH.map((p) => <option key={p} value={p}>{t(`automod.action_${p}`)}</option>)}
                  </select>
                  {punish === "timeout" && (
                    <DurationInput id="rule-timeout" value={r.actions.find((x) => x.type === "timeout")?.duration_seconds ?? 600}
                      onChange={(v) => set({ actions: r.actions.map((x) => (x.type === "timeout" ? { ...x, duration_seconds: v } : x)) })} />
                  )}
                </div>
              </Field>
              {r.actions.length === 0 && <p className="text-[13px] text-danger">{t("automod.needAction")}</p>}
            </fieldset>

            <Field id="rule-roles" label={t("automod.exemptRoles")}>
              <RoleMultiSelect id="rule-roles" guildId={guildId} value={r.exempt_role_ids} onChange={(v) => set({ exempt_role_ids: v })} />
            </Field>
            <Field id="rule-channels" label={t("automod.exemptChannels")}>
              <ChannelMultiSelect id="rule-channels" guildId={guildId} value={r.exempt_channel_ids} onChange={(v) => set({ exempt_channel_ids: v })} />
            </Field>
            <div className="flex flex-wrap gap-6">
              <Field id="rule-priority" label={t("automod.priority")} help={t("automod.priorityHelp")}>
                <input id="rule-priority" type="number" min={0} max={100} className={cn(inputClass, "w-28")} value={r.priority} onChange={(e) => set({ priority: Number(e.target.value) })} />
              </Field>
              <label className="flex items-center gap-3 pt-6 text-sm">
                <Switch checked={r.test_mode} label={t("automod.testMode")} onCheckedChange={(v) => set({ test_mode: v })} />
                <span>
                  {t("automod.testMode")}
                  <span className="block text-[12px] text-muted">{t("automod.testModeHelp")}</span>
                </span>
              </label>
            </div>
          </div>
          <div className="flex justify-end gap-2 border-t border-border px-6 py-4">
            <Button variant="secondary" onClick={onClose}>{t("common.cancel")}</Button>
            <Button loading={save.isPending} disabled={!r.name.trim() || r.actions.length === 0} onClick={() => save.mutate()}>{t("common.save")}</Button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

function TestBox({ guildId }: { guildId: string }) {
  const t = useTranslations();
  const [text, setText] = useState("");
  const test = useMutation({
    mutationFn: () => api<{ match: null | { rule_name: string; reason: string; detail: string | null } }>(`/guilds/${guildId}/automod/test`, { method: "POST", json: { text } }),
  });
  const m = test.data?.match;
  return (
    <Card>
      <CardHeader icon={FlaskConical} title={t("automod.tryTitle")} description={t("automod.tryHelp")} />
      <div className="space-y-3 p-5">
        <textarea rows={3} className={cn(inputClass, "py-2")} value={text} maxLength={4000} onChange={(e) => setText(e.target.value)} placeholder={t("automod.tryPlaceholder")} aria-label={t("automod.tryTitle")} />
        <Button variant="secondary" className="w-full" disabled={!text.trim()} loading={test.isPending} onClick={() => test.mutate()}>{t("automod.tryButton")}</Button>
        {test.isSuccess && (
          <p className={cn("rounded-lg px-3 py-2 text-[13px]", m ? "bg-danger/10 text-danger" : "bg-success/10 text-success")}>
            {m ? t("automod.tryHit", { rule: m.rule_name, reason: t(`automod.type_${m.reason}`) }) + (m.detail ? ` · ${m.detail}` : "") : t("automod.tryClean")}
          </p>
        )}
        <p className="text-[12px] text-muted">{t("automod.tryNote")}</p>
      </div>
    </Card>
  );
}

function RecentEvents({ guildId }: { guildId: string }) {
  const t = useTranslations();
  const format = useFormatter();
  const q = useQuery({
    queryKey: ["automod-events", guildId],
    queryFn: () => api<{ data: { id: string; rule: string | null; user_id: string; action: string; test_mode: boolean; excerpt: string | null; created_at: string }[] }>(`/guilds/${guildId}/automod/events?limit=15`),
    refetchInterval: 30_000,
  });
  return (
    <Card>
      <CardHeader title={t("automod.recent")} />
      {!q.data?.data.length ? (
        <p className="px-5 py-6 text-center text-[13px] text-muted">{t("automod.noEvents")}</p>
      ) : (
        <ul className="divide-y divide-border">
          {q.data.data.map((e) => (
            <li key={e.id} className="px-5 py-3 text-[13px]">
              <p className="flex items-center gap-2">
                <span className="font-medium">{e.rule ?? "—"}</span>
                {e.test_mode && <Badge tone="warning">{t("automod.testMode")}</Badge>}
                <span className="ml-auto text-[12px] text-muted">{format.relativeTime(new Date(e.created_at))}</span>
              </p>
              {e.excerpt && <p className="truncate text-muted">“{e.excerpt}”</p>}
              <p className="font-mono text-[11px] text-muted">{e.user_id} · {e.action}</p>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
