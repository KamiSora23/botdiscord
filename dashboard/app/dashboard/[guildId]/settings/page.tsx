"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Settings } from "lucide-react";
import { useFormatter, useNow, useTranslations } from "next-intl";
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { ConfirmDialog, SaveBar } from "@/components/save-bar";
import { Card, CardHeader, ErrorState, Field, inputClass, PageHeader, ReadOnlyNotice, Skeleton } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { useGuildId } from "@/lib/hooks";
import type { GuildSettings } from "@/lib/types";
import { cn, colorToHex, hexToColor } from "@/lib/utils";

type Form = { locale: "es" | "en"; timezone: string; color: string };

const SUGGESTED = ["#7465F7", "#5865F2", "#22C55E", "#F59E0B", "#EF4444", "#EC4899", "#06B6D4", "#E5E7EB"];

function timezones(): string[] {
  try {
    const list = (Intl as unknown as { supportedValuesOf?: (k: string) => string[] }).supportedValuesOf?.("timeZone") ?? [];
    return ["UTC", ...list.filter((z) => z !== "UTC")];
  } catch {
    return ["UTC"];
  }
}

function toForm(s: GuildSettings): Form {
  return { locale: s.locale, timezone: s.timezone, color: colorToHex(s.embed_color) };
}

export default function SettingsPage() {
  const t = useTranslations();
  const guildId = useGuildId();
  const qc = useQueryClient();
  const key = ["settings", guildId];
  const q = useQuery({
    queryKey: key,
    queryFn: () => api<{ data: GuildSettings; can_edit: boolean }>(`/guilds/${guildId}/settings`),
  });
  const [form, setForm] = useState<Form | null>(null);
  const [conflict, setConflict] = useState<number | null>(null);

  useEffect(() => {
    if (q.data && form === null) setForm(toForm(q.data.data));
  }, [q.data, form]);

  const saved = q.data ? toForm(q.data.data) : null;
  const dirty = Boolean(form && saved && JSON.stringify(form) !== JSON.stringify(saved));
  const colorValue = form ? hexToColor(form.color) : null;
  const tzs = useMemo(timezones, []);
  const errors: Partial<Record<keyof Form, string>> = {};
  if (form && colorValue === null) errors.color = t("settings.invalidColor");
  if (form && !tzs.includes(form.timezone)) errors.timezone = "—";

  const save = useMutation({
    mutationFn: (version: number) =>
      api<{ data: GuildSettings }>(`/guilds/${guildId}/settings`, {
        method: "PUT",
        json: { locale: form!.locale, timezone: form!.timezone, embed_color: colorValue, version },
      }),
    onSuccess: (res) => {
      qc.setQueryData(key, { data: res.data, can_edit: q.data?.can_edit ?? true });
      setForm(toForm(res.data));
      qc.invalidateQueries({ queryKey: ["overview", guildId] });
      toast.success(t("settings.saved"));
    },
    onError: (err) => {
      if (err instanceof ApiError && err.code === "version_conflict") {
        setConflict(Number(err.body.current_version));
      } else {
        toast.error(err instanceof ApiError ? err.message : t("states.errorBody"));
      }
    },
  });

  if (q.isPending || !form) {
    return q.isError ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : <SettingsSkeleton />;
  }
  const canEdit = q.data!.can_edit;
  const set = <K extends keyof Form>(k: K, v: Form[K]) => setForm({ ...form, [k]: v });

  return (
    <div className="space-y-6 pb-24">
      <PageHeader title={t("settings.title")} description={t("settings.description")} />
      {!canEdit && <ReadOnlyNotice />}

      <Card>
        <CardHeader icon={Settings} title={t("settings.title")} />
        <fieldset disabled={!canEdit} className="grid gap-5 p-5 md:grid-cols-2">
          <Field id="locale" label={t("settings.locale")} help={t("settings.localeHelp")}>
            <select id="locale" className={inputClass} value={form.locale} onChange={(e) => set("locale", e.target.value as Form["locale"])}>
              <option value="es">Español</option>
              <option value="en">English</option>
            </select>
          </Field>

          <Field id="timezone" label={t("settings.timezone")} help={<TimeHelp timezone={form.timezone} />}>
            <input
              id="timezone"
              list="nx-timezones"
              className={inputClass}
              value={form.timezone}
              onChange={(e) => set("timezone", e.target.value)}
              aria-invalid={Boolean(errors.timezone)}
            />
            <datalist id="nx-timezones">
              {tzs.map((z) => (
                <option key={z} value={z} />
              ))}
            </datalist>
          </Field>

          <div className="md:col-span-2">
            <Field id="embed_color" label={t("settings.embedColor")} help={t("settings.embedColorHelp")} error={errors.color}>
              <div className="flex flex-wrap items-center gap-3">
                <input
                  type="color"
                  aria-label={t("settings.embedColor")}
                  value={colorValue !== null ? colorToHex(colorValue).toLowerCase() : "#000000"}
                  onChange={(e) => set("color", e.target.value.toUpperCase())}
                  className="h-10 w-12 cursor-pointer rounded-lg border border-border bg-input p-1"
                />
                <input
                  id="embed_color"
                  className={cn(inputClass, "w-32 font-mono uppercase")}
                  value={form.color}
                  maxLength={7}
                  onChange={(e) => set("color", e.target.value)}
                  aria-invalid={Boolean(errors.color)}
                  aria-describedby={errors.color ? "embed_color-error" : "embed_color-help"}
                />
                <div className="flex flex-wrap gap-2">
                  {SUGGESTED.map((c) => (
                    <button
                      key={c}
                      type="button"
                      onClick={() => set("color", c)}
                      aria-label={c}
                      className="size-8 rounded-lg border-2 border-transparent aria-pressed:border-white"
                      aria-pressed={form.color.toUpperCase() === c}
                      style={{ background: c }}
                    />
                  ))}
                </div>
              </div>
              <div className="mt-3 flex max-w-md overflow-hidden rounded-md bg-[#2b2d31]">
                <span className="w-1 shrink-0" style={{ background: colorValue !== null ? colorToHex(colorValue) : "transparent" }} aria-hidden />
                <div className="px-3 py-2.5 text-[13px]">
                  <p className="font-semibold">NEXUS BOT</p>
                  <p className="text-[#dbdee1]">Embed</p>
                </div>
              </div>
            </Field>
          </div>
        </fieldset>
      </Card>

      {canEdit && (
        <SaveBar
          dirty={dirty}
          saving={save.isPending}
          errorCount={Object.keys(errors).length}
          onSave={() => save.mutate(q.data!.data.version)}
          onDiscard={() => setForm(saved)}
        />
      )}

      <ConfirmDialog
        open={conflict !== null}
        title={t("save.conflictTitle")}
        body={t("save.conflictBody")}
        cancelLabel={t("save.conflictReload")}
        confirmLabel={t("save.conflictOverwrite")}
        destructive
        onCancel={() => {
          setConflict(null);
          setForm(null);
          q.refetch();
        }}
        onConfirm={() => {
          const v = conflict;
          setConflict(null);
          if (v) save.mutate(v);
        }}
      />
    </div>
  );
}

function TimeHelp({ timezone }: { timezone: string }) {
  const t = useTranslations("settings");
  const format = useFormatter();
  const now = useNow({ updateInterval: 30_000 });
  let time = "—";
  try {
    time = format.dateTime(now, { timeZone: timezone, hour: "2-digit", minute: "2-digit", weekday: "short" });
  } catch {
    // zona horaria inválida mientras se escribe
  }
  return <>{t("timezoneHelp", { time })}</>;
}

function SettingsSkeleton() {
  return (
    <div className="space-y-6">
      <Skeleton className="h-9 w-48" />
      <Skeleton className="h-80" />
    </div>
  );
}
