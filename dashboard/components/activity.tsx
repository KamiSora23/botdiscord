"use client";

import { Bot, Settings2 } from "lucide-react";
import { useFormatter, useNow, useTranslations } from "next-intl";

import { Avatar } from "@/components/ui";
import type { AuditEntry } from "@/lib/types";

export function useActionLabel() {
  const t = useTranslations();
  return (entry: AuditEntry) => {
    const moduleName = entry.module ? t.has(`nav.items.${entry.module}`) ? t(`nav.items.${entry.module}`) : entry.module : "";
    const key = `actions.${entry.action.replaceAll(".", "_")}`;
    return t.has(key) ? t(key, { module: moduleName }) : t("actions.unknown", { action: entry.action });
  };
}

export function ActorAvatar({ entry, size = 28 }: { entry: AuditEntry; size?: number }) {
  if (entry.actor) return <Avatar url={entry.actor.avatar_url} size={size} />;
  const Icon = entry.source === "bot" ? Bot : Settings2;
  return (
    <span className="grid shrink-0 place-items-center rounded-full bg-input" style={{ width: size, height: size }}>
      <Icon className="size-3.5 text-muted" aria-hidden />
    </span>
  );
}

export function RelativeTime({ iso }: { iso: string }) {
  const format = useFormatter();
  const now = useNow({ updateInterval: 60_000 });
  const date = new Date(iso);
  return (
    <time dateTime={iso} title={format.dateTime(date, { dateStyle: "medium", timeStyle: "short" })}>
      {format.relativeTime(date, now)}
    </time>
  );
}
