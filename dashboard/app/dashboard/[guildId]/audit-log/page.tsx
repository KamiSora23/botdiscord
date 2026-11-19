"use client";

import * as Dialog from "@radix-ui/react-dialog";
import { useInfiniteQuery } from "@tanstack/react-query";
import { History, X } from "lucide-react";
import { useFormatter, useTranslations } from "next-intl";
import { useState } from "react";

import { ActorAvatar, useActionLabel } from "@/components/activity";
import { Button, Card, EmptyState, ErrorState, PageHeader, Skeleton } from "@/components/ui";
import { api } from "@/lib/api";
import { useGuildId } from "@/lib/hooks";
import type { AuditEntry } from "@/lib/types";

type Page = { data: AuditEntry[]; next_cursor: string | null };

export default function AuditLogPage() {
  const t = useTranslations();
  const format = useFormatter();
  const label = useActionLabel();
  const guildId = useGuildId();
  const [open, setOpen] = useState<AuditEntry | null>(null);
  const q = useInfiniteQuery({
    queryKey: ["audit", guildId],
    queryFn: ({ pageParam }) => api<Page>(`/guilds/${guildId}/audit-log?limit=50${pageParam ? `&cursor=${pageParam}` : ""}`),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next_cursor,
  });
  const rows = q.data?.pages.flatMap((p) => p.data) ?? [];

  return (
    <div className="space-y-6">
      <PageHeader title={t("audit.title")} description={t("audit.description")} />
      {q.isPending ? (
        <Skeleton className="h-96" />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : rows.length === 0 ? (
        <Card>
          <EmptyState icon={History} title={t("audit.empty")} />
        </Card>
      ) : (
        <Card className="overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[560px] text-left text-sm">
              <thead className="border-b border-border text-[12px] uppercase tracking-wider text-muted">
                <tr>
                  <th scope="col" className="px-5 py-3 font-semibold">{t("audit.date")}</th>
                  <th scope="col" className="px-5 py-3 font-semibold">{t("audit.who")}</th>
                  <th scope="col" className="px-5 py-3 font-semibold">{t("audit.action")}</th>
                  <th scope="col" className="px-5 py-3"><span className="sr-only">{t("audit.viewChanges")}</span></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {rows.map((e) => (
                  <tr key={e.id} className="hover:bg-panel-hover/50">
                    <td className="whitespace-nowrap px-5 py-3 text-muted">
                      {format.dateTime(new Date(e.created_at), { dateStyle: "medium", timeStyle: "short" })}
                    </td>
                    <td className="px-5 py-3">
                      <span className="flex items-center gap-2">
                        <ActorAvatar entry={e} size={24} />
                        {e.actor?.name ?? (e.source === "bot" ? "NEXUS" : t("audit.system"))}
                      </span>
                    </td>
                    <td className="px-5 py-3">{label(e)}</td>
                    <td className="px-5 py-3 text-right">
                      {e.changes && Object.keys(e.changes).length > 0 && (
                        <Button variant="ghost" size="sm" onClick={() => setOpen(e)}>
                          {t("audit.viewChanges")}
                        </Button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {q.hasNextPage && (
            <div className="border-t border-border p-3 text-center">
              <Button variant="secondary" onClick={() => q.fetchNextPage()} loading={q.isFetchingNextPage}>
                {t("audit.loadMore")}
              </Button>
            </div>
          )}
        </Card>
      )}

      <Dialog.Root open={open !== null} onOpenChange={(o) => !o && setOpen(null)}>
        <Dialog.Portal>
          <Dialog.Overlay className="fixed inset-0 z-50 bg-black/60" />
          <Dialog.Content className="fixed inset-y-0 right-0 z-50 w-[min(480px,100vw)] overflow-y-auto border-l border-border bg-sidebar p-6">
            <div className="mb-5 flex items-center justify-between">
              <Dialog.Title className="text-lg font-semibold">{t("audit.changes")}</Dialog.Title>
              <Dialog.Close className="grid size-9 place-items-center rounded-lg text-muted hover:bg-panel-hover" aria-label={t("common.close")}>
                <X className="size-5" />
              </Dialog.Close>
            </div>
            {open && (
              <dl className="space-y-4">
                {Object.entries(open.changes ?? {}).map(([field, { old, new: next }]) => (
                  <div key={field} className="rounded-lg border border-border bg-panel p-3">
                    <dt className="mb-2 font-mono text-[12px] text-primary-text">{field}</dt>
                    <dd className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-[13px]">
                      <span className="text-muted">{t("audit.before")}</span>
                      <code className="break-all font-mono text-danger/90">{show(old)}</code>
                      <span className="text-muted">{t("audit.after")}</span>
                      <code className="break-all font-mono text-success">{show(next)}</code>
                    </dd>
                  </div>
                ))}
              </dl>
            )}
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
    </div>
  );
}

function show(v: unknown): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "number" && v > 0xff && v <= 0xffffff) return `${v} (#${v.toString(16).padStart(6, "0").toUpperCase()})`;
  return typeof v === "string" ? v : JSON.stringify(v);
}
