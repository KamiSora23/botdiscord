"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BookOpen, Briefcase, Check, Gamepad2, LifeBuoy, Sparkles, Video, Wand2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { toast } from "sonner";

import { ChannelSelect } from "@/components/channel-select";
import { Badge, Button, Card, ErrorState, Field, Notice, PageHeader, Skeleton, Switch } from "@/components/ui";
import { api, errorText } from "@/lib/api";
import { useGuildId } from "@/lib/hooks";
import { cn } from "@/lib/utils";

type Tpl = { key: string; modules: string[] };
type Resp = { templates: Tpl[]; configured: string[]; slots: string[]; can_apply: boolean };

const ICONS: Record<string, typeof Gamepad2> = { gaming: Gamepad2, support: LifeBuoy, creator: Video, study: BookOpen, professional: Briefcase, minimal: Sparkles };
const SLOT_MODULE: Record<string, string> = { welcome: "welcome", logs: "logging", mod_log: "moderation", suggestions: "suggestions", levels: "levels" };

export default function SetupPage() {
  const t = useTranslations();
  const router = useRouter();
  const guildId = useGuildId();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["templates", guildId], queryFn: () => api<Resp>(`/guilds/${guildId}/templates`) });
  const [step, setStep] = useState(1);
  const [tpl, setTpl] = useState<string | null>(null);
  const [modules, setModules] = useState<string[]>([]);
  const [channels, setChannels] = useState<Record<string, string | null>>({});
  const [overwrite, setOverwrite] = useState(false);
  const apply = useMutation({
    mutationFn: () => api<{ applied: string[]; skipped: string[] }>(`/guilds/${guildId}/setup`, { method: "POST", json: { template: tpl, modules, channels, overwrite } }),
    onSuccess: (r) => {
      toast.success(t("setup.done", { count: r.applied.length }));
      qc.invalidateQueries();
      router.push(`/dashboard/${guildId}/overview`);
    },
    onError: (e) => toast.error(errorText(e, t("states.errorBody"))),
  });

  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (q.isPending) return <Skeleton className="h-96" />;
  const data = q.data;
  const chosen = data.templates.find((x) => x.key === tpl);
  const slots = data.slots.filter((s) => modules.includes(SLOT_MODULE[s]!));
  const overlap = modules.filter((m) => data.configured.includes(m));
  const modName = (m: string) => (t.has(`nav.items.${m}`) ? t(`nav.items.${m}`) : m);

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <PageHeader title={t("setup.title")} description={t("setup.description")} />
      <ol className="flex flex-wrap gap-2 text-[13px]" aria-label={t("setup.steps")}>
        {[1, 2, 3].map((n) => (
          <li key={n} className={cn("flex items-center gap-2 rounded-full px-3 py-1", step === n ? "bg-primary-solid text-white" : step > n ? "bg-success/15 text-success" : "bg-input text-muted")}>
            {step > n ? <Check className="size-3.5" aria-hidden /> : <span className="font-semibold">{n}</span>} {t(`setup.step${n}`)}
          </li>
        ))}
      </ol>
      {!data.can_apply && <Notice tone="info">{t("states.readOnly")}</Notice>}

      {step === 1 && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {data.templates.map((x) => {
            const Icon = ICONS[x.key] ?? Wand2;
            return (
              <button key={x.key} type="button" aria-pressed={tpl === x.key} onClick={() => { setTpl(x.key); setModules(x.modules); }}
                className={cn("rounded-xl border bg-panel p-5 text-left transition-colors", tpl === x.key ? "border-primary bg-primary/10" : "border-border hover:bg-panel-hover")}>
                <Icon className="mb-3 size-6 text-primary-text" aria-hidden />
                <p className="font-semibold">{t(`setup.tpl_${x.key}`)}</p>
                <p className="mt-1 text-[13px] text-muted">{t(`setup.tplDesc_${x.key}`)}</p>
                <p className="mt-3 text-[12px] text-muted">{t("setup.modulesCount", { count: x.modules.length })}</p>
              </button>
            );
          })}
        </div>
      )}

      {step === 2 && chosen && (
        <Card className="p-5">
          <p className="mb-4 text-sm text-muted">{t("setup.pickModules")}</p>
          <div className="grid gap-2 sm:grid-cols-2">
            {chosen.modules.map((m) => (
              <label key={m} className="flex items-center justify-between gap-3 rounded-lg border border-border px-3 py-2.5 text-sm">
                <span className="flex items-center gap-2">{modName(m)}{data.configured.includes(m) && <Badge tone="primary">{t("setup.alreadyOn")}</Badge>}</span>
                <Switch checked={modules.includes(m)} label={modName(m)} onCheckedChange={(v) => setModules(v ? [...modules, m] : modules.filter((x) => x !== m))} />
              </label>
            ))}
          </div>
        </Card>
      )}

      {step === 3 && (
        <Card className="space-y-4 p-5">
          <p className="text-sm text-muted">{t("setup.pickChannels")}</p>
          {slots.length === 0 && <p className="text-[13px] text-muted">{t("setup.noChannels")}</p>}
          <div className="grid gap-4 sm:grid-cols-2">
            {slots.map((s) => (
              <Field key={s} id={`setup-${s}`} label={t(`setup.slot_${s}`)}>
                <ChannelSelect id={`setup-${s}`} guildId={guildId} value={channels[s] ?? null} onChange={(v) => setChannels({ ...channels, [s]: v })} needEmbed />
              </Field>
            ))}
          </div>
          {overlap.length > 0 && (
            <label className="flex items-start justify-between gap-4 rounded-lg border border-warning/30 bg-warning/10 p-3 text-sm">
              <span>{t("setup.overwrite", { modules: overlap.map(modName).join(", ") })}<span className="block text-[12px] text-muted">{t("setup.overwriteHelp")}</span></span>
              <Switch checked={overwrite} label={t("setup.overwriteLabel")} onCheckedChange={setOverwrite} />
            </label>
          )}
          <p className="text-[12px] text-muted">{t("setup.afterwards")}</p>
        </Card>
      )}

      <div className="flex justify-between gap-2">
        <Button variant="ghost" disabled={step === 1} onClick={() => setStep(step - 1)}>{t("setup.back")}</Button>
        {step < 3 ? (
          <Button disabled={!tpl || (step === 2 && modules.length === 0)} onClick={() => setStep(step + 1)}>{t("setup.next")}</Button>
        ) : (
          <Button disabled={!data.can_apply || modules.length === 0} loading={apply.isPending} onClick={() => apply.mutate()}>
            <Wand2 className="size-4" aria-hidden /> {t("setup.apply")}
          </Button>
        )}
      </div>
    </div>
  );
}
