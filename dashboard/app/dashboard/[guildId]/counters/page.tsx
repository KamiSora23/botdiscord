"use client";

import { useMutation } from "@tanstack/react-query";
import { BarChart3, Plus, RefreshCw, Trash2, Wand2 } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { toast } from "sonner";

import { useChannels } from "@/components/channel-select";
import { ModulePage } from "@/components/module-page";
import { Badge, Button, Card, CardHeader, EmptyState, Field, inputClass } from "@/components/ui";
import { api, errorText } from "@/lib/api";
import { useGuildId } from "@/lib/hooks";
import { useModuleConfig } from "@/lib/use-module";
import { cn } from "@/lib/utils";

const TYPES = ["members", "humans", "bots", "boosts", "channels", "roles", "in_voice"] as const;
type CType = (typeof TYPES)[number];
type Counter = { id?: string; type: CType; template: string; channel_id: string | null };
type Cfg = { category_id: string | null; counters: Counter[] };

const newId = () => Math.random().toString(16).slice(2, 10).padEnd(8, "0");

export default function CountersPage() {
  const t = useTranslations();
  const guildId = useGuildId();
  const ctl = useModuleConfig<Cfg>(guildId, "counters");
  const form = ctl.form;
  const set = (p: Partial<Cfg>) => form && ctl.setForm({ ...form, ...p });
  const upd = (i: number, p: Partial<Counter>) => form && set({ counters: form.counters.map((c, j) => (j === i ? { ...c, ...p } : c)) });
  const { data: channels } = useChannels(guildId);
  const [values, setValues] = useState<Record<string, number> | null>(null);

  const setup = useMutation({
    mutationFn: () => api<{ created: number }>(`/guilds/${guildId}/counters/setup`, { method: "POST" }),
    onSuccess: (r) => { toast.success(t("counters.created", { n: r.created })); ctl.query.refetch().then(() => ctl.discard()); },
    onError: (e) => toast.error(errorText(e, t("states.errorBody"))),
  });
  const refresh = useMutation({
    mutationFn: () => api<{ changed: number; values: Record<string, number> }>(`/guilds/${guildId}/counters/refresh`, { method: "POST" }),
    onSuccess: (r) => { setValues(r.values); toast.success(t("counters.refreshed", { n: r.changed })); },
    onError: (e) => toast.error(errorText(e, t("states.errorBody"))),
  });

  const bad = form?.counters.some((c) => !c.template.includes("{count}")) ?? false;
  const missing = form?.counters.filter((c) => !c.channel_id || !channels?.some((ch) => ch.id === c.channel_id)).length ?? 0;
  const preview = (c: Counter) => c.template.replace("{count}", values?.[c.type] != null ? new Intl.NumberFormat().format(values[c.type]) : "123");

  return (
    <ModulePage ctl={ctl as never} title={t("nav.items.counters")} description={t("counters.description")} errorCount={bad ? 1 : 0}>
      {form && (
        <div className="space-y-6">
          <Card>
            <CardHeader icon={BarChart3} title={t("counters.list")} description={t("counters.listHelp")} action={
              ctl.canEdit && <Button size="sm" disabled={form.counters.length >= 10} onClick={() => set({ counters: [...form.counters, { id: newId(), type: "members", template: t("counters.tpl_members"), channel_id: null }] })}><Plus className="size-4" aria-hidden /> {t("counters.add")}</Button>
            } />
            {form.counters.length === 0 ? <EmptyState icon={BarChart3} title={t("counters.none")} body={t("counters.noneBody")} /> : (
              <fieldset disabled={!ctl.canEdit} className="divide-y divide-border">
                {form.counters.map((c, i) => {
                  const exists = !!c.channel_id && channels?.some((ch) => ch.id === c.channel_id);
                  return (
                    <div key={c.id ?? i} className="grid items-end gap-3 px-5 py-4 sm:grid-cols-[200px_1fr_auto_auto]">
                      <Field id={`ct-type-${i}`} label={t("counters.type")}>
                        <select id={`ct-type-${i}`} className={inputClass} value={c.type} onChange={(e) => {
                          const type = e.target.value as CType;
                          upd(i, { type, template: t(`counters.tpl_${type}`) });
                        }}>
                          {TYPES.map((x) => <option key={x} value={x}>{t(`counters.type_${x}`)}</option>)}
                        </select>
                      </Field>
                      <Field id={`ct-tpl-${i}`} label={t("counters.template")} error={!c.template.includes("{count}") ? t("counters.needCount") : undefined}>
                        <input id={`ct-tpl-${i}`} className={inputClass} maxLength={90} value={c.template} onChange={(e) => upd(i, { template: e.target.value })} />
                      </Field>
                      <div className="pb-2 text-[13px]">
                        <span className="block text-muted">{t("counters.preview")}</span>
                        <span className="font-medium">🔊 {preview(c)}</span>
                      </div>
                      <div className="flex items-center gap-2 pb-1.5">
                        <Badge tone={exists ? "success" : "neutral"}>{exists ? t("counters.live") : t("counters.noChannel")}</Badge>
                        <Button variant="ghost" size="sm" aria-label={t("automod.delete")} onClick={() => set({ counters: form.counters.filter((_, j) => j !== i) })}><Trash2 className="size-4" /></Button>
                      </div>
                    </div>
                  );
                })}
              </fieldset>
            )}
          </Card>

          <Card>
            <div className="flex flex-wrap items-center gap-3 p-5">
              <div className="min-w-0 flex-1 text-[13px] text-muted">
                <p>{t("counters.howTo")}</p>
                <p className="mt-1">{t("counters.limit")}</p>
              </div>
              <Button disabled={!ctl.canManage || !ctl.enabled || ctl.dirty || bad || missing === 0} loading={setup.isPending} onClick={() => setup.mutate()}>
                <Wand2 className="size-4" aria-hidden /> {t("counters.setup", { n: missing })}
              </Button>
              <Button variant="secondary" disabled={!ctl.enabled || ctl.dirty} loading={refresh.isPending} onClick={() => refresh.mutate()}>
                <RefreshCw className={cn("size-4", refresh.isPending && "animate-spin")} aria-hidden /> {t("counters.refresh")}
              </Button>
            </div>
            {ctl.dirty && <p className="px-5 pb-4 text-[12px] text-muted">{t("welcome.saveFirst")}</p>}
          </Card>
        </div>
      )}
    </ModulePage>
  );
}
