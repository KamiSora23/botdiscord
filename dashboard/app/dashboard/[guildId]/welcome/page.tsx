"use client";

import { useMutation } from "@tanstack/react-query";
import { Send } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { toast } from "sonner";

import { ChannelSelect, useChannels } from "@/components/channel-select";
import { DiscordPreview } from "@/components/discord-preview";
import { MessageEditor } from "@/components/message-editor";
import { ModulePage } from "@/components/module-page";
import { Button, Card, CardHeader, Field, inputClass, Switch } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { useGuildId } from "@/lib/hooks";
import { clean, embedChars, isEmpty, LIMITS, type MessageTemplate, unknownVariables, urlError } from "@/lib/messages";
import { useModuleConfig } from "@/lib/use-module";
import { useSample } from "@/lib/use-sample";
import { cn } from "@/lib/utils";

type Join = {
  enabled: boolean;
  channel_id: string | null;
  ignore_bots: boolean;
  message: MessageTemplate;
  dm: { enabled: boolean; message: MessageTemplate | null };
  delete_after_seconds: number | null;
};
type Leave = { enabled: boolean; channel_id: string | null; ignore_bots: boolean; message: MessageTemplate };
type Welcome = { join: Join; leave: Leave };

const DELETE_OPTIONS = [null, 5, 10, 30, 60, 300, 3600, 86400];

function templateErrors(m: MessageTemplate | null): number {
  if (!m) return 0;
  let n = 0;
  if (isEmpty(m)) n++;
  if ((m.content ?? "").length > LIMITS.content) n++;
  for (const e of m.embeds) {
    if (embedChars(e) > LIMITS.total) n++;
    for (const u of [e.url, e.thumbnail_url, e.image_url, e.author.icon_url, e.footer.icon_url]) if (urlError(u)) n++;
    if ((e.description ?? "").length > LIMITS.description || (e.title ?? "").length > LIMITS.title) n++;
  }
  return n;
}

