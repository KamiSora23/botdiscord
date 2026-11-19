"use client";

import { MessageCircleReply, Pin, Plus, Tag as TagIcon, Trash2 } from "lucide-react";
import { useTranslations } from "next-intl";

import { ChannelSelect } from "@/components/channel-select";
import { ModulePage } from "@/components/module-page";
import { ChannelMultiSelect } from "@/components/multi-select";
import { Button, Card, CardHeader, EmptyState, Field, inputClass, Switch } from "@/components/ui";
import { useGuildId } from "@/lib/hooks";
import { useModuleConfig } from "@/lib/use-module";
import { cn } from "@/lib/utils";

type Tag = { name: string; content: string };
type Trigger = { id?: string; keywords: string[]; match: "contains" | "word" | "exact" | "starts"; response: string; channel_ids: string[]; reply: boolean; cooldown_seconds: number };
type Sticky = { channel_id: string | null; content: string };
type Cfg = { tags: Tag[]; triggers: Trigger[]; stickies: Sticky[] };

const newId = () => Math.random().toString(16).slice(2, 10).padEnd(8, "0");

export default function ResponsesPage() {
  const t = useTranslations();
  const guildId = useGuildId();
  const ctl = useModuleConfig<Cfg>(guildId, "responses");
  const form = ctl.form;
  const set = (p: Partial<Cfg>) => form && ctl.setForm({ ...form, ...p });
  const upd = <K extends keyof Cfg>(k: K, idx: number, p: Partial<Cfg[K][number]>) =>
    form && set({ [k]: (form[k] as unknown[]).map((x, i) => (i === idx ? { ...(x as object), ...p } : x)) } as Partial<Cfg>);
  const del = <K extends keyof Cfg>(k: K, idx: number) => form && set({ [k]: (form[k] as unknown[]).filter((_, i) => i !== idx) } as Partial<Cfg>);

  const tagNames = form?.tags.map((x) => x.name.trim().toLowerCase()) ?? [];
  const dupTag = tagNames.some((n, i) => n && tagNames.indexOf(n) !== i);
  const badTag = form?.tags.some((x) => !/^[a-z0-9áéíóúñü_-]{1,32}$/.test(x.name.trim().toLowerCase().replace(/ /g, "-")) || !x.content.trim()) ?? false;
  const badTrigger = form?.triggers.some((x) => !x.keywords.some((k) => k.trim()) || !x.response.trim()) ?? false;
  const badSticky = form?.stickies.some((x) => !x.channel_id || !x.content.trim()) ?? false;
  const errorCount = [dupTag, badTag, badTrigger, badSticky].filter(Boolean).length;

  return (
    <ModulePage ctl={ctl as never} title={t("nav.items.responses")} description={t("responses.description")} errorCount={errorCount}>
      {form && (
        <div className="space-y-6">
          {/* Etiquetas */}
          <Card>
            <CardHeader icon={TagIcon} title={t("responses.tagsTitle")} description={t("responses.tagsHelp")} action={
              ctl.canEdit && <Button size="sm" disabled={form.tags.length >= 100} onClick={() => set({ tags: [...form.tags, { name: "", content: "" }] })}><Plus className="size-4" aria-hidden /> {t("responses.addTag")}</Button>
            } />
            {form.tags.length === 0 ? <EmptyState icon={TagIcon} title={t("responses.noTags")} body={t("responses.noTagsBody")} /> : (
              <fieldset disabled={!ctl.canEdit} className="divide-y divide-border">
                {form.tags.map((tag, i) => (
                  <div key={i} className="grid gap-3 px-5 py-4 sm:grid-cols-[200px_1fr_auto]">
                    <Field id={`tag-name-${i}`} label={t("responses.tagName")} error={dupTag && tagNames.indexOf(tag.name.trim().toLowerCase()) !== i ? t("responses.dupTag") : undefined}>
                      <div className="flex items-center rounded-lg bg-input"><span className="pl-3 text-[13px] text-muted">/tag</span>
                        <input id={`tag-name-${i}`} className={cn(inputClass, "bg-transparent pl-1.5")} maxLength={32} placeholder="reglas" value={tag.name} onChange={(e) => upd("tags", i, { name: e.target.value.toLowerCase().replace(/ /g, "-") })} />
                      </div>
                    </Field>
                    <Field id={`tag-content-${i}`} label={t("responses.content")}>
                      <textarea id={`tag-content-${i}`} rows={2} className={cn(inputClass, "py-2")} maxLength={2000} value={tag.content} onChange={(e) => upd("tags", i, { content: e.target.value })} />
                    </Field>
                    <Button variant="ghost" size="sm" className="self-end" aria-label={t("automod.delete")} onClick={() => del("tags", i)}><Trash2 className="size-4" /></Button>
                  </div>
                ))}
              </fieldset>
            )}
          </Card>

          {/* Respuestas automáticas */}
          <Card>
            <CardHeader icon={MessageCircleReply} title={t("responses.triggersTitle")} description={t("responses.triggersHelp")} action={
              ctl.canEdit && <Button size="sm" disabled={form.triggers.length >= 50} onClick={() => set({ triggers: [...form.triggers, { id: newId(), keywords: [""], match: "word", response: "", channel_ids: [], reply: true, cooldown_seconds: 30 }] })}><Plus className="size-4" aria-hidden /> {t("responses.addTrigger")}</Button>
            } />
            {form.triggers.length === 0 ? <EmptyState icon={MessageCircleReply} title={t("responses.noTriggers")} body={t("responses.noTriggersBody")} /> : (
              <fieldset disabled={!ctl.canEdit} className="divide-y divide-border">
                {form.triggers.map((tr, i) => (
                  <div key={tr.id ?? i} className="grid gap-3 px-5 py-4 lg:grid-cols-2">
                    <Field id={`tr-kw-${i}`} label={t("responses.keywords")} help={t("responses.keywordsHelp")}>
                      <input id={`tr-kw-${i}`} className={inputClass} placeholder={t("responses.keywordsPh")} value={tr.keywords.join(", ")} onChange={(e) => upd("triggers", i, { keywords: e.target.value.split(",").map((k) => k.trimStart()).slice(0, 10) })} />
                    </Field>
                    <Field id={`tr-match-${i}`} label={t("responses.match")}>
                      <select id={`tr-match-${i}`} className={inputClass} value={tr.match} onChange={(e) => upd("triggers", i, { match: e.target.value as Trigger["match"] })}>
                        {(["word", "contains", "starts", "exact"] as const).map((m) => <option key={m} value={m}>{t(`responses.match_${m}`)}</option>)}
                      </select>
                    </Field>
                    <Field id={`tr-resp-${i}`} label={t("responses.response")} help={t("responses.responseHelp")}>
                      <textarea id={`tr-resp-${i}`} rows={2} className={cn(inputClass, "py-2")} maxLength={2000} value={tr.response} onChange={(e) => upd("triggers", i, { response: e.target.value })} />
                    </Field>
                    <div className="space-y-3">
                      <Field id={`tr-ch-${i}`} label={t("responses.onlyChannels")} help={t("responses.onlyChannelsHelp")}>
                        <ChannelMultiSelect id={`tr-ch-${i}`} guildId={guildId} value={tr.channel_ids} onChange={(v) => upd("triggers", i, { channel_ids: v })} />
                      </Field>
                      <div className="flex flex-wrap items-center gap-4">
                        <label className="flex items-center gap-2 text-sm"><Switch checked={tr.reply} label={t("responses.reply")} onCheckedChange={(v) => upd("triggers", i, { reply: v })} />{t("responses.reply")}</label>
                        <label className="flex items-center gap-2 text-sm">{t("responses.cooldown")}
                          <select className={cn(inputClass, "w-28")} value={tr.cooldown_seconds} onChange={(e) => upd("triggers", i, { cooldown_seconds: Number(e.target.value) })}>
                            {[0, 10, 30, 60, 300, 900, 3600].map((s) => <option key={s} value={s}>{s === 0 ? t("responses.noCooldown") : s < 60 ? `${s} s` : `${s / 60} min`}</option>)}
                          </select>
                        </label>
                        <Button variant="ghost" size="sm" className="ml-auto" aria-label={t("automod.delete")} onClick={() => del("triggers", i)}><Trash2 className="size-4" /></Button>
                      </div>
                    </div>
                  </div>
                ))}
              </fieldset>
            )}
          </Card>

          {/* Mensajes fijos */}
          <Card>
            <CardHeader icon={Pin} title={t("responses.stickyTitle")} description={t("responses.stickyHelp")} action={
              ctl.canEdit && <Button size="sm" disabled={form.stickies.length >= 20} onClick={() => set({ stickies: [...form.stickies, { channel_id: null, content: "" }] })}><Plus className="size-4" aria-hidden /> {t("responses.addSticky")}</Button>
            } />
            {form.stickies.length === 0 ? <EmptyState icon={Pin} title={t("responses.noSticky")} body={t("responses.noStickyBody")} /> : (
              <fieldset disabled={!ctl.canEdit} className="divide-y divide-border">
                {form.stickies.map((st, i) => (
                  <div key={i} className="grid gap-3 px-5 py-4 sm:grid-cols-[240px_1fr_auto]">
                    <Field id={`st-ch-${i}`} label={t("welcome.channel")}>
                      <ChannelSelect id={`st-ch-${i}`} guildId={guildId} value={st.channel_id} onChange={(v) => upd("stickies", i, { channel_id: v })} />
                    </Field>
                    <Field id={`st-c-${i}`} label={t("responses.content")}>
                      <textarea id={`st-c-${i}`} rows={2} className={cn(inputClass, "py-2")} maxLength={2000} value={st.content} onChange={(e) => upd("stickies", i, { content: e.target.value })} />
                    </Field>
                    <Button variant="ghost" size="sm" className="self-end" aria-label={t("automod.delete")} onClick={() => del("stickies", i)}><Trash2 className="size-4" /></Button>
                  </div>
                ))}
              </fieldset>
            )}
          </Card>
        </div>
      )}
    </ModulePage>
  );
}
