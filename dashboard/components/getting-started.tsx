"use client";

import { useQueries } from "@tanstack/react-query";
import { ArrowRight, CheckCircle2, Circle, ListChecks, X } from "lucide-react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { Card } from "@/components/ui";
import { api } from "@/lib/api";
import type { Alert, ModuleState } from "@/lib/types";
import { cn } from "@/lib/utils";

type ModResp = { data: { enabled: boolean; config: Record<string, any> } }; // eslint-disable-line @typescript-eslint/no-explicit-any

/** Lista de primeros pasos en Inicio: qué falta configurar y adónde ir para hacerlo. */
export function GettingStarted({ guildId, modules, alerts }: { guildId: string; modules: ModuleState[]; alerts: Alert[] }) {
  const t = useTranslations("start");
  const storageKey = `nexus:start-hidden:${guildId}`;
  const [hidden, setHidden] = useState(false);
  useEffect(() => {
    try { setHidden(localStorage.getItem(storageKey) === "1"); } catch { /* sin almacenamiento */ }
  }, [storageKey]);
  const [logging, antiraid, honeypot] = useQueries({
    queries: ["logging", "antiraid", "honeypot"].map((m) => ({
      queryKey: ["module", guildId, m], queryFn: () => api<ModResp>(`/guilds/${guildId}/modules/${m}`), staleTime: 30_000,
    })),
  });
  const staff = useQueries({
    queries: [{ queryKey: ["permissions", guildId], queryFn: () => api<{ rows: unknown[] }>(`/guilds/${guildId}/permissions`), staleTime: 30_000, retry: false }],
  })[0];
  const on = (m: string) => modules.some((x) => x.module === m && x.enabled);
  const logChannels = Object.values(logging.data?.data.config.categories ?? {}).some((c: any) => c?.channel_id); // eslint-disable-line @typescript-eslint/no-explicit-any

  const steps = [
    { key: "perms", done: !alerts.some((a) => a.code === "missing_permission"), path: "diagnostics" },
    { key: "logs", done: on("logging") && logChannels, path: "logging" },
    { key: "moderation", done: on("moderation"), path: "moderation" },
    { key: "welcome", done: on("welcome"), path: "welcome" },
    { key: "verify", done: on("antiraid") && !!antiraid.data?.data.config.verification?.message_id, path: "antiraid" },
    { key: "honeypot", done: on("honeypot") && !!honeypot.data?.data.config.channel_id, path: "honeypot" },
    { key: "staff", done: (staff.data?.rows.length ?? 0) > 0, path: "permissions", optional: true },
  ];
  const required = steps.filter((s) => !s.optional);
  const doneCount = required.filter((s) => s.done).length;
  const allDone = doneCount === required.length;

  const hide = () => {
    setHidden(true);
    try { localStorage.setItem(storageKey, "1"); } catch { /* sin almacenamiento */ }
  };
  if (hidden) return null;

  return (
    <Card className="overflow-hidden">
      <div className="flex items-start gap-3 px-5 pt-4">
        <ListChecks className="mt-0.5 size-5 text-primary-text" aria-hidden />
        <div className="min-w-0 flex-1">
          <h2 className="font-semibold">{allDone ? t("allDone") : t("title")}</h2>
          <p className="text-[13px] text-muted">{t("progress", { done: doneCount, total: required.length })}</p>
        </div>
        <button type="button" onClick={hide} aria-label={t("hide")} title={t("hide")}
          className="grid size-8 place-items-center rounded-lg text-muted hover:bg-panel-hover hover:text-text"><X className="size-4" /></button>
      </div>
      <div className="mx-5 mt-3 h-1.5 overflow-hidden rounded-full bg-panel-hover">
        <div className="h-full rounded-full bg-primary transition-all" style={{ width: `${(doneCount / required.length) * 100}%` }} />
      </div>
      {!allDone && (
        <ul className="mt-3 divide-y divide-border border-t border-border">
          {steps.map((s) => (
            <li key={s.key}>
              <Link href={`/dashboard/${guildId}/${s.path}`} className="flex items-center gap-3 px-5 py-2.5 text-sm hover:bg-panel-hover">
                {s.done ? <CheckCircle2 className="size-4 shrink-0 text-success" aria-hidden /> : <Circle className="size-4 shrink-0 text-muted" aria-hidden />}
                <span className="min-w-0 flex-1">
                  <span className={cn("font-medium", s.done && "text-muted line-through")}>{t(`${s.key}_title`)}</span>
                  {s.optional && <span className="ml-2 text-[11px] uppercase text-muted">{t("optional")}</span>}
                  {!s.done && <span className="block text-[12px] text-muted">{t(`${s.key}_help`)}</span>}
                </span>
                {!s.done && <ArrowRight className="size-4 shrink-0 text-muted" aria-hidden />}
              </Link>
            </li>
          ))}
        </ul>
      )}
      {allDone && <div className="h-4" />}
    </Card>
  );
}
