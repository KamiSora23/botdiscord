"use client";

import { useMutation } from "@tanstack/react-query";
import { Bug, Plus, Repeat, Send, Trash2, Wand2 } from "lucide-react";
import { useTranslations } from "next-intl";
import { toast } from "sonner";

import { ChannelSelect, useChannels } from "@/components/channel-select";
import { DiscordPreview } from "@/components/discord-preview";
import { MessageEditor } from "@/components/message-editor";
import { ModulePage } from "@/components/module-page";
import { RoleMultiSelect } from "@/components/multi-select";
import { Button, Card, CardHeader, Field, inputClass } from "@/components/ui";
import { api, errorText } from "@/lib/api";
import { useGuildId } from "@/lib/hooks";
import { clean, type MessageTemplate } from "@/lib/messages";
import { useModuleConfig } from "@/lib/use-module";
import { useSample } from "@/lib/use-sample";
import { cn } from "@/lib/utils";

type Cfg = {
  channel_id: string | null; message_id: string | null; message: MessageTemplate;
  action: "delete" | "timeout" | "kick" | "softban" | "ban"; timeout_minutes: number; purge_minutes: number;
  exempt_role_ids: string[]; alert_channel_id: string | null;
  escalation: Step[]; strike_window_days: number;
};
type Step = { count: number; action: Cfg["action"]; timeout_minutes: number };
const ACTIONS = ["delete", "timeout", "kick", "softban", "ban"] as const;
const MINUTES = [10, 60, 360, 1440, 10080, 40320];

