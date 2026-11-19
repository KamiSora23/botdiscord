"use client";

import { useMutation } from "@tanstack/react-query";
import { Bell, EyeOff, LockOpen, ShieldCheck, Siren, UserX, Wand2 } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { toast } from "sonner";

import { ChannelSelect, useChannels } from "@/components/channel-select";
import { DiscordPreview } from "@/components/discord-preview";
import { MessageEditor } from "@/components/message-editor";
import { ModulePage } from "@/components/module-page";
import { ChannelMultiSelect, RoleSelect } from "@/components/multi-select";
import { ConfirmDialog } from "@/components/save-bar";
import { Badge, Button, Card, CardHeader, Field, inputClass, Switch } from "@/components/ui";
import { api, errorText } from "@/lib/api";
import { useGuildId } from "@/lib/hooks";
import { clean, type MessageTemplate } from "@/lib/messages";
import { useModuleConfig } from "@/lib/use-module";
import { useSample } from "@/lib/use-sample";
import { cn } from "@/lib/utils";

type Verification = {
  enabled: boolean; channel_id: string | null; message_id: string | null; role_id: string | null;
  method: "button" | "captcha"; message: MessageTemplate; button_label: string;
  public_channel_ids: string[]; gate_active: boolean; gate_backup: Record<string, number[] | null>;
};
type Cfg = {
  verification: Verification; alert_channel_id: string | null;
  min_account_age_days: number; young_action: "alert" | "kick" | "quarantine";
  raid_detection: boolean; raid_joins: number; raid_seconds: number; raid_action: "alert" | "lockdown" | "kick"; raid_minutes: number;
  quarantine_role_id: string | null;
};

