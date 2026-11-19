"use client";

import { useQueries } from "@tanstack/react-query";
import { ArrowRight, Hash, MapPin, MessageSquare, Mic, ScrollText, Shield, Tags, Users } from "lucide-react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { ChannelSelect, useChannels } from "@/components/channel-select";
import { ModulePage } from "@/components/module-page";
import { ChannelMultiSelect } from "@/components/multi-select";
import { Card, CardHeader, Field, Switch } from "@/components/ui";
import { api } from "@/lib/api";
import { useGuildId } from "@/lib/hooks";
import { useModuleConfig } from "@/lib/use-module";

type Category = { channel_id: string | null; events: Record<string, boolean>; event_channels: Record<string, string> };
type LogCfg = { categories: Record<string, Category>; ignored_channel_ids: string[]; ignore_bots: boolean };
type ModResp = { data: { enabled: boolean; config: Record<string, unknown> } };

const CATS = [
  { key: "messages", icon: MessageSquare },
  { key: "members", icon: Users },
  { key: "roles", icon: Tags },
  { key: "channels", icon: Hash },
  { key: "moderation", icon: Shield },
  { key: "voice", icon: Mic },
];

// Registros que envían otros módulos (con su campo de canal y la página donde se cambia).
const OTHER = [
  { module: "moderation", field: "log_channel_id", path: "moderation", label: "logging.dest_cases", fallbackLogs: "mod_case" },
  { module: "automod", field: "log_channel_id", path: "automod", label: "logging.dest_automod", fallbackLogs: "automod_action" },
  { module: "antiraid", field: "alert_channel_id", path: "antiraid", label: "logging.dest_antiraid", fallbackModeration: true },
  { module: "tickets", field: "transcript_channel_id", path: "tickets", label: "logging.dest_tickets" },
  { module: "ai_moderation", field: "alert_channel_id", path: "ai-moderation", label: "logging.dest_ai" },
] as const;