export default function HoneypotPage() {
  const t = useTranslations();
  const guildId = useGuildId();
  const ctl = useModuleConfig<Cfg>(guildId, "honeypot", (c) => ({ ...c, message: clean(c.message) }));
  const form = ctl.form;
  const set = (p: Partial<Cfg>) => form && ctl.setForm({ ...form, ...p });
  const { data: channels } = useChannels(guildId);
  const { sample, color } = useSample(guildId, channels?.find((c) => c.id === form?.channel_id)?.name ?? null);

  const done = () => ctl.query.refetch().then(() => ctl.discard());
  const setup = useMutation({
    mutationFn: () => api(`/guilds/${guildId}/honeypot/setup`, { method: "POST" }),
    onSuccess: () => { toast.success(t("honeypot.created")); done(); },
    onError: (e) => toast.error(errorText(e, t("states.errorBody"))),
  });
  const publish = useMutation({
    mutationFn: () => api(`/guilds/${guildId}/honeypot/publish`, { method: "POST" }),
    onSuccess: () => { toast.success(t("rr.published")); done(); },
    onError: (e) => toast.error(errorText(e, t("states.errorBody"))),
  });

  return (
    <ModulePage ctl={ctl as never} title={t("nav.items.honeypot")} description={t("honeypot.description")} errorCount={form && new Set(form.escalation.map((x) => x.count)).size !== form.escalation.length ? 1 : 0}>
      {form && (
        <div className="space-y-6">
          <Card>
            <CardHeader icon={Bug} title={t("honeypot.howTitle")} />
            <ol className="list-decimal space-y-1.5 py-4 pl-10 pr-5 text-[13px] text-muted">
              <li>{t("honeypot.how1")}</li>
              <li>{t("honeypot.how2")}</li>
              <li>{t("honeypot.how3")}</li>
              <li>{t("honeypot.how4")}</li>
            </ol>
          </Card>

          <div className="grid gap-6 lg:grid-cols-2">
            <Card>
              <CardHeader title={t("honeypot.channelTitle")} />
              <fieldset disabled={!ctl.canEdit} className="space-y-4 p-5">
                <Field id="hp-channel" label={t("honeypot.channel")} help={t("honeypot.channelHelp")}>
                  <ChannelSelect id="hp-channel" guildId={guildId} value={form.channel_id} onChange={(v) => set({ channel_id: v, message_id: null })} />
                </Field>
                <Button className="w-full" variant="secondary" disabled={!ctl.canManage || !ctl.enabled || ctl.dirty} loading={setup.isPending} onClick={() => setup.mutate()}>
                  <Wand2 className="size-4" aria-hidden /> {t("honeypot.create")}
                </Button>
                {!ctl.enabled && <p className="text-[12px] text-muted">{t("tempvoice.enableFirst")}</p>}
                <Field id="hp-alert" label={t("antiraid.alertChannel")} help={t("antiraid.alertChannelHelp")}>
                  <ChannelSelect id="hp-alert" guildId={guildId} value={form.alert_channel_id} onChange={(v) => set({ alert_channel_id: v })} needEmbed />
                </Field>
                <Field id="hp-exempt" label={t("honeypot.exempt")} help={t("honeypot.exemptHelp")}>
                  <RoleMultiSelect id="hp-exempt" guildId={guildId} value={form.exempt_role_ids} onChange={(v) => set({ exempt_role_ids: v })} />
                </Field>
              </fieldset>
            </Card>

            <Card>
              <CardHeader title={t("honeypot.actionTitle")} description={t("honeypot.actionHelp")} />
              <fieldset disabled={!ctl.canEdit} className="space-y-4 p-5">
                <Field id="hp-action" label={t("honeypot.action")}>
                  <select id="hp-action" className={inputClass} value={form.action} onChange={(e) => set({ action: e.target.value as Cfg["action"] })}>
                    {(["delete", "timeout", "kick", "softban", "ban"] as const).map((a) => <option key={a} value={a}>{t(`honeypot.act_${a}`)}</option>)}
                  </select>
                </Field>
                {form.action === "timeout" && (
                  <Field id="hp-timeout" label={t("honeypot.timeoutMinutes")}>
                    <select id="hp-timeout" className={inputClass} value={form.timeout_minutes} onChange={(e) => set({ timeout_minutes: Number(e.target.value) })}>
                      {[10, 60, 360, 1440, 10080, 40320].map((m) => <option key={m} value={m}>{t(`honeypot.mins_${m}`)}</option>)}
                    </select>
                  </Field>
                )}
                {form.action !== "ban" && form.action !== "softban" ? (
                  <Field id="hp-purge" label={t("honeypot.purge")} help={t("honeypot.purgeHelp")}>
                    <select id="hp-purge" className={inputClass} value={form.purge_minutes} onChange={(e) => set({ purge_minutes: Number(e.target.value) })}>
                      {[0, 10, 30, 60, 180, 1440].map((m) => <option key={m} value={m}>{t(`honeypot.purge_${m}`)}</option>)}
                    </select>
                  </Field>
                ) : <p className="text-[12px] text-muted">{t("honeypot.banPurges")}</p>}
                <p className="rounded-lg border border-border bg-panel-hover p-3 text-[12px] text-muted">{t("honeypot.staffNote")}</p>
              </fieldset>
            </Card>
          </div>

          <Card>
            <CardHeader icon={Repeat} title={t("honeypot.repeatTitle")} description={t("honeypot.repeatHelp")} action={
              ctl.canEdit && <Button size="sm" disabled={form.escalation.length >= 5} onClick={() => {
                const next = Math.max(form.escalation.reduce((m, s) => Math.max(m, s.count), 1) + 1, 3);
                set({ escalation: [...form.escalation, { count: next, action: "ban", timeout_minutes: 1440 }] });
              }}><Plus className="size-4" aria-hidden /> {t("honeypot.addStep")}</Button>
            } />
            <fieldset disabled={!ctl.canEdit} className="space-y-4 p-5">
              <p className="text-[13px]">
                <span className="text-muted">{t("honeypot.firstTime")}</span>{" "}
                <strong>{t(`honeypot.act_${form.action}`)}{form.action === "timeout" ? ` · ${t(`honeypot.mins_${form.timeout_minutes}`)}` : ""}</strong>
              </p>
              {form.escalation.length === 0 ? <p className="text-[13px] text-muted">{t("honeypot.noSteps")}</p> : (
                <ul className="space-y-3">
                  {[...form.escalation].sort((a, b) => a.count - b.count).map((st) => {
                    const i = form.escalation.indexOf(st);
                    const updStep = (p: Partial<Step>) => set({ escalation: form.escalation.map((x, j) => (j === i ? { ...x, ...p } : x)) });
                    const dup = form.escalation.filter((x) => x.count === st.count).length > 1;
                    return (
                      <li key={i} className={cn("flex flex-wrap items-center gap-2 rounded-lg border p-3 text-sm", dup ? "border-danger" : "border-border")}>
                        <span>{t("honeypot.fromTime")}</span>
                        <select aria-label={t("honeypot.fromTime")} className={cn(inputClass, "w-20")} value={st.count} onChange={(e) => updStep({ count: Number(e.target.value) })}>
                          {Array.from({ length: 19 }, (_, n) => n + 2).map((n) => <option key={n} value={n}>{n}ª</option>)}
                        </select>
                        <span>{t("honeypot.time")} →</span>
                        <select aria-label={t("honeypot.action")} className={cn(inputClass, "w-auto min-w-48 flex-1")} value={st.action} onChange={(e) => updStep({ action: e.target.value as Step["action"] })}>
                          {ACTIONS.map((a) => <option key={a} value={a}>{t(`honeypot.act_${a}`)}</option>)}
                        </select>
                        {st.action === "timeout" && (
                          <select aria-label={t("honeypot.timeoutMinutes")} className={cn(inputClass, "w-36")} value={st.timeout_minutes} onChange={(e) => updStep({ timeout_minutes: Number(e.target.value) })}>
                            {MINUTES.map((m) => <option key={m} value={m}>{t(`honeypot.mins_${m}`)}</option>)}
                          </select>
                        )}
                        <Button variant="ghost" size="sm" aria-label={t("automod.delete")} onClick={() => set({ escalation: form.escalation.filter((_, j) => j !== i) })}><Trash2 className="size-4" /></Button>
                        {dup && <span className="w-full text-[12px] text-danger">{t("honeypot.dupStep")}</span>}
                      </li>
                    );
                  })}
                </ul>
              )}
              <Field id="hp-window" label={t("honeypot.window")} help={t("honeypot.windowHelp")}>
                <select id="hp-window" className={cn(inputClass, "sm:w-72")} value={form.strike_window_days} onChange={(e) => set({ strike_window_days: Number(e.target.value) })}>
                  {[1, 7, 30, 90, 365, 0].map((d) => <option key={d} value={d}>{t(`honeypot.window_${d}`)}</option>)}
                </select>
              </Field>
              {form.action === "ban" || form.action === "softban" || form.action === "kick" ? (
                <p className="rounded-lg border border-border bg-panel-hover p-3 text-[12px] text-muted">{t("honeypot.repeatNote")}</p>
              ) : null}
            </fieldset>
          </Card>

          <Card>
            <CardHeader title={t("honeypot.messageTitle")} description={t("honeypot.messageHelp")} />
            <div className="grid gap-6 p-5 lg:grid-cols-2">
              <fieldset disabled={!ctl.canEdit}>
                <MessageEditor idPrefix="hp" value={form.message} onChange={(m) => set({ message: m })} defaultColor={color} />
              </fieldset>
              <div className="space-y-3">
                <DiscordPreview template={form.message} sample={sample} color={color} />
                <Button className="w-full" variant="secondary" disabled={!form.channel_id || ctl.dirty || !ctl.canEdit || !ctl.enabled} loading={publish.isPending} onClick={() => publish.mutate()}>
                  <Send className="size-4" aria-hidden /> {form.message_id ? t("rr.update") : t("rr.publish")}
                </Button>
                {ctl.dirty && <p className="text-[12px] text-muted">{t("welcome.saveFirst")}</p>}
              </div>
            </div>
          </Card>
        </div>
      )}
    </ModulePage>
  );
}
