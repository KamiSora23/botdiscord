"use client";

import { Star } from "lucide-react";
import { useTranslations } from "next-intl";

import { ChannelSelect } from "@/components/channel-select";
import { ModulePage } from "@/components/module-page";
import { ChannelMultiSelect } from "@/components/multi-select";
import { Card, CardHeader, Field, inputClass, Switch } from "@/components/ui";
import { useGuildId } from "@/lib/hooks";
import { useModuleConfig } from "@/lib/use-module";
import { cn } from "@/lib/utils";

type Cfg = { channel_id: string | null; emoji: string; threshold: number; allow_self_star: boolean; include_bots: boolean; ignored_channel_ids: string[] };

export default function StarboardPage() {
  const t = useTranslations();
  const guildId = useGuildId();
  const ctl = useModuleConfig<Cfg>(guildId, "starboard");
  const form = ctl.form;
  const set = (p: Partial<Cfg>) => form && ctl.setForm({ ...form, ...p });
  return (
    <ModulePage ctl={ctl as never} title={t("nav.items.starboard")} description={t("starboard.description")}>
      {form && (
        <Card>
          <CardHeader icon={Star} title={t("welcome.settings")} />
          <fieldset disabled={!ctl.canEdit} className="grid gap-4 p-5 sm:grid-cols-2">
            <Field id="sb-channel" label={t("starboard.channel")}><ChannelSelect id="sb-channel" guildId={guildId} value={form.channel_id} onChange={(v) => set({ channel_id: v })} needEmbed /></Field>
            <div className="flex gap-4">
              <Field id="sb-emoji" label="Emoji"><input id="sb-emoji" className={cn(inputClass, "w-24 text-center")} value={form.emoji} maxLength={64} onChange={(e) => set({ emoji: e.target.value })} /></Field>
              <Field id="sb-threshold" label={t("starboard.threshold")}><input id="sb-threshold" type="number" min={1} max={100} className={cn(inputClass, "w-28")} value={form.threshold} onChange={(e) => set({ threshold: Number(e.target.value) })} /></Field>
            </div>
            <label className="flex items-center justify-between gap-4 text-sm">{t("starboard.selfStar")}<Switch checked={form.allow_self_star} label={t("starboard.selfStar")} onCheckedChange={(v) => set({ allow_self_star: v })} /></label>
            <label className="flex items-center justify-between gap-4 text-sm">{t("starboard.bots")}<Switch checked={form.include_bots} label={t("starboard.bots")} onCheckedChange={(v) => set({ include_bots: v })} /></label>
            <div className="sm:col-span-2">
              <Field id="sb-ignored" label={t("logging.ignoredChannels")}><ChannelMultiSelect id="sb-ignored" guildId={guildId} value={form.ignored_channel_ids} onChange={(v) => set({ ignored_channel_ids: v })} /></Field>
            </div>
            <p className="text-[12px] text-muted sm:col-span-2">{t("starboard.help", { emoji: form.emoji, count: form.threshold })}</p>
          </fieldset>
        </Card>
      )}
    </ModulePage>
  );
}
