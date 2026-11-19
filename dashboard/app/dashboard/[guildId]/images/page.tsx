"use client";

import { ExternalLink, ImageIcon, Info, Sparkles, Trash2 } from "lucide-react";
import { useFormatter, useTranslations } from "next-intl";
import { useState } from "react";

import { type MediaItem, type MediaPlace, mb, mediaSrc, UploadZone, useMedia } from "@/components/media-picker";
import { ConfirmDialog } from "@/components/save-bar";
import { Badge, Button, Card, EmptyState, ErrorState, PageHeader, Skeleton } from "@/components/ui";
import { useGuildId } from "@/lib/hooks";
import { cn } from "@/lib/utils";

type Filter = "all" | "used" | "unused";

export default function ImagesPage() {
  const t = useTranslations("media");
  const tr = useTranslations();
  const format = useFormatter();
  const guildId = useGuildId();
  const { list, upload, remove, cleanup, send } = useMedia(guildId);
  const [filter, setFilter] = useState<Filter>("all");
  const [toDelete, setToDelete] = useState<MediaItem | null>(null);
  const [askCleanup, setAskCleanup] = useState(false);
  const data = list.data;

  const place = (p: MediaPlace) => {
    if (p.type === "module_configs") {
      const key = `nav.items.${p.name}`;
      return tr.has(key) ? tr(key) : p.name;
    }
    return t(`place_${p.type}`, { name: p.name });
  };

  const items = data?.items ?? [];
  const unused = items.filter((m) => m.used_in.length === 0);
  const shown = filter === "all" ? items : filter === "used" ? items.filter((m) => m.used_in.length) : unused;
  const ttl = data?.usage.unused_ttl_days ?? 7;
  const pct = data ? Math.min(100, Math.max((data.usage.bytes / data.usage.max_bytes) * 100, (data.usage.count / data.usage.max_count) * 100)) : 0;
  const unusedBytes = unused.reduce((n, m) => n + m.size, 0);

  return (
    <div>
      <PageHeader title={t("pageTitle")} description={t("pageDescription")} action={
        data?.can_edit && unused.length > 0 && (
          <Button variant="secondary" loading={cleanup.isPending} onClick={() => setAskCleanup(true)}>
            <Sparkles className="size-4" aria-hidden /> {t("cleanup", { count: unused.length })}
          </Button>
        )
      } />

      {list.isError ? <ErrorState error={list.error} onRetry={() => list.refetch()} /> : !data ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">{Array.from({ length: 4 }, (_, i) => <Skeleton key={i} className="h-56" />)}</div>
      ) : (
        <div className="space-y-6">
          <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
            <Card className="p-5">
              <div className="flex flex-wrap items-baseline justify-between gap-2 text-sm">
                <span className="font-medium">{t("space")}</span>
                <span className="text-muted">{t("usage", { count: data.usage.count, max: data.usage.max_count, used: mb(data.usage.bytes), total: mb(data.usage.max_bytes) })}</span>
              </div>
              <div className="mt-3 h-2 overflow-hidden rounded-full bg-input">
                <div className={cn("h-full rounded-full", pct > 90 ? "bg-danger" : pct > 70 ? "bg-warning" : "bg-primary")} style={{ width: `${pct}%` }} />
              </div>
              <p className="mt-3 flex items-start gap-2 text-[13px] text-muted">
                <Info className="mt-0.5 size-4 shrink-0" aria-hidden />
                <span>{t("autoCleanup", { days: ttl })}{unused.length > 0 && <> {t("unusedNow", { count: unused.length, size: mb(unusedBytes) })}</>}</span>
              </p>
            </Card>
            {data.can_edit && <UploadZone send={send} pending={upload.isPending} maxFile={data.usage.max_file} />}
          </div>

          <div className="flex flex-wrap gap-2" role="tablist">
            {(["all", "used", "unused"] as const).map((f) => {
              const n = f === "all" ? items.length : f === "used" ? items.length - unused.length : unused.length;
              return (
                <button key={f} type="button" role="tab" aria-selected={filter === f} onClick={() => setFilter(f)}
                  className={cn("rounded-full border px-3 py-1 text-[13px] font-medium transition-colors",
                    filter === f ? "border-primary bg-primary/15 text-primary-text" : "border-border text-muted hover:bg-panel-hover")}>
                  {t(`filter_${f}`)} · {n}
                </button>
              );
            })}
          </div>

          {shown.length === 0 ? (
            <EmptyState icon={ImageIcon} title={items.length ? t("emptyFilter") : t("empty")} body={items.length ? "" : t("emptyBody")} />
          ) : (
            <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
              {shown.map((m) => {
                const src = mediaSrc(guildId, m.url)!;
                const created = new Date(m.created_at);
                const expires = new Date(created.getTime() + ttl * 86400000);
                return (
                  <li key={m.id}>
                    <Card className="flex h-full flex-col overflow-hidden">
                      <a href={src} target="_blank" rel="noreferrer" className="group relative block bg-[repeating-conic-gradient(var(--nx-input)_0_25%,transparent_0_50%)] bg-[length:16px_16px]">
                        {/* eslint-disable-next-line @next/next/no-img-element */}
                        <img src={src} alt={m.filename} loading="lazy" className="aspect-video w-full object-contain" />
                        <span className="absolute right-2 top-2 rounded-md bg-black/60 p-1 text-white opacity-0 transition-opacity group-hover:opacity-100"><ExternalLink className="size-3.5" aria-hidden /></span>
                      </a>
                      <div className="flex flex-1 flex-col gap-2 p-3">
                        <div className="min-w-0">
                          <p className="truncate text-sm font-medium" title={m.filename}>{m.filename}</p>
                          <p className="text-[12px] text-muted">{mb(m.size)} · {format.dateTime(created, { dateStyle: "medium" })}</p>
                        </div>
                        {m.used_in.length ? (
                          <div className="flex flex-wrap gap-1">
                            {m.used_in.slice(0, 4).map((p, i) => <Badge key={i} tone="primary" className="normal-case tracking-normal">{place(p)}</Badge>)}
                            {m.used_in.length > 4 && <Badge>+{m.used_in.length - 4}</Badge>}
                          </div>
                        ) : (
                          <p className="text-[12px] text-warning">{t("unusedUntil", { date: format.dateTime(expires < new Date() ? new Date() : expires, { dateStyle: "medium" }) })}</p>
                        )}
                        {data.can_edit && (
                          <Button variant="ghost" size="sm" className="mt-auto self-end text-danger" onClick={() => setToDelete(m)}>
                            <Trash2 className="size-4" aria-hidden /> {t("delete")}
                          </Button>
                        )}
                      </div>
                    </Card>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      )}

      <ConfirmDialog open={toDelete !== null} destructive title={t("delete")}
        body={toDelete?.used_in.length ? t("confirmDeleteUsed", { places: toDelete.used_in.map(place).join(", ") }) : t("confirmDelete")}
        confirmLabel={t("delete")} onCancel={() => setToDelete(null)}
        onConfirm={() => { if (toDelete) remove.mutate(toDelete.id); setToDelete(null); }} />
      <ConfirmDialog open={askCleanup} destructive title={t("cleanupTitle")}
        body={t("cleanupBody", { count: unused.length, size: mb(unusedBytes) })}
        confirmLabel={t("cleanup", { count: unused.length })} onCancel={() => setAskCleanup(false)}
        onConfirm={() => { cleanup.mutate(); setAskCleanup(false); }} />
    </div>
  );
}
