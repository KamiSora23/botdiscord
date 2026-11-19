"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Laptop, Trash2, UserRound } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useFormatter, useTranslations } from "next-intl";
import { useMemo, useState } from "react";
import { toast } from "sonner";

import { setLocaleCookie } from "@/components/locale-sync";
import { Avatar, Badge, Button, Card, CardHeader, ErrorState, Field, inputClass, Skeleton } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { useMe } from "@/lib/hooks";
import type { Me, Session } from "@/lib/types";
import { cn } from "@/lib/utils";

function timezones(): string[] {
  try {
    const list = (Intl as unknown as { supportedValuesOf?: (k: string) => string[] }).supportedValuesOf?.("timeZone") ?? [];
    return ["UTC", ...list.filter((z) => z !== "UTC")];
  } catch {
    return ["UTC"];
  }
}

export default function AccountPage() {
  const t = useTranslations();
  const format = useFormatter();
  const router = useRouter();
  const qc = useQueryClient();
  const me = useMe();
  const sessions = useQuery({ queryKey: ["sessions"], queryFn: () => api<{ data: Session[] }>("/me/sessions").then((r) => r.data) });
  const [confirmText, setConfirmText] = useState("");
  const tzs = useMemo(timezones, []);

  const patch = useMutation({
    mutationFn: (body: Partial<Pick<Me, "locale" | "timezone">>) => api<Me>("/me", { method: "PATCH", json: body }),
    onSuccess: (data, body) => {
      qc.setQueryData(["me"], data);
      toast.success(t("account.saved"));
      if (body.locale) {
        setLocaleCookie(body.locale);
        router.refresh();
      }
    },
    onError: (err) => toast.error(err instanceof ApiError ? err.message : t("states.errorBody")),
  });

  const revoke = useMutation({
    mutationFn: (id: string) => api(`/me/sessions/${id}`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["sessions"] }),
  });

  const remove = useMutation({
    mutationFn: () => api("/me", { method: "DELETE", json: { confirm: "DELETE" } }),
    onSuccess: () => {
      window.location.href = "/";
    },
  });

  return (
    <div className="mx-auto max-w-3xl space-y-6 px-4 py-8 sm:px-6">
      <Link href="/dashboard" className="inline-flex items-center gap-1.5 text-sm text-muted hover:text-text">
        <ArrowLeft className="size-4" aria-hidden /> {t("servers.title")}
      </Link>
      <h1 className="text-2xl font-semibold tracking-tight">{t("account.title")}</h1>

      {me.isPending ? (
        <Skeleton className="h-40" />
      ) : me.isError ? (
        <ErrorState error={me.error} onRetry={() => me.refetch()} />
      ) : (
        <>
          <Card>
            <CardHeader icon={UserRound} title={t("account.profile")} />
            <div className="flex items-center gap-4 p-5">
              <Avatar url={me.data.avatar_url} size={56} />
              <div>
                <p className="text-lg font-semibold">{me.data.global_name ?? me.data.username}</p>
                <p className="text-muted">@{me.data.username}</p>
                <p className="font-mono text-[12px] text-muted">{me.data.id}</p>
              </div>
            </div>
          </Card>

          <Card>
            <CardHeader title={t("account.preferences")} />
            <div className="grid gap-5 p-5 sm:grid-cols-2">
              <Field id="account-locale" label={t("account.language")}>
                <select
                  id="account-locale"
                  className={inputClass}
                  value={me.data.locale}
                  disabled={patch.isPending}
                  onChange={(e) => patch.mutate({ locale: e.target.value as Me["locale"] })}
                >
                  <option value="es">Español</option>
                  <option value="en">English</option>
                </select>
              </Field>
              <Field id="account-tz" label={t("account.timezone")}>
                <select
                  id="account-tz"
                  className={inputClass}
                  value={me.data.timezone}
                  disabled={patch.isPending}
                  onChange={(e) => patch.mutate({ timezone: e.target.value })}
                >
                  {tzs.map((z) => (
                    <option key={z} value={z}>
                      {z}
                    </option>
                  ))}
                </select>
              </Field>
            </div>
          </Card>
        </>
      )}

      <Card>
        <CardHeader icon={Laptop} title={t("account.sessions")} />
        {sessions.isPending ? (
          <Skeleton className="m-5 h-16" />
        ) : sessions.isError ? null : (
          <ul className="divide-y divide-border">
            {sessions.data.map((s) => (
              <li key={s.id} className="flex flex-wrap items-center gap-3 px-5 py-3">
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm">{s.user_agent ?? "—"}</p>
                  <p className="text-[12px] text-muted">
                    {s.ip ?? ""} · {t("account.lastSeen", { date: format.dateTime(new Date(s.last_seen_at), { dateStyle: "medium", timeStyle: "short" }) })}
                  </p>
                </div>
                {s.current ? (
                  <Badge tone="primary">{t("account.current")}</Badge>
                ) : (
                  <Button variant="secondary" size="sm" onClick={() => revoke.mutate(s.id)}>
                    {t("account.revoke")}
                  </Button>
                )}
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Card className="border-danger/40">
        <CardHeader icon={Trash2} title={t("account.danger")} />
        <div className="space-y-3 p-5">
          <h3 className="font-semibold">{t("account.deleteTitle")}</h3>
          <p className="text-muted">{t("account.deleteBody")}</p>
          <div className="flex flex-wrap gap-2">
            <input
              aria-label={t("account.deleteConfirm")}
              placeholder={t("account.deleteConfirm")}
              value={confirmText}
              onChange={(e) => setConfirmText(e.target.value)}
              className={cn(inputClass, "max-w-xs font-mono")}
            />
            <Button variant="danger" disabled={confirmText !== "DELETE"} loading={remove.isPending} onClick={() => remove.mutate()}>
              {t("account.deleteButton")}
            </Button>
          </div>
        </div>
      </Card>
    </div>
  );
}