export default function AntiraidPage() {
  const t = useTranslations();
  const guildId = useGuildId();
  const ctl = useModuleConfig<Cfg>(guildId, "antiraid", (c) => ({ ...c, verification: { ...c.verification, message: clean(c.verification.message) } }));
  const form = ctl.form;
  const set = (p: Partial<Cfg>) => form && ctl.setForm({ ...form, ...p });
  const setV = (p: Partial<Verification>) => form && set({ verification: { ...form.verification, ...p } });
  const { data: channels } = useChannels(guildId);
  const { sample, color } = useSample(guildId, channels?.find((c) => c.id === form?.verification.channel_id)?.name ?? null);

  const publish = useMutation({
    mutationFn: () => api(`/guilds/${guildId}/antiraid/verification/publish`, { method: "POST" }),
    onSuccess: () => { toast.success(t("rr.published")); ctl.query.refetch().then(() => ctl.discard()); },
    onError: (e) => toast.error(errorText(e, t("states.errorBody"))),
  });
  const createRole = useMutation({
    mutationFn: () => api<{ role_id: string; channels: number }>(`/guilds/${guildId}/antiraid/quarantine-role`, { method: "POST" }),
    onSuccess: (r) => { set({ quarantine_role_id: r.role_id }); toast.success(t("antiraid.roleCreated", { count: r.channels })); },
    onError: (e) => toast.error(errorText(e, t("states.errorBody"))),
  });

  const [confirmGate, setConfirmGate] = useState<"apply" | "undo" | null>(null);
  const gate = useMutation({
    mutationFn: (action: "apply" | "undo") => api<{ active: boolean; changed: number }>(`/guilds/${guildId}/antiraid/gate`, { method: "POST", json: { action } }),
    onSuccess: (r) => {
      toast.success(r.active ? t("antiraid.gateApplied", { count: r.changed }) : t("antiraid.gateRemoved"));
      ctl.query.refetch().then(() => ctl.discard());
    },
    onError: (e) => toast.error(errorText(e, t("states.errorBody"))),
    onSettled: () => setConfirmGate(null),
  });

  const vErr = !!form?.verification.enabled && (!form.verification.channel_id || !form.verification.role_id);
  const qErr = !!form && form.young_action === "quarantine" && form.min_account_age_days > 0 && !form.quarantine_role_id;
  const num = (k: keyof Cfg, label: string, min: number, max: number, help?: string) => form && (
    <Field id={`ar-${k}`} label={label} help={help}>
      <input id={`ar-${k}`} type="number" min={min} max={max} className={inputClass} value={form[k] as number}
        onChange={(e) => set({ [k]: Math.max(min, Math.min(max, Number(e.target.value))) } as Partial<Cfg>)} />
    </Field>
  );

  return (
    <ModulePage ctl={ctl as never} title={t("nav.items.antiraid")} description={t("antiraid.description")} errorCount={(vErr ? 1 : 0) + (qErr ? 1 : 0)}>
      {form && (
        <div className="space-y-6">
          <Card>
            <CardHeader icon={ShieldCheck} title={t("antiraid.verification")} description={t("antiraid.verificationHelp")} />
            <div className="grid gap-6 p-5 lg:grid-cols-2">
              <fieldset disabled={!ctl.canEdit} className="space-y-4">
                <label className="flex items-center justify-between gap-4 text-sm">{t("antiraid.verifyEnabled")}<Switch checked={form.verification.enabled} label={t("antiraid.verifyEnabled")} onCheckedChange={(v) => setV({ enabled: v })} /></label>
                <div className="grid gap-4 sm:grid-cols-2">
                  <Field id="ar-vchannel" label={t("antiraid.verifyChannel")}><ChannelSelect id="ar-vchannel" guildId={guildId} value={form.verification.channel_id} onChange={(v) => setV({ channel_id: v })} needEmbed /></Field>
                  <Field id="ar-vrole" label={t("antiraid.verifyRole")}><RoleSelect id="ar-vrole" guildId={guildId} value={form.verification.role_id} onChange={(v) => setV({ role_id: v })} disabled={form.verification.gate_active} /></Field>
                  <Field id="ar-method" label={t("antiraid.method")}>
                    <select id="ar-method" className={inputClass} value={form.verification.method} onChange={(e) => setV({ method: e.target.value as Verification["method"] })}>
                      <option value="captcha">{t("antiraid.methodCaptcha")}</option>
                      <option value="button">{t("antiraid.methodButton")}</option>
                    </select>
                  </Field>
                  <Field id="ar-label" label={t("antiraid.buttonLabel")}><input id="ar-label" className={inputClass} maxLength={80} value={form.verification.button_label} onChange={(e) => setV({ button_label: e.target.value })} /></Field>
                </div>
                {vErr && <p className="text-[13px] text-danger">{t("antiraid.verifyIncomplete")}</p>}
                <h3 className="pt-2 text-sm font-semibold">{t("tickets.panelMessage")}</h3>
                <MessageEditor idPrefix="ar-v" value={form.verification.message} onChange={(m) => setV({ message: m })} defaultColor={color} />
              </fieldset>
              <div className="space-y-3">
                <DiscordPreview template={form.verification.message} sample={sample} color={color} />
                <div className="-mt-3 rounded-b-xl bg-[#313338] px-4 pb-4 pl-[72px]">
                  <span className="inline-flex h-8 items-center gap-1.5 rounded bg-[#248046] px-4 text-sm font-medium text-white">✅ {form.verification.button_label}</span>
                </div>
                <Button className="w-full" variant="secondary" disabled={!form.verification.enabled || vErr || ctl.dirty || !ctl.canEdit || !ctl.enabled} loading={publish.isPending} onClick={() => publish.mutate()}>
                  <ShieldCheck className="size-4" aria-hidden /> {form.verification.message_id ? t("rr.update") : t("rr.publish")}
                </Button>
                {ctl.dirty && <p className="text-[12px] text-muted">{t("welcome.saveFirst")}</p>}
                <div className="rounded-lg border border-border bg-panel-hover p-3 text-[13px] leading-relaxed text-muted">
                  <p className="mb-1 font-medium text-text">{t("antiraid.setupTitle")}</p>
                  <ol className="list-decimal space-y-1 pl-4">
                    <li>{t("antiraid.setup1")}</li>
                    <li>{t("antiraid.setup2")}</li>
                    <li>{t("antiraid.setup3")}</li>
                  </ol>
                </div>
              </div>
            </div>
          </Card>

          <Card>
            <CardHeader icon={EyeOff} title={t("antiraid.gateTitle")} description={t("antiraid.gateHelp")}
              action={form.verification.gate_active ? <Badge tone="success">{t("antiraid.gateOn")}</Badge> : <Badge>{t("antiraid.gateOff")}</Badge>} />
            <div className="grid gap-6 p-5 lg:grid-cols-[1fr_320px]">
              <fieldset disabled={!ctl.canEdit} className="space-y-3">
                <Field id="ar-public" label={t("antiraid.publicChannels")} help={t("antiraid.publicHelp")}>
                  <ChannelMultiSelect id="ar-public" guildId={guildId} value={form.verification.public_channel_ids} onChange={(v) => setV({ public_channel_ids: v.slice(0, 10) })} />
                </Field>
                <ul className="list-disc space-y-1 pl-5 text-[13px] text-muted">
                  <li>{t("antiraid.gateRule1")}</li>
                  <li>{t("antiraid.gateRule2")}</li>
                  <li>{t("antiraid.gateRule3")}</li>
                </ul>
              </fieldset>
              <div className="space-y-2">
                <Button className="w-full" disabled={!ctl.canManage || !ctl.enabled || ctl.dirty || !form.verification.enabled || vErr} loading={gate.isPending && confirmGate === "apply"} onClick={() => setConfirmGate("apply")}>
                  <EyeOff className="size-4" aria-hidden /> {form.verification.gate_active ? t("antiraid.gateReapply") : t("antiraid.gateApply")}
                </Button>
                {form.verification.gate_active && (
                  <Button className="w-full" variant="secondary" disabled={!ctl.canManage || ctl.dirty} loading={gate.isPending && confirmGate === "undo"} onClick={() => setConfirmGate("undo")}>
                    <LockOpen className="size-4" aria-hidden /> {t("antiraid.gateUndo")}
                  </Button>
                )}
                {ctl.dirty && <p className="text-[12px] text-muted">{t("welcome.saveFirst")}</p>}
                {!form.verification.enabled && <p className="text-[12px] text-muted">{t("antiraid.gateNeedsVerify")}</p>}
              </div>
            </div>
          </Card>

          <div className="grid gap-6 lg:grid-cols-2">
            <Card>
              <CardHeader icon={UserX} title={t("antiraid.young")} description={t("antiraid.youngHelp")} />
              <fieldset disabled={!ctl.canEdit} className="grid gap-4 p-5 sm:grid-cols-2">
                {num("min_account_age_days", t("antiraid.minAge"), 0, 365, t("antiraid.minAgeHelp"))}
                <Field id="ar-young" label={t("antiraid.action")}>
                  <select id="ar-young" className={inputClass} value={form.young_action} onChange={(e) => set({ young_action: e.target.value as Cfg["young_action"] })}>
                    <option value="alert">{t("antiraid.actAlert")}</option>
                    <option value="quarantine">{t("antiraid.actQuarantine")}</option>
                    <option value="kick">{t("antiraid.actKick")}</option>
                  </select>
                </Field>
                {qErr && <p className="text-[13px] text-danger sm:col-span-2">{t("antiraid.needQuarantineRole")}</p>}
              </fieldset>
            </Card>

            <Card>
              <CardHeader icon={Siren} title={t("antiraid.raid")} description={t("antiraid.raidHelp")} />
              <fieldset disabled={!ctl.canEdit} className="grid gap-4 p-5 sm:grid-cols-2">
                <label className="flex items-center justify-between gap-4 text-sm sm:col-span-2">{t("antiraid.raidEnabled")}<Switch checked={form.raid_detection} label={t("antiraid.raidEnabled")} onCheckedChange={(v) => set({ raid_detection: v })} /></label>
                {num("raid_joins", t("antiraid.raidJoins"), 3, 100)}
                {num("raid_seconds", t("antiraid.raidSeconds"), 5, 300)}
                <Field id="ar-raid-action" label={t("antiraid.action")}>
                  <select id="ar-raid-action" className={inputClass} value={form.raid_action} onChange={(e) => set({ raid_action: e.target.value as Cfg["raid_action"] })}>
                    <option value="alert">{t("antiraid.actAlert")}</option>
                    <option value="lockdown">{t("antiraid.actLockdown")}</option>
                    <option value="kick">{t("antiraid.actKickRaid")}</option>
                  </select>
                </Field>
                {num("raid_minutes", t("antiraid.raidMinutes"), 1, 120)}
                <p className="text-[12px] text-muted sm:col-span-2">{t("antiraid.raidSummary", { joins: form.raid_joins, seconds: form.raid_seconds })}</p>
              </fieldset>
            </Card>
          </div>

          <Card>
            <CardHeader icon={Bell} title={t("antiraid.alertsTitle")} description={t("antiraid.alertsHelp")} />
            <fieldset disabled={!ctl.canEdit} className="grid gap-4 p-5 sm:grid-cols-2">
              <Field id="ar-alert" label={t("antiraid.alertChannel")} help={t("antiraid.alertChannelHelp")}><ChannelSelect id="ar-alert" guildId={guildId} value={form.alert_channel_id} onChange={(v) => set({ alert_channel_id: v })} needEmbed /></Field>
              <div className="space-y-2">
                <Field id="ar-qrole" label={t("antiraid.quarantineRole")} help={t("antiraid.quarantineRoleHelp")}><RoleSelect id="ar-qrole" guildId={guildId} value={form.quarantine_role_id} onChange={(v) => set({ quarantine_role_id: v })} /></Field>
                <Button variant="ghost" className={cn("w-full")} disabled={!ctl.canManage || !ctl.enabled} loading={createRole.isPending} onClick={() => createRole.mutate()}>
                  <Wand2 className="size-4" aria-hidden /> {t("antiraid.createRole")}
                </Button>
              </div>
              <p className="text-[12px] text-muted sm:col-span-2">{t("antiraid.commandsHelp")}</p>
            </fieldset>
          </Card>
        </div>
      )}
      <ConfirmDialog
        open={confirmGate !== null}
        title={confirmGate === "undo" ? t("antiraid.gateUndo") : t("antiraid.gateApply")}
        body={confirmGate === "undo" ? t("antiraid.gateUndoBody") : t("antiraid.gateApplyBody")}
        confirmLabel={confirmGate === "undo" ? t("antiraid.gateUndo") : t("antiraid.gateApply")}
        onCancel={() => { if (!gate.isPending) setConfirmGate(null); }}
        onConfirm={() => { if (confirmGate) gate.mutate(confirmGate); }}
      />
    </ModulePage>
  );
}