export default function LoggingPage() {
  const t = useTranslations();
  const guildId = useGuildId();
  const ctl = useModuleConfig<LogCfg>(guildId, "logging");
  const form = ctl.form;
  const { data: channels } = useChannels(guildId);
  const [perEvent, setPerEvent] = useState<Record<string, boolean>>({});
  const setCat = (k: string, p: Partial<Category>) =>
    form && ctl.setForm({ ...form, categories: { ...form.categories, [k]: { ...form.categories[k]!, ...p } } });
  useEffect(() => {
    const cat = window.location.hash.slice(1);
    if (!form || !CATS.some((c) => c.key === cat)) return;
    setPerEvent((p) => ({ ...p, [cat]: true }));
    requestAnimationFrame(() => document.getElementById(`cat-${cat}`)?.scrollIntoView({ behavior: "smooth", block: "start" }));
  }, [form !== null]); // eslint-disable-line react-hooks/exhaustive-deps
  const others = useQueries({
    queries: OTHER.map((o) => ({ queryKey: ["module", guildId, o.module], queryFn: () => api<ModResp>(`/guilds/${guildId}/modules/${o.module}`) })),
  });
  const chName = (id: string | null | undefined) => (id ? `#${channels?.find((c) => c.id === id)?.name ?? "?"}` : null);
  const eventChannel = (cat: string, ev: string) => {
    const c = form?.categories[cat];
    if (!c || c.events[ev] === false) return null;
    return c.event_channels?.[ev] ?? c.channel_id;
  };

  return (
    <ModulePage ctl={ctl as never} title={t("nav.items.logging")} description={t("logging.description")}>
      {form && (
        <div className="space-y-6">
          {/* Resumen: dónde va cada registro del servidor */}
          <Card>
            <CardHeader icon={MapPin} title={t("logging.whereTitle")} description={t("logging.whereHelp")} />
            <ul className="divide-y divide-border text-sm">
              {CATS.map(({ key, icon: Icon }) => {
                const c = form.categories[key];
                if (!c) return null;
                const dests = Array.from(new Set(Object.keys(c.events).map((ev) => eventChannel(key, ev)).filter(Boolean))) as string[];
                return (
                  <li key={key} className="flex items-center justify-between gap-3 px-5 py-2.5">
                    <span className="flex items-center gap-2"><Icon className="size-4 text-muted" aria-hidden />{t(`logging.cat_${key}`)}</span>
                    <span className={dests.length ? "text-primary-text" : "text-muted"}>{dests.length ? dests.map(chName).join(", ") : t("logging.notSent")}</span>
                  </li>
                );
              })}
              {OTHER.map((o, n) => {
                const q = others[n];
                const enabled = q.data?.data.enabled;
                const own = q.data?.data.config?.[o.field] as string | null | undefined;
                let dest = own ?? null;
                let via: string | null = null;
                if (!dest && "fallbackLogs" in o) { dest = eventChannel("moderation", o.fallbackLogs); via = t("logging.viaLogs"); }
                if (!dest && "fallbackModeration" in o) {
                  const mod = others[0].data?.data.config?.log_channel_id as string | null | undefined;
                  dest = mod ?? eventChannel("moderation", "mod_case"); via = t("logging.viaModeration");
                }
                return (
                  <li key={o.module} className="flex items-center justify-between gap-3 px-5 py-2.5">
                    <span className="flex items-center gap-2 text-muted">{t(o.label)}{enabled === false && <span className="text-[12px]">· {t("logging.moduleOff")}</span>}</span>
                    <Link href={`/dashboard/${guildId}/${o.path}`} className="flex items-center gap-1.5 hover:underline">
                      <span className={dest ? "text-primary-text" : "text-muted"}>{dest ? chName(dest) : t("logging.notSent")}</span>
                      {via && dest && <span className="text-[12px] text-muted">({via})</span>}
                      <ArrowRight className="size-3.5 text-muted" aria-hidden />
                    </Link>
                  </li>
                );
              })}
            </ul>
          </Card>

          <div className="grid gap-6 lg:grid-cols-2">
            {CATS.map(({ key, icon }) => {
              const c = form.categories[key];
              if (!c) return null;
              const overrides = c.event_channels ?? {};
              const showPer = perEvent[key] ?? Object.keys(overrides).length > 0;
              return (
                <Card key={key} id={`cat-${key}`} className="scroll-mt-20">
                  <CardHeader icon={icon} title={t(`logging.cat_${key}`)} description={t(`logging.catHelp_${key}`)} />
                  <fieldset disabled={!ctl.canEdit} className="space-y-4 p-5">
                    <Field id={`log-${key}`} label={t("welcome.channel")}>
                      <ChannelSelect id={`log-${key}`} guildId={guildId} value={c.channel_id} onChange={(v) => setCat(key, { channel_id: v })} needEmbed />
                    </Field>
                    <label className="flex items-center justify-between gap-4 text-[13px] text-muted">
                      {t("logging.perEvent")}
                      <Switch checked={showPer} label={t("logging.perEvent")} onCheckedChange={(v) => {
                        setPerEvent({ ...perEvent, [key]: v });
                        if (!v && Object.keys(overrides).length) setCat(key, { event_channels: {} });
                      }} />
                    </label>
                    <ul className="space-y-3">
                      {Object.entries(c.events).map(([ev, on]) => (
                        <li key={ev} className="space-y-1.5">
                          <label className="flex items-center justify-between gap-4 text-sm">
                            {t(`logging.ev_${ev}`)}
                            <Switch checked={on} disabled={!c.channel_id && !overrides[ev]} label={t(`logging.ev_${ev}`)} onCheckedChange={(v) => setCat(key, { events: { ...c.events, [ev]: v } })} />
                          </label>
                          {showPer && on && (
                            <ChannelSelect id={`log-${key}-${ev}`} guildId={guildId} compact needEmbed value={overrides[ev] ?? null}
                              noneLabel={c.channel_id ? t("logging.sameChannel", { channel: chName(c.channel_id) ?? "" }) : t("logging.noChannel")}
                              onChange={(v) => {
                                const next = { ...overrides };
                                if (v) next[ev] = v; else delete next[ev];
                                setCat(key, { event_channels: next });
                              }} />
                          )}
                        </li>
                      ))}
                    </ul>
                  </fieldset>
                </Card>
              );
            })}
            <Card>
              <CardHeader icon={ScrollText} title={t("logging.options")} />
              <fieldset disabled={!ctl.canEdit} className="space-y-4 p-5">
                <label className="flex items-center justify-between gap-4 text-sm">
                  {t("logging.ignoreBots")}
                  <Switch checked={form.ignore_bots} label={t("logging.ignoreBots")} onCheckedChange={(v) => ctl.setForm({ ...form, ignore_bots: v })} />
                </label>
                <Field id="log-ignored" label={t("logging.ignoredChannels")} help={t("logging.ignoredHelp")}>
                  <ChannelMultiSelect id="log-ignored" guildId={guildId} value={form.ignored_channel_ids} onChange={(v) => ctl.setForm({ ...form, ignored_channel_ids: v })} />
                </Field>
                <p className="text-[12px] text-muted">{t("logging.privacy")}</p>
              </fieldset>
            </Card>
          </div>
        </div>
      )}
    </ModulePage>
  );
}
