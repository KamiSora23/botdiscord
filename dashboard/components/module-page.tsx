"use client";

import { useQuery } from "@tanstack/react-query";
import { ShieldAlert } from "lucide-react";
import Link from "next/link";
import { useTranslations } from "next-intl";

import { ConfirmDialog, SaveBar } from "@/components/save-bar";
import { ErrorState, Notice, PageHeader, ReadOnlyNotice, Skeleton, Switch } from "@/components/ui";
import { api } from "@/lib/api";
import type { useModuleConfig } from "@/lib/use-module";

type Ctl = ReturnType<typeof useModuleConfig<unknown>>;
type Diag = { permissions: { permission: string; granted: boolean; required_by: string[] }[] };

/** Permisos de Discord que le faltan a NEXUS para este módulo (mismo dato que la página Diagnóstico). */
function MissingPermissions({ guildId, module }: { guildId: string; module: string }) {
  const t = useTranslations();
  const q = useQuery({ queryKey: ["diagnostics", guildId], queryFn: () => api<Diag>(`/guilds/${guildId}/diagnostics`), staleTime: 60_000 });
  const missing = (q.data?.permissions ?? []).filter((p) => !p.granted && p.required_by.includes(module));
  if (!missing.length) return null;
  return (
    <Notice tone="warning" icon={ShieldAlert} action={
      <Link href={`/dashboard/${guildId}/diagnostics`} className="whitespace-nowrap text-[13px] font-medium underline">{t("module.permsFix")}</Link>
    }>
      {t("module.permsMissing", { perms: missing.map((p) => (t.has(`permissions.${p.permission}`) ? t(`permissions.${p.permission}`) : p.permission)).join(", ") })}
    </Notice>
  );
}

/** Estructura común de una página de módulo: cabecera con interruptor, avisos, barra de guardado y conflicto. */
export function ModulePage({ ctl, title, description, toggleable = true, errorCount = 0, children }: {
  ctl: Ctl; title: string; description: string; toggleable?: boolean; errorCount?: number; children: React.ReactNode;
}) {
  const t = useTranslations();
  if (ctl.query.isError) return <ErrorState error={ctl.query.error} onRetry={() => ctl.query.refetch()} />;
  if (ctl.query.isPending || ctl.form === null) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-10 w-72" />
        <Skeleton className="h-[480px]" />
      </div>
    );
  }
  return (
    <div className="space-y-6 pb-28">
      <PageHeader
        title={title}
        description={description}
        action={
          toggleable ? (
            <label className="flex items-center gap-3 rounded-xl border border-border bg-panel px-4 py-2.5 text-sm font-medium">
              {ctl.enabled ? t("common.enabled") : t("common.disabled")}
              <Switch checked={ctl.enabled} disabled={!ctl.canManage || ctl.toggling} onCheckedChange={ctl.setEnabled} label={title} />
            </label>
          ) : null
        }
      />
      {!ctl.canEdit && <ReadOnlyNotice />}
      {ctl.enabled && <MissingPermissions guildId={ctl.guildId} module={ctl.module} />}
      {toggleable && !ctl.enabled && <Notice tone="info">{t("module.disabledNotice")}</Notice>}
      {ctl.warnings.map((w, i) => (
        <Notice key={i} tone="warning">
          {t.has(`editor.warn_${w.code}`) ? t(`editor.warn_${w.code}`) : w.code}
        </Notice>
      ))}
      <div className={toggleable && !ctl.enabled ? "opacity-75" : undefined}>{children}</div>
      {ctl.canEdit && (
        <SaveBar dirty={ctl.dirty} saving={ctl.saving} errorCount={errorCount} onSave={ctl.saveNow} onDiscard={ctl.discard} />
      )}
      <ConfirmDialog
        open={ctl.conflict !== null}
        title={t("save.conflictTitle")}
        body={t("save.conflictBody")}
        cancelLabel={t("save.conflictReload")}
        confirmLabel={t("save.conflictOverwrite")}
        destructive
        onCancel={ctl.reloadAfterConflict}
        onConfirm={ctl.overwrite}
      />
    </div>
  );
}
