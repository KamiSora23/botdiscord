"use client";

import { useTranslations } from "next-intl";

import { Button } from "@/components/ui";

export default function ErrorPage({ reset }: { error: Error; reset: () => void }) {
  const t = useTranslations();
  return (
    <div className="grid min-h-[60dvh] place-items-center px-4 text-center">
      <div className="space-y-3">
        <p className="font-mono text-sm text-danger">500</p>
        <h1 className="text-2xl font-semibold">{t("states.errorTitle")}</h1>
        <p className="text-muted">{t("states.errorBody")}</p>
        <Button variant="secondary" onClick={reset}>
          {t("common.retry")}
        </Button>
      </div>
    </div>
  );
}
