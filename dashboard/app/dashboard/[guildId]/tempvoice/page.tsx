"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Mic, Wand2 } from "lucide-react";
import { useTranslations } from "next-intl";
import { toast } from "sonner";

import { useChannels } from "@/components/channel-select";
import { ModulePage } from "@/components/module-page";
import { Button, Card, CardHeader, Field, inputClass } from "@/components/ui";
import { api, errorText } from "@/lib/api";
import { useGuildId } from "@/lib/hooks";
import { useModuleConfig } from "@/lib/use-module";

type Cfg = { hub_channel_id: string | null; category_id: string | null; name_template: string; default_limit: number; max_rooms_per_user: number };

export default function TempVoicePage() {
  const t = useTranslations();
  const guildId = useGuildId();
  const qc = useQueryClient();
  const ctl = useModuleConfig<Cfg>(guildId, "tempvoice");
  const form = ctl.form;
  const set = (p: Partial<Cfg>) => form && ctl.setForm({ ...form, ...p });
  const { data: channels } = useChannels(guildId);
  const voice = (channels ?? []).filter((c) => c.type === "voice");
  const categories = (channels ?? []).filter((c) => c.type === "category");
  const catName = (id: string | null) => categories.find((c) => c.id === id)?.name;

  const setup = useMutation({
    mutationFn: () => api<{ category_id: string; hub_channel_id: string }>(`/guilds/${guildId}/tempvoice/setup`, { method: "POST" }),
    onSuccess: async (r) => {
      await qc.invalidateQueries({ queryKey: ["channels", guildId] });
      set({ hub_channel_id: r.hub_channel_id, category_id: r.category_id });
      toast.success(t("tempvoice.created"));
    },
    onError: (e) => toast.error(errorText(e, t("states.errorBody"))),
  });

  const preview = (form?.name_template || "{user}").replace("{user}", "ju@n25");

  return (
    <ModulePage ctl={ctl as never} title={t("nav.items.tempvoice")} description={t("tempvoice.description")}>
      {form && (
        <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
          <Card>
            <CardHeader icon={Mic} title={t("welcome.settings")} />
            <fieldset disabled={!ctl.canEdit} className="grid gap-4 p-5 sm:grid-cols-2">
              <Field id="tv-hub" label={t("tempvoice.hub")} help={t("tempvoice.hubHelp")}>
                <select id="tv-hub" className={inputClass} value={form.hub_channel_id ?? ""} onChange={(e) => set({ hub_channel_id: e.target.value || null })}>
                  <option value="">{t("tempvoice.pickVoice")}</option>
                  {voice.map((c) => <option key={c.id} value={c.id}>🔊 {c.name}{c.parent_id ? ` · ${catName(c.parent_id) ?? ""}` : ""}</option>)}
                </select>
              </Field>
              <Field id="tv-cat" label={t("tempvoice.category")} help={t("tempvoice.categoryHelp")}>
                <select id="tv-cat" className={inputClass} value={form.category_id ?? ""} onChange={(e) => set({ category_id: e.target.value || null })}>
                  <option value="">{t("tempvoice.sameCategory")}</option>
                  {categories.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
                </select>
              </Field>
              <Field id="tv-name" label={t("tempvoice.nameTemplate")} help={t("tempvoice.nameHelp", { preview })}>
                <input id="tv-name" className={inputClass} maxLength={90} value={form.name_template} onChange={(e) => set({ name_template: e.target.value })} />
              </Field>
              <Field id="tv-limit" label={t("tempvoice.defaultLimit")} help={t("tempvoice.limitHelp")}>
                <input id="tv-limit" type="number" min={0} max={99} className={inputClass} value={form.default_limit} onChange={(e) => set({ default_limit: Math.max(0, Math.min(99, Number(e.target.value))) })} />
              </Field>
              <Field id="tv-max" label={t("tempvoice.maxRooms")}>
                <select id="tv-max" className={inputClass} value={form.max_rooms_per_user} onChange={(e) => set({ max_rooms_per_user: Number(e.target.value) })}>
                  {[1, 2, 3].map((n) => <option key={n} value={n}>{n}</option>)}
                </select>
              </Field>
            </fieldset>
          </Card>
          <div className="space-y-4">
            <Card>
              <div className="space-y-3 p-5">
                <p className="text-sm font-semibold text-text">{t("tempvoice.quickTitle")}</p>
                <p className="text-[13px] text-muted">{t("tempvoice.quickHelp")}</p>
                <Button className="w-full" variant="secondary" disabled={!ctl.canManage || !ctl.enabled} loading={setup.isPending} onClick={() => setup.mutate()}>
                  <Wand2 className="size-4" aria-hidden /> {t("tempvoice.quickButton")}
                </Button>
                {!ctl.enabled && <p className="text-[12px] text-muted">{t("tempvoice.enableFirst")}</p>}
              </div>
            </Card>
            <Card>
              <div className="space-y-2 p-5 text-[13px] text-muted">
                <p className="text-sm font-semibold text-text">{t("tempvoice.howTitle")}</p>
                <p>{t("tempvoice.how")}</p>
                <p className="font-mono text-[12px]">{t("tempvoice.commands")}</p>
              </div>
            </Card>
          </div>
        </div>
      )}
    </ModulePage>
  );
}
