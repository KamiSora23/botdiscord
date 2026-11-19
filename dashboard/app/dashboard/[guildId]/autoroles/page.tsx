"use client";

import { Bot, UserPlus } from "lucide-react";
import { useTranslations } from "next-intl";

import { ModulePage } from "@/components/module-page";
import { RoleMultiSelect, useRoles } from "@/components/multi-select";
import { Card, CardHeader, Field, inputClass, Notice, Switch } from "@/components/ui";
import { useGuildId } from "@/lib/hooks";
import { useModuleConfig } from "@/lib/use-module";

type Cfg = { human_role_ids: string[]; bot_role_ids: string[]; delay_seconds: number; wait_for_screening: boolean };

export default function AutorolesPage() {
  const t = useTranslations();
  const guildId = useGuildId();
  const ctl = useModuleConfig<Cfg>(guildId, "autoroles");
  const { data: roles } = useRoles(guildId);
  const form = ctl.form;
  const set = (p: Partial<Cfg>) => form && ctl.setForm({ ...form, ...p });
  const blocked = form
    ? (roles ?? []).filter((r) => [...form.human_role_ids, ...form.bot_role_ids].includes(r.id) && !r.bot_can_assign)
    : [];

  return (
    <ModulePage ctl={ctl as never} title={t("nav.items.autoroles")} description={t("autoroles.description")}>
      {form && (
        <div className="space-y-6">
          {blocked.length > 0 && <Notice tone="warning">{t("autoroles.hierarchy", { roles: blocked.map((r) => r.name).join(", ") })}</Notice>}
          <div className="grid gap-6 lg:grid-cols-2">
            <Card>
              <CardHeader icon={UserPlus} title={t("autoroles.humans")} description={t("autoroles.humansHelp")} />
              <fieldset disabled={!ctl.canEdit} className="p-5">
                <Field id="ar-humans" label={t("autoroles.roles")}>
                  <RoleMultiSelect id="ar-humans" guildId={guildId} value={form.human_role_ids} onChange={(v) => set({ human_role_ids: v.slice(0, 10) })} />
                </Field>
              </fieldset>
            </Card>
            <Card>
              <CardHeader icon={Bot} title={t("autoroles.bots")} description={t("autoroles.botsHelp")} />
              <fieldset disabled={!ctl.canEdit} className="p-5">
                <Field id="ar-bots" label={t("autoroles.roles")}>
                  <RoleMultiSelect id="ar-bots" guildId={guildId} value={form.bot_role_ids} onChange={(v) => set({ bot_role_ids: v.slice(0, 10) })} />
                </Field>
              </fieldset>
            </Card>
          </div>
          <Card>
            <CardHeader title={t("autoroles.timing")} />
            <fieldset disabled={!ctl.canEdit} className="space-y-4 p-5">
              <label className="flex items-center justify-between gap-4">
                <span>
                  <span className="block text-sm font-medium">{t("autoroles.waitScreening")}</span>
                  <span className="text-[13px] text-muted">{t("autoroles.waitScreeningHelp")}</span>
                </span>
                <Switch checked={form.wait_for_screening} label={t("autoroles.waitScreening")} onCheckedChange={(v) => set({ wait_for_screening: v })} />
              </label>
              <Field id="ar-delay" label={t("autoroles.delay")} help={t("autoroles.delayHelp")}>
                <select id="ar-delay" className={inputClass} value={form.delay_seconds} onChange={(e) => set({ delay_seconds: Number(e.target.value) })}>
                  {[0, 10, 30, 60, 300, 600, 1800, 3600].map((s) => (
                    <option key={s} value={s}>
                      {s === 0 ? t("autoroles.noDelay") : s < 60 ? t("welcome.seconds", { n: s }) : s < 3600 ? t("welcome.minutes", { n: s / 60 }) : t("welcome.hours", { n: 1 })}
                    </option>
                  ))}
                </select>
              </Field>
            </fieldset>
          </Card>
        </div>
      )}
    </ModulePage>
  );
}
