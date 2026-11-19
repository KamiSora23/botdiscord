"use client";

import { AlertTriangle, Loader2 } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { useTranslations } from "next-intl";
import { Suspense, useEffect, useState } from "react";

import { loginUrl } from "@/lib/api";

function LoginRedirect() {
  const t = useTranslations();
  const params = useSearchParams();
  const [problem, setProblem] = useState<"notConfigured" | "apiDown" | null>(null);

  useEffect(() => {
    const next = params.get("next") ?? "/dashboard";
    fetch("/api/v1/health")
      .then((r) => r.json())
      .then((h: { discord_configured?: boolean }) => {
        if (!h.discord_configured) setProblem("notConfigured");
        else window.location.href = loginUrl(next.startsWith("/") ? next : "/dashboard");
      })
      .catch(() => setProblem("apiDown"));
  }, [params]);

  return (
    <div className="grid min-h-dvh place-items-center px-4">
      <div className="flex max-w-md flex-col items-center gap-4 text-center">
        {problem ? (
          <>
            <AlertTriangle className="size-8 text-warning" aria-hidden />
            <p>{problem === "notConfigured" ? t("login.notConfigured") : t("states.apiDown")}</p>
          </>
        ) : (
          <>
            <Loader2 className="size-8 animate-spin text-primary" aria-hidden />
            <p className="text-muted">{t("login.redirecting")}</p>
          </>
        )}
      </div>
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense>
      <LoginRedirect />
    </Suspense>
  );
}
