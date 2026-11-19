"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";

import { api, ApiError } from "@/lib/api";

export type ModuleData<C> = {
  module: string;
  enabled: boolean;
  config: C;
  version: number;
  updated_at: string | null;
  updated_by: string | null;
};
type ModuleResponse<C> = { data: ModuleData<C>; can_edit: boolean; can_manage: boolean };
export type Warning = { code: string; field?: string };

/**
 * Carga, edita y guarda la configuración de un módulo con control de versiones
 * (docs/NEXUS_API_SPEC.md §6.5). Lo usan todas las páginas de módulos.
 */
export function useModuleConfig<C>(guildId: string, module: string, prepare: (c: C) => C = (c) => c) {
  const t = useTranslations();
  const qc = useQueryClient();
  const key = ["module", guildId, module];
  const q = useQuery({ queryKey: key, queryFn: () => api<ModuleResponse<C>>(`/guilds/${guildId}/modules/${module}`) });
  const [form, setForm] = useState<C | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [warnings, setWarnings] = useState<Warning[]>([]);
  const [conflict, setConflict] = useState<number | null>(null);

  useEffect(() => {
    if (q.data && form === null) setForm(q.data.data.config);
  }, [q.data, form]);

  const saved = q.data?.data.config ?? null;
  const dirty = Boolean(form && saved && JSON.stringify(form) !== JSON.stringify(saved));

  const save = useMutation({
    mutationFn: (version: number) =>
      api<{ data: ModuleData<C>; warnings: Warning[] }>(`/guilds/${guildId}/modules/${module}`, {
        method: "PUT",
        json: { config: prepare(form as C), version },
      }),
    onSuccess: (res) => {
      qc.setQueryData<ModuleResponse<C>>(key, (old) => (old ? { ...old, data: res.data } : old));
      setForm(res.data.config);
      setFieldErrors({});
      setWarnings(res.warnings);
      qc.invalidateQueries({ queryKey: ["overview", guildId] });
      toast.success(t("settings.saved"));
    },
    onError: (err) => {
      if (err instanceof ApiError && err.code === "version_conflict") setConflict(Number(err.body.current_version ?? 0));
      else if (err instanceof ApiError && err.fields) {
        setFieldErrors(err.fields);
        toast.error(t("save.errors", { count: Object.keys(err.fields).length }));
      } else toast.error(err instanceof ApiError ? err.message : t("states.errorBody"));
    },
  });

  const toggle = useMutation({
    mutationFn: (enabled: boolean) =>
      api<{ enabled: boolean; version: number }>(`/guilds/${guildId}/modules/${module}/enabled`, { method: "PATCH", json: { enabled } }),
    onSuccess: (res) => {
      qc.setQueryData<ModuleResponse<C>>(key, (old) => (old ? { ...old, data: { ...old.data, enabled: res.enabled, version: res.version } } : old));
      qc.invalidateQueries({ queryKey: ["overview", guildId] });
      qc.invalidateQueries({ queryKey: ["modules", guildId] });
    },
    onError: (err) => toast.error(err instanceof ApiError ? err.message : t("states.errorBody")),
  });

  const discard = useCallback(() => {
    setForm(saved);
    setFieldErrors({});
  }, [saved]);

  const reloadAfterConflict = () => {
    setConflict(null);
    setForm(null);
    q.refetch();
  };
  const overwrite = () => {
    const v = conflict;
    setConflict(null);
    if (v !== null) save.mutate(v);
  };

  return {
    module,
    guildId,
    query: q,
    form,
    setForm,
    dirty,
    saving: save.isPending,
    saveNow: () => save.mutate(q.data!.data.version),
    discard,
    fieldErrors,
    warnings,
    conflict,
    reloadAfterConflict,
    overwrite,
    enabled: q.data?.data.enabled ?? false,
    setEnabled: (v: boolean) => toggle.mutate(v),
    toggling: toggle.isPending,
    canEdit: q.data?.can_edit ?? false,
    canManage: q.data?.can_manage ?? false,
  };
}

/** Errores cuyo campo empieza por `prefix` (p. ej. "config.join"). */
export function errorsUnder(errors: Record<string, string>, prefix: string): string[] {
  return Object.entries(errors)
    .filter(([k]) => k.startsWith(prefix))
    .map(([, v]) => v);
}