export default function WelcomePage() {
  const t = useTranslations();
  const guildId = useGuildId();
  const ctl = useModuleConfig<Welcome>(guildId, "welcome", (c) => ({
    join: { ...c.join, message: clean(c.join.message), dm: { ...c.join.dm, message: c.join.dm.message ? clean(c.join.dm.message) : null } },
    leave: { ...c.leave, message: clean(c.leave.message) },
  }));
  const [tab, setTab] = useState<"join" | "leave">("join");
  const [previewTarget, setPreviewTarget] = useState<"channel" | "dm">("channel");
  const { data: channels } = useChannels(guildId);
  const form = ctl.form;

  const channelName = (id: string | null) => channels?.find((c) => c.id === id)?.name ?? null;
  const { sample, color } = useSample(guildId, form ? channelName(tab === "join" ? form.join.channel_id : form.leave.channel_id) : null);

  const test = useMutation({
    mutationFn: (part: "join" | "leave" | "dm") => api(`/guilds/${guildId}/modules/welcome/test`, { method: "POST", json: { part } }),
    onSuccess: () => toast.success(t("welcome.testSent")),
    onError: (err) => toast.error(err instanceof ApiError ? (t.has(`welcome.err_${err.code}`) ? t(`welcome.err_${err.code}`) : err.message) : t("states.errorBody")),
  });

  let errors = 0;
  if (form) {
    if (form.join.enabled && !form.join.channel_id) errors++;
    if (form.leave.enabled && !form.leave.channel_id) errors++;
    errors += templateErrors(form.join.message) + templateErrors(form.leave.message) + (form.join.dm.enabled ? templateErrors(form.join.dm.message) : 0);
  }

  const setJoin = (p: Partial<Join>) => form && ctl.setForm({ ...form, join: { ...form.join, ...p } });
  const setLeave = (p: Partial<Leave>) => form && ctl.setForm({ ...form, leave: { ...form.leave, ...p } });

  const sendTest = (part: "join" | "leave" | "dm") => {
    if (ctl.dirty) {
      toast.warning(t("welcome.saveFirst"));
      return;
    }
    test.mutate(part);
  };

  const part = form ? (tab === "join" ? form.join : form.leave) : null;
  const previewMessage =
    form && tab === "join" && previewTarget === "dm" && form.join.dm.enabled && form.join.dm.message ? form.join.dm.message : part?.message;
  const unknown = previewMessage
    ? [previewMessage.content, ...previewMessage.embeds.flatMap((e) => [e.title, e.description, e.footer.text, e.author.name, ...e.fields.flatMap((f) => [f.name, f.value])])].flatMap(unknownVariables)
    : [];

  return (
    <ModulePage ctl={ctl as never} title={t("nav.items.welcome")} description={t("welcome.description")} errorCount={errors}>
      {form && part && (
        <>
          <div role="tablist" className="mb-4 inline-flex rounded-xl border border-border bg-panel p-1">
            {(["join", "leave"] as const).map((k) => (
              <button
                key={k}
                role="tab"
                aria-selected={tab === k}
                onClick={() => {
                  setTab(k);
                  setPreviewTarget("channel");
                }}
                className={cn("min-h-9 rounded-lg px-4 text-sm font-medium", tab === k ? "bg-primary-solid text-white" : "text-muted hover:text-text")}
              >
                {t(k === "join" ? "welcome.tabJoin" : "welcome.tabLeave")}
              </button>
            ))}
          </div>

          <div className="grid items-start gap-6 xl:grid-cols-[minmax(0,1fr)_minmax(0,440px)]">
            <div className="space-y-6">
              <Card>
                <CardHeader title={t("welcome.settings")} />
                <fieldset disabled={!ctl.canEdit} className="space-y-4 p-5">
                  <label className="flex items-center justify-between gap-4">
                    <span>
                      <span className="block text-sm font-medium">{t(tab === "join" ? "welcome.sendJoin" : "welcome.sendLeave")}</span>
                      <span className="text-[13px] text-muted">{t(tab === "join" ? "welcome.sendJoinHelp" : "welcome.sendLeaveHelp")}</span>
                    </span>
                    <Switch checked={part.enabled} label={t(tab === "join" ? "welcome.sendJoin" : "welcome.sendLeave")} onCheckedChange={(v) => (tab === "join" ? setJoin({ enabled: v }) : setLeave({ enabled: v }))} />
                  </label>
                  <Field
                    id={`${tab}-channel`}
                    label={t("welcome.channel")}
                    error={part.enabled && !part.channel_id ? t("welcome.channelRequired") : ctl.fieldErrors[`config.${tab}`] ? t("welcome.channelRequired") : undefined}
                  >
                    <ChannelSelect
                      id={`${tab}-channel`}
                      guildId={guildId}
                      value={part.channel_id}
                      needEmbed={part.message.embeds.length > 0}
                      invalid={part.enabled && !part.channel_id}
                      onChange={(v) => (tab === "join" ? setJoin({ channel_id: v }) : setLeave({ channel_id: v }))}
                    />
                  </Field>
                  <label className="flex items-center justify-between gap-4">
                    <span className="text-sm font-medium">{t("welcome.ignoreBots")}</span>
                    <Switch checked={part.ignore_bots} label={t("welcome.ignoreBots")} onCheckedChange={(v) => (tab === "join" ? setJoin({ ignore_bots: v }) : setLeave({ ignore_bots: v }))} />
                  </label>
                  {tab === "join" && (
                    <Field id="join-delete" label={t("welcome.deleteAfter")}>
                      <select id="join-delete" className={inputClass} value={form.join.delete_after_seconds ?? ""} onChange={(e) => setJoin({ delete_after_seconds: e.target.value ? Number(e.target.value) : null })}>
                        {DELETE_OPTIONS.map((s) => (
                          <option key={s ?? "never"} value={s ?? ""}>
                            {s === null ? t("welcome.never") : s < 60 ? t("welcome.seconds", { n: s }) : s < 3600 ? t("welcome.minutes", { n: s / 60 }) : t("welcome.hours", { n: s / 3600 })}
                          </option>
                        ))}
                      </select>
                    </Field>
                  )}
                </fieldset>
              </Card>

              <Card>
                <CardHeader title={t("welcome.message")} description={t("welcome.messageHelp")} />
                <div className="p-5">
                  <MessageEditor
                    idPrefix={tab}
                    value={part.message}
                    defaultColor={color}
                    disabled={!ctl.canEdit}
                    onChange={(m) => (tab === "join" ? setJoin({ message: m }) : setLeave({ message: m }))}
                  />
                </div>
              </Card>

              {tab === "join" && (
                <Card>
                  <CardHeader
                    title={t("welcome.dm")}
                    description={t("welcome.dmHelp")}
                    action={
                      <Switch
                        checked={form.join.dm.enabled}
                        disabled={!ctl.canEdit}
                        label={t("welcome.dm")}
                        onCheckedChange={(v) => setJoin({ dm: { enabled: v, message: form.join.dm.message ?? { content: "", embeds: [] } } })}
                      />
                    }
                  />
                  {form.join.dm.enabled && form.join.dm.message && (
                    <div className="p-5">
                      <MessageEditor idPrefix="dm" value={form.join.dm.message} defaultColor={color} disabled={!ctl.canEdit} onChange={(m) => setJoin({ dm: { ...form.join.dm, message: m } })} />
                    </div>
                  )}
                </Card>
              )}
            </div>

            <div className="space-y-3 xl:sticky xl:top-24">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h2 className="text-sm font-semibold">{t("editor.preview")}</h2>
                {tab === "join" && form.join.dm.enabled && (
                  <div className="flex rounded-lg border border-border p-0.5 text-[13px]">
                    {(["channel", "dm"] as const).map((p) => (
                      <button key={p} type="button" aria-pressed={previewTarget === p} onClick={() => setPreviewTarget(p)} className={cn("min-h-8 rounded-md px-3", previewTarget === p ? "bg-input" : "text-muted")}>
                        {t(p === "channel" ? "welcome.previewChannel" : "welcome.previewDm")}
                      </button>
                    ))}
                  </div>
                )}
              </div>
              {previewMessage && <DiscordPreview template={previewMessage} sample={sample} color={color} />}
              {unknown.length > 0 && <p className="text-[13px] text-danger">{t("editor.unknownVars", { vars: unknown.map((v) => `{${v}}`).join(", ") })}</p>}
              <Button
                variant="secondary"
                className="w-full"
                loading={test.isPending}
                disabled={!ctl.canEdit}
                onClick={() => sendTest(tab === "join" && previewTarget === "dm" ? "dm" : tab)}
              >
                <Send className="size-4" aria-hidden /> {t(previewTarget === "dm" && tab === "join" ? "welcome.testDm" : "welcome.test")}
              </Button>
              <p className="text-[12px] text-muted">{t("welcome.testHelp")}</p>
            </div>
          </div>
        </>
      )}
    </ModulePage>
  );
}
