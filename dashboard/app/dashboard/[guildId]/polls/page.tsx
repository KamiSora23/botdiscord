"use client";

import { useMutation } from "@tanstack/react-query";
import { ExternalLink, Plus, Trash2, Vote } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { toast } from "sonner";

import { ChannelSelect } from "@/components/channel-select";
import { ModulePage } from "@/components/module-page";
import { Button, Card, CardHeader, Field, inputClass, Switch } from "@/components/ui";
import { api, errorText } from "@/lib/api";
import { useGuildId } from "@/lib/hooks";
import { useModuleConfig } from "@/lib/use-module";
import { cn } from "@/lib/utils";

export default function PollsPage() {
  const t = useTranslations();
  const guildId = useGuildId();
  const ctl = useModuleConfig<{ allow_members: boolean }>(guildId, "polls");
  const [channel, setChannel] = useState<string | null>(null);
  const [question, setQuestion] = useState("");
  const [answers, setAnswers] = useState(["", ""]);
  const [hours, setHours] = useState(24);
  const [multiple, setMultiple] = useState(false);
  const [last, setLast] = useState<string | null>(null);
  const create = useMutation({
    mutationFn: () => api<{ jump_url: string }>(`/guilds/${guildId}/polls`, { method: "POST", json: { channel_id: channel, question, answers: answers.filter((a) => a.trim()), duration_hours: hours, multiple } }),
    onSuccess: (r) => { setLast(r.jump_url); setQuestion(""); setAnswers(["", ""]); toast.success(t("polls.created")); },
    onError: (e) => toast.error(errorText(e, t("states.errorBody"))),
  });
  const valid = channel && question.trim() && answers.filter((a) => a.trim()).length >= 2;

  return (
    <ModulePage ctl={ctl as never} title={t("nav.items.polls")} description={t("polls.description")}>
      {ctl.form && (
        <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_340px]">
          <Card>
            <CardHeader icon={Vote} title={t("polls.new")} description={t("polls.newHelp")} />
            <fieldset disabled={!ctl.canEdit || !ctl.enabled} className="space-y-4 p-5">
              <Field id="poll-channel" label={t("welcome.channel")}><ChannelSelect id="poll-channel" guildId={guildId} value={channel} onChange={setChannel} /></Field>
              <Field id="poll-q" label={t("polls.question")}><input id="poll-q" className={inputClass} value={question} maxLength={300} onChange={(e) => setQuestion(e.target.value)} /></Field>
              <fieldset className="space-y-2">
                <legend className="mb-1 text-[13px] font-medium">{t("polls.answers")}</legend>
                {answers.map((a, i) => (
                  <div key={i} className="flex gap-2">
                    <input aria-label={`${t("polls.answers")} ${i + 1}`} className={inputClass} value={a} maxLength={55} onChange={(e) => setAnswers(answers.map((x, j) => (j === i ? e.target.value : x)))} />
                    {answers.length > 2 && <button type="button" className="grid size-10 place-items-center rounded-md text-muted hover:text-danger" aria-label={t("automod.delete")} onClick={() => setAnswers(answers.filter((_, j) => j !== i))}><Trash2 className="size-4" /></button>}
                  </div>
                ))}
                {answers.length < 10 && <Button type="button" size="sm" variant="secondary" onClick={() => setAnswers([...answers, ""])}><Plus className="size-4" aria-hidden /> {t("polls.addAnswer")}</Button>}
              </fieldset>
              <div className="flex flex-wrap items-end gap-6">
                <Field id="poll-hours" label={t("polls.duration")}>
                  <select id="poll-hours" className={cn(inputClass, "w-40")} value={hours} onChange={(e) => setHours(Number(e.target.value))}>
                    {[1, 4, 8, 24, 72, 168, 336].map((h) => <option key={h} value={h}>{h < 24 ? t("duration.nHours", { n: h }) : t("duration.nDays", { n: h / 24 })}</option>)}
                  </select>
                </Field>
                <label className="flex items-center gap-3 pb-2 text-sm"><Switch checked={multiple} label={t("polls.multiple")} onCheckedChange={setMultiple} />{t("polls.multiple")}</label>
              </div>
              <Button disabled={!valid} loading={create.isPending} onClick={() => create.mutate()}>{t("polls.send")}</Button>
              {last && <a href={last} target="_blank" rel="noopener noreferrer" className="ml-3 inline-flex items-center gap-1 text-[13px] text-primary-text hover:underline">{t("embeds.openInDiscord")} <ExternalLink className="size-3.5" aria-hidden /></a>}
            </fieldset>
          </Card>
          <Card className="h-fit">
            <CardHeader title={t("welcome.settings")} />
            <fieldset disabled={!ctl.canEdit} className="space-y-3 p-5">
              <label className="flex items-center justify-between gap-4 text-sm">{t("polls.allowMembers")}<Switch checked={ctl.form.allow_members} label={t("polls.allowMembers")} onCheckedChange={(v) => ctl.setForm({ allow_members: v })} /></label>
              <p className="text-[12px] text-muted">{t("polls.commandHelp")}</p>
            </fieldset>
          </Card>
        </div>
      )}
    </ModulePage>
  );
}
