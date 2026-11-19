"use client";

import { useQuery } from "@tanstack/react-query";
import { CheckCircle2, KeyRound, Layers, Radio, XCircle } from "lucide-react";
import { useTranslations } from "next-intl";

import { Card, CardHeader, ErrorState, LinkButton, Notice, PageHeader, Skeleton } from "@/components/ui";
import { api } from "@/lib/api";
import { useGuildId } from "@/lib/hooks";
import type { Diagnostics } from "@/lib/types";

export default function DiagnosticsPage() {
  const t = useTranslations();
  const guildId = useGuildId();
  const q = useQuery({
    queryKey: ["diagnostics", guildId],
    queryFn: () => api<Diagnostics>(`/guilds/${guildId}/diagnostics`),
  });

  return (
    <div className="space-y-6">
      <PageHeader
        title={t("diagnostics.title")}
        description={t("diagnostics.description")}
        action={
          q.data?.invite_url && q.data.permissions.some((p) => !p.granted) ? (
            <LinkButton href={q.data.invite_url} target="_blank" rel="noopener noreferrer">
              {t("diagnostics.reinvite")}
            </LinkButton>
          ) : null
        }
      />
      {q.isPending ? (
        <Skeleton className="h-96" />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : (
        <>
          {q.data.issues.length === 0 && <Notice tone="info" icon={CheckCircle2}>{t("diagnostics.allGood")}</Notice>}

          <Card id="field-permissions" className="scroll-mt-24">
            <CardHeader icon={KeyRound} title={t("diagnostics.permissionsTitle")} />
            <ul className="divide-y divide-border">
              {q.data.permissions.map((p) => (
                <li key={p.permission} className="flex flex-wrap items-center gap-3 px-5 py-3">
                  {p.granted ? (
                    <CheckCircle2 className="size-5 text-success" aria-hidden />
                  ) : (
                    <XCircle className="size-5 text-danger" aria-hidden />
                  )}
                  <div className="min-w-0 flex-1">
                    <p className="font-medium">{t.has(`permissions.${p.permission}`) ? t(`permissions.${p.permission}`) : p.permission}</p>
                    <p className="text-[12px] text-muted">
                      {t("diagnostics.usedBy", {
                        modules: p.required_by.map((m) => (m === "core" ? "NEXUS" : t.has(`nav.items.${m}`) ? t(`nav.items.${m}`) : m)).join(", "),
                      })}
                    </p>
                  </div>
                  <span className={p.granted ? "text-[13px] text-success" : "text-[13px] font-medium text-danger"}>
                    {p.granted ? t("diagnostics.granted") : t("diagnostics.missing")}
                  </span>
                </li>
              ))}
            </ul>
          </Card>

          <Card id="field-intents" className="scroll-mt-24">
            <CardHeader icon={Radio} title={t("diagnostics.intentsTitle")} />
            <ul className="divide-y divide-border">
              <IntentRow label={t("diagnostics.intentGuildMembers")} value={q.data.intents.guild_members} required />
              <IntentRow label={t("diagnostics.intentMessageContent")} value={q.data.intents.message_content} required />
            </ul>
          </Card>

          <Card>
            <CardHeader icon={Layers} title={t("diagnostics.hierarchyTitle")} />
            <p className="px-5 py-4 text-muted">{t("diagnostics.hierarchyBody")}</p>
          </Card>
        </>
      )}
    </div>
  );
}

function IntentRow({ label, value, required }: { label: string; value: boolean | null; required?: boolean }) {
  const t = useTranslations("diagnostics");
  let state: React.ReactNode;
  if (!required) state = <span className="text-[13px] text-muted">{t("notNeeded")}</span>;
  else if (value === null || value === undefined) state = <span className="text-[13px] text-muted">{t("unknown")}</span>;
  else
    state = (
      <span className={value ? "text-[13px] text-success" : "text-[13px] font-medium text-danger"}>
        {value ? t("granted") : t("missing")}
      </span>
    );
  return (
    <li className="flex items-center justify-between gap-3 px-5 py-3">
      <span className="font-medium">{label}</span>
      {state}
    </li>
  );
}
